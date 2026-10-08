"""
饮水提醒模块。

按设定间隔提醒用户喝水，记录每日饮水量，日终检查达成情况。
"""

import random
from datetime import datetime, time, timedelta
from typing import Any, Callable, Dict, Optional

from apscheduler.schedulers.qt import QtScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from core.event_bus import bus, EVENT_HEALTH_REMINDER
from core.service_registry import registry
from core.state_manager import StateManager, UserActivityState
from utils.logger import get_logger

logger = get_logger(__name__)


class DrinkReminder:
    """饮水提醒器。

    核心功能：
    - 按间隔（默认45分钟）提醒喝水
    - 仅在工作时段计时（默认9:00-21:00）
    - 记录每次饮水量（默认250ml/次）
    - 21:00 日终检查，不足目标时温柔提醒
    """

    REMINDER_MESSAGES = [
        "该喝水啦！💧 你的小猫咪提醒你补充水分~",
        "喵~ 已经{}分钟没喝水了，快去倒一杯！",
        "口渴了喵！来一杯水吧，身体会感谢你的~",
        "暂停一下！给你的小身体来点水分补给吧 💙",
        "喝水时间到！每天8杯水，皮肤水嫩嫩~",
    ]

    def __init__(self):
        self._scheduler: Optional[QtScheduler] = None
        self._state_manager: Optional[StateManager] = None
        self._interval_min = 45
        self._daily_target_ml = 2000
        self._cup_size_ml = 250
        self._active_start = time(9, 0)
        self._active_end = time(21, 0)
        self._postpone_min = 15

        self._today_ml = 0
        self._last_drink_time: Optional[datetime] = None
        self._callback: Optional[Callable] = None
        self._postponed = False

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize(self, callback: Optional[Callable] = None) -> None:
        """初始化饮水提醒器。"""
        self._interval_min = self._get_setting_int("health.drink_interval_min", 45)
        self._daily_target_ml = self._get_setting_int("health.drink_target_ml", 2000)
        self._state_manager = registry.get("state_manager")
        self._callback = callback

        self._scheduler = registry.get("health_scheduler")
        if self._scheduler is None:
            self._scheduler = QtScheduler()
            self._scheduler.start()
            registry.register("health_scheduler", self._scheduler)

        # 定时提醒
        self._scheduler.add_job(
            func=self._check_and_remind,
            trigger=IntervalTrigger(minutes=self._interval_min),
            id="drink_reminder",
            replace_existing=True,
        )

        # 日终检查（21:00）
        self._scheduler.add_job(
            func=self._end_of_day_check,
            trigger=CronTrigger(hour=21, minute=0),
            id="drink_eod_check",
            replace_existing=True,
        )

        # 凌晨重置
        self._scheduler.add_job(
            func=self._daily_reset,
            trigger=CronTrigger(hour=0, minute=1),
            id="drink_daily_reset",
            replace_existing=True,
        )

        self._load_today_drinks()
        logger.info(f"饮水提醒器已启动 (间隔={self._interval_min}min, 目标={self._daily_target_ml}ml)")

    # ------------------------------------------------------------------
    # 提醒逻辑
    # ------------------------------------------------------------------

    def _check_and_remind(self) -> None:
        """检查条件并触发饮水提醒。"""
        now = datetime.now().time()

        if now < self._active_start or now > self._active_end:
            return

        # 推迟后恢复原始间隔（P1-8 修复）
        if self._postponed:
            self._postponed = False
            job = self._scheduler.get_job("drink_reminder") if self._scheduler else None
            if job:
                job.reschedule(trigger=IntervalTrigger(minutes=self._interval_min))
            return

        if self._state_manager:
            state = self._state_manager.user_state
            if state in (UserActivityState.BUSY, UserActivityState.SLEEP):
                return
            if not self._state_manager.can_notify():
                return

        self._trigger_reminder()

    def _trigger_reminder(self) -> None:
        """触发饮水提醒通知。"""
        msg = random.choice(self.REMINDER_MESSAGES).format(self._interval_min)
        remaining = max(0, self._daily_target_ml - self._today_ml)
        progress = f"\n今日已饮 {self._today_ml}ml，还差 {remaining}ml"

        schedule_id = f"drink_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        bus.publish(EVENT_HEALTH_REMINDER, {
            "type": "drink_reminder",
            "schedule_id": schedule_id,
            "message": f"{msg}{progress}",
            "target_ml": self._daily_target_ml,
            "current_ml": self._today_ml,
            "priority": 0,
            "buttons": [
                ("🥤 喝啦", "drink", "primary"),
                ("⏭ 跳过", "skip", "secondary"),
            ],
        })

        if self._callback:
            self._callback("drink", f"{msg}{progress}")

        logger.debug(f"饮水提醒触发: 今日 {self._today_ml}/{self._daily_target_ml}ml")

    # ------------------------------------------------------------------
    # 反馈处理
    # ------------------------------------------------------------------

    def handle_feedback(self, action: str) -> str:
        """处理用户对饮水提醒的反馈。"""
        if action == "drink":
            self._today_ml += self._cup_size_ml
            self._last_drink_time = datetime.now()
            log_id = self._record_drink(self._cup_size_ml, triggered=True)
            remaining = max(0, self._daily_target_ml - self._today_ml)
            if remaining == 0:
                return f"太棒了！今日饮水目标达成！🎉 ({self._daily_target_ml}ml)"

            # 发一条5秒可撤回通知
            bus.publish(EVENT_HEALTH_REMINDER, {
                "type": "drink_undo",
                "schedule_id": f"drink_undo_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "message": f"已记录 {self._cup_size_ml}ml ✓",
                "priority": 0,
                "duration_ms": 5000,
                "buttons": [("↩ 撤回", "undo", "secondary")],
                "log_id": log_id,
            })
            return f"真乖~ 今日已饮 {self._today_ml}ml，还差 {remaining}ml 💧"
        elif action == "skip":
            # P1-8 修复：改为15分钟后重试，而非等下一轮45分钟
            self._postponed = True
            if self._scheduler:
                job = self._scheduler.get_job("drink_reminder")
                if job:
                    job.reschedule(trigger=IntervalTrigger(minutes=self._postpone_min))
            return "好吧，记得一会儿喝哦~ 😸"

        return ""

    def manual_drink(self, amount_ml: int = 250) -> None:
        """手动记录饮水。"""
        self._record_drink(amount_ml, triggered=False)
        self._today_ml += amount_ml
        self._last_drink_time = datetime.now()

    # ------------------------------------------------------------------
    # 日终检查
    # ------------------------------------------------------------------

    def _end_of_day_check(self) -> None:
        """每日21:00检查饮水是否达标。"""
        if self._today_ml >= self._daily_target_ml:
            logger.info(f"饮水达标: {self._today_ml}/{self._daily_target_ml}ml")
            return

        shortfall = self._daily_target_ml - self._today_ml
        logger.info(f"饮水不足: {self._today_ml}/{self._daily_target_ml}ml (缺{shortfall}ml)")

        bus.publish(EVENT_HEALTH_REMINDER, {
            "type": "drink_summary",
            "message": f"今天水喝得有点少哦~ 只喝了 {self._today_ml}ml，明天要记得多喝水！💙",
            "current_ml": self._today_ml,
            "target_ml": self._daily_target_ml,
            "priority": 0,
        })

    def _daily_reset(self) -> None:
        """每日凌晨重置饮水计数。"""
        self._today_ml = 0
        self._last_drink_time = None
        self._postponed = False
        # 恢复原始间隔
        if self._scheduler:
            job = self._scheduler.get_job("drink_reminder")
            if job:
                job.reschedule(trigger=IntervalTrigger(minutes=self._interval_min))
        logger.debug("饮水计数已重置")

    # ------------------------------------------------------------------
    # 数据库操作
    # ------------------------------------------------------------------

    def _record_drink(self, amount_ml: int, triggered: bool = False) -> Optional[int]:
        """记录饮水，返回自增 ID。"""
        try:
            db = registry.get("database")
            if db:
                cursor = db.execute(
                    "INSERT INTO drink_log (amount_ml, triggered_by_reminder) VALUES (?, ?)",
                    (amount_ml, 1 if triggered else 0),
                )
                db.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.warning(f"饮水记录失败: {e}")
        return None

    def undo_drink(self, log_id: int) -> str:
        """撤回指定饮水记录。"""
        try:
            db = registry.get("database")
            if db is None:
                return "撤回失败 😿"
            # 只允许撤回最近一条
            cursor = db.execute(
                "SELECT amount_ml FROM drink_log WHERE id = ? AND date(timestamp) = date('now')",
                (log_id,),
            )
            row = cursor.fetchone()
            if not row:
                return "已过期，无法撤回"
            amount = row[0]
            db.execute("DELETE FROM drink_log WHERE id = ?", (log_id,))
            db.commit()
            self._today_ml = max(0, self._today_ml - amount)
            return f"已撤回 {amount}ml"
        except Exception as e:
            logger.error(f"饮水撤回失败: {e}")
            return "撤回失败 😿"

    def _load_today_drinks(self) -> None:
        try:
            db = registry.get("database")
            if db is None:
                return
            cursor = db.execute(
                "SELECT COALESCE(SUM(amount_ml), 0) FROM drink_log "
                "WHERE date(timestamp) = date('now')"
            )
            self._today_ml = cursor.fetchone()[0]
            logger.debug(f"今日已饮: {self._today_ml}ml")
        except Exception as e:
            logger.warning(f"加载饮水记录失败: {e}")

    def _get_setting_int(self, key: str, default: int) -> int:
        """读取整型配置。

        统一走 core.config：app_settings（用户修改）覆盖 config/settings.yaml（出厂默认）。
        key 使用规范键名（如 health.drink_target_ml），历史键名由 config 内部别名兼容。
        """
        from core.config import config

        return config.get_int(key, default)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_daily_stats(self) -> Dict[str, Any]:
        return {
            "current_ml": self._today_ml,
            "target_ml": self._daily_target_ml,
            "percent": round(self._today_ml / max(1, self._daily_target_ml) * 100, 1),
            "remaining_ml": max(0, self._daily_target_ml - self._today_ml),
            "cups": self._today_ml // self._cup_size_ml,
        }

    def update_settings(self, interval_min: int, target_ml: int) -> None:
        self._interval_min = interval_min
        self._daily_target_ml = target_ml

        try:
            db = registry.get("database")
            if db:
                db.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                    ("drink_interval_min", str(interval_min)),
                )
                db.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                    ("drink_daily_target_ml", str(target_ml)),
                )
                db.commit()
        except Exception as e:
            logger.warning(f"设置更新失败: {e}")

        if self._scheduler and not self._postponed:
            job = self._scheduler.get_job("drink_reminder")
            if job:
                job.reschedule(trigger=IntervalTrigger(minutes=interval_min))

        logger.info(f"饮水设置已更新: 间隔={interval_min}min, 目标={target_ml}ml")

    def shutdown(self) -> None:
        if self._scheduler:
            for job_id in ("drink_reminder", "drink_eod_check", "drink_daily_reset"):
                try:
                    self._scheduler.remove_job(job_id)
                except Exception:
                    pass