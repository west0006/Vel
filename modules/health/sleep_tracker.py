"""
作息跟踪模块。

记录用户每日首次和末次交互时间，推测睡眠时段。
每7天分析平均作息，检测不规律模式，必要时温和提醒。
"""

from datetime import datetime, date, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from apscheduler.schedulers.qt import QtScheduler
from apscheduler.triggers.cron import CronTrigger

from core.event_bus import bus, EVENT_HEALTH_REMINDER
from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class SleepTracker:
    """作息跟踪器。

    通过记录每日交互时间推测作息，分析睡眠规律性。
    Alpha 版使用简化的启发式推测。
    """

    def __init__(self):
        self._today_first_interaction: Optional[datetime] = None
        self._today_last_interaction: Optional[datetime] = None
        self._no_interaction_minutes = 0
        self._sleep_candidate = False
        self._sleep_time_estimate: Optional[datetime] = None
        # 休眠判定：最后交互后持续 N 分钟无操作
        self._sleep_threshold_min = 30
        self._scheduler = None

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._load_today()

        # 复用全局调度器，如不存在则创建共享实例
        self._scheduler = registry.get("health_scheduler")
        if self._scheduler is None:
            self._scheduler = QtScheduler()
            self._scheduler.start()
            registry.register("health_scheduler", self._scheduler)

        self._scheduler.add_job(
            func=self._save_daily_record,
            trigger=CronTrigger(hour=0, minute=3),
            id="sleep_daily_save",
        )
        self._scheduler.add_job(
            func=self._weekly_analysis,
            trigger=CronTrigger(day_of_week="sun", hour=10, minute=0),
            id="sleep_weekly_analysis",
        )

        logger.info("作息跟踪器已启动")

    # ------------------------------------------------------------------
    # 交互记录
    # ------------------------------------------------------------------

    def record_interaction(self) -> None:
        """记录一次用户交互。"""
        now = datetime.now()

        if self._today_first_interaction is None:
            self._today_first_interaction = now
            logger.debug(f"今日首次交互: {now.strftime('%H:%M:%S')}")

            # 检查是否在睡眠时段醒来
            if self._sleep_time_estimate:
                wake_delta = now - self._sleep_time_estimate
                if wake_delta > timedelta(hours=6):
                    logger.debug(f"推测醒来 (睡眠 {wake_delta.total_seconds()/3600:.1f} 小时)")

        self._today_last_interaction = now
        self._no_interaction_minutes = 0
        self._sleep_candidate = False

    def check_idle(self, idle_minutes: int) -> None:
        """检查空闲时长（外部周期性调用）。

        Args:
            idle_minutes: 连续空闲分钟数
        """
        self._no_interaction_minutes = idle_minutes

        # 长时间无操作 → 推测睡眠
        if idle_minutes >= self._sleep_threshold_min and not self._sleep_candidate:
            self._sleep_candidate = True
            self._sleep_time_estimate = datetime.now() - timedelta(minutes=idle_minutes)
            logger.debug(f"推测入睡: {self._sleep_time_estimate.strftime('%H:%M')}")

    # ------------------------------------------------------------------
    # 每日保存
    # ------------------------------------------------------------------

    def _save_daily_record(self, yesterday: Optional[date] = None) -> None:
        """保存昨日的作息记录到数据库。"""
        yesterday = yesterday or (date.today() - timedelta(days=1))

        try:
            db = registry.get("database")
            if db is None:
                return

            # 检查是否已有记录
            cursor = db.execute("SELECT date FROM sleep_log WHERE date = ?", (yesterday.isoformat(),))
            if cursor.fetchone():
                return  # 已有记录

            sleep_time = self._sleep_time_estimate
            wake_time = self._today_first_interaction

            db.execute(
                "INSERT INTO sleep_log (date, sleep_time_estimate, wake_time_estimate, confidence) "
                "VALUES (?, ?, ?, ?)",
                (
                    yesterday.isoformat(),
                    sleep_time.isoformat() if sleep_time else None,
                    wake_time.isoformat() if wake_time else None,
                    0.5,  # 推测置信度
                ),
            )
            db.commit()
            logger.info(f"作息记录已保存: {yesterday}")

            # 重置今日数据
            self._today_first_interaction = None
            self._today_last_interaction = None
            self._sleep_time_estimate = None

        except Exception as e:
            logger.warning(f"作息保存失败: {e}")

    # ------------------------------------------------------------------
    # 周分析
    # ------------------------------------------------------------------

    def _weekly_analysis(self) -> None:
        """分析近7天作息规律性。"""
        records = self._get_week_records()
        if len(records) < 3:
            logger.debug("作息数据不足（少于3天），跳过分析")
            return

        # 分析睡眠时间
        sleep_times = []
        wake_times = []
        durations = []

        for r in records:
            if r.get("sleep_time"):
                st = datetime.fromisoformat(r["sleep_time"])
                sleep_times.append(st)
            if r.get("wake_time"):
                wt = datetime.fromisoformat(r["wake_time"])
                wake_times.append(wt)
            if r.get("sleep_time") and r.get("wake_time"):
                duration = (datetime.fromisoformat(r["wake_time"]) -
                           datetime.fromisoformat(r["sleep_time"])).total_seconds() / 3600
                durations.append(duration)

        if not sleep_times or not wake_times:
            return

        # 计算平均入睡/起床时间
        avg_sleep_hour = sum(t.hour + t.minute / 60 for t in sleep_times) / len(sleep_times)
        avg_wake_hour = sum(t.hour + t.minute / 60 for t in wake_times) / len(wake_times)
        avg_duration = sum(durations) / len(durations) if durations else 0

        # 计算标准差
        if len(sleep_times) >= 3:
            sleep_std = (
                sum((t.hour + t.minute / 60 - avg_sleep_hour) ** 2 for t in sleep_times)
                / len(sleep_times)
            ) ** 0.5
        else:
            sleep_std = 0

        logger.info(
            f"周作息分析: 均入睡 {avg_sleep_hour:.1f}h, "
            f"均起床 {avg_wake_hour:.1f}h, "
            f"均睡眠 {avg_duration:.1f}h, "
            f"入睡标准差 {sleep_std:.1f}h"
        )

        # 连续性不足（平均<6小时，连续7天）
        if avg_duration < 6 and len(durations) >= 7 and all(d < 6.5 for d in durations):
            bus.publish(EVENT_HEALTH_REMINDER, {
                "type": "sleep_warning",
                "message": "最近睡得有点晚哦～今天早点休息吧，身体需要充足的睡眠！🌙",
                "avg_duration_h": round(avg_duration, 1),
            })
            logger.info("睡眠不足提醒已触发")

        # 极度不规律（标准差 > 2小时）
        if sleep_std > 2.0:
            bus.publish(EVENT_HEALTH_REMINDER, {
                "type": "sleep_irregular",
                "message": "最近作息好像不太规律呢～试着固定一个睡觉时间，对身体更好哦！🐱",
                "std_h": round(sleep_std, 1),
            })
            logger.info("作息不规律提醒已触发")

    def _get_week_records(self) -> List[Dict[str, Any]]:
        """获取近7天作息记录。"""
        try:
            db = registry.get("database")
            if db is None:
                return []
            cursor = db.execute(
                "SELECT * FROM sleep_log WHERE date >= date('now', '-7 days') ORDER BY date ASC"
            )
            return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
        except Exception:
            return []

    def _load_today(self) -> None:
        """加载今日已有的交互记录。"""
        try:
            db = registry.get("database")
            if db is None:
                return
            cursor = db.execute(
                "SELECT sleep_time_estimate, wake_time_estimate FROM sleep_log "
                "WHERE date = date('now', '-1 days')"
            )
            row = cursor.fetchone()
            if row:
                if row[0]:
                    self._sleep_time_estimate = datetime.fromisoformat(row[0])
        except Exception:
            logger.exception("_load_today 执行失败")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_sleep_estimate(self) -> Optional[datetime]:
        """获取推测的入睡时间。"""
        return self._sleep_time_estimate

    def get_weekly_summary(self) -> Dict[str, Any]:
        """获取本周作息摘要。"""
        records = self._get_week_records()
        if not records:
            return {"days_tracked": 0}
        return {
            "days_tracked": len(records),
            "avg_sleep_h": round(
                sum(
                    (datetime.fromisoformat(r["wake_time"]) -
                     datetime.fromisoformat(r["sleep_time"])).total_seconds() / 3600
                    for r in records if r.get("sleep_time") and r.get("wake_time")
                ) / max(1, sum(1 for r in records if r.get("sleep_time") and r.get("wake_time"))),
                1
            ) if records else 0,
        }

    def shutdown(self) -> None:
        """关闭跟踪器。"""
        self._save_daily_record()
