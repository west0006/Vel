"""
久坐检测与活动提醒模块。

监控键鼠活动，计算连续活动时长，超阈值时提醒用户起身活动。
支持动态阈值调节和活动引导。
"""

import random
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import QTimer
from apscheduler.schedulers.qt import QtScheduler
from apscheduler.triggers.cron import CronTrigger

from core.event_bus import bus, EVENT_HEALTH_REMINDER
from core.service_registry import registry
from core.state_manager import StateManager, UserActivityState
from utils.logger import get_logger

logger = get_logger(__name__)


class SedentaryMonitor:
    """久坐活动监控器。

    监控用户连续活动时长，超阈值时触发活动提醒。
    动态阈值根据用户反馈自动调整。
    """

    # 活动建议库
    ACTIVITY_SUGGESTIONS = [
        ("👀 眼保健操", "闭上眼睛，上下左右转动眼球，每次10秒，重复5次", 3),
        ("🤸 肩颈拉伸", "双手抱头，慢慢向后仰，感受肩颈的拉伸，保持15秒", 3),
        ("🚶 起身走动", "离开座位走一圈，看看窗外远方的风景", 3),
        ("💪 手臂伸展", "双手交叉举过头顶，尽量向上伸展，保持10秒", 3),
        ("🧘 深呼吸", "深呼吸5次：吸气4秒→屏息4秒→呼气6秒", 2),
        ("🦵 腿部活动", "站起来踮脚尖20次，促进腿部血液循环", 3),
        ("🙆 转体运动", "坐直，左手扶右膝，右手扶椅背，慢慢向右转体，保持10秒后换边", 3),
        ("🎯 桌面俯卧撑", "双手撑桌，身体倾斜做10个桌面俯卧撑", 2),
    ]

    def __init__(self):
        self._state_manager: Optional[StateManager] = None
        self._threshold_min = 50           # 默认阈值（分钟）
        self._min_threshold = 30
        self._max_threshold = 90
        self._pause_reset_sec = 30         # 连续静置超过此秒数重置计时

        self._last_activity_time = datetime.now()
        self._continuous_min = 0           # 当前连续活动时长

        # 反馈记录（用于动态阈值）
        self._recent_feedbacks: List[bool] = []  # True=接受, False=拒绝
        self._max_feedback_history = 5

        # 活动引导状态
        self._is_guiding = False
        self._guide_total_sec = 0
        self._guide_activity_name = ""
        self._guide_timer = QTimer()
        self._guide_timer = QTimer()
        self._guide_timer.timeout.connect(self._on_guide_tick)
        self._guide_remaining_sec = 0

        # 监控定时器
        self._monitor_timer = QTimer()
        self._monitor_timer.timeout.connect(self._tick)
        self._monitor_timer.setInterval(60 * 1000)  # 每分钟检测一次
        self._monitor_timer.start()

        self._callback: Optional[Callable] = None
        self._pomodoro_paused = False

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize(self, callback: Optional[Callable] = None) -> None:
        """初始化久坐监控器。

        Args:
            callback: 提醒触发时回调
        """
        self._state_manager = registry.get("state_manager")
        self._callback = callback

        # 从数据库读取阈值
        self._threshold_min = self._get_setting_int("sedentary_threshold_min", 50)

        # 每周一重置阈值
        self._setup_weekly_reset()

        logger.info(f"久坐监控器已启动 (阈值={self._threshold_min}min)")

        bus.subscribe_sync("POMODORO_START", lambda d: self._pause_for_pomodoro())
        bus.subscribe_sync("POMODORO_END", lambda d: self._resume_from_pomodoro())

    def _pause_for_pomodoro(self) -> None:
        self._pomodoro_paused = True
        self._continuous_min = 0

    def _resume_from_pomodoro(self) -> None:
        self._pomodoro_paused = False
        self._last_activity_time = datetime.now()

    def _setup_weekly_reset(self) -> None:
        """设置每周一凌晨阈值重置。"""
        try:
            scheduler = registry.get("health_scheduler")
            if scheduler:
                scheduler.add_job(
                    func=self._weekly_reset,
                    trigger=CronTrigger(day_of_week="mon", hour=0, minute=5),
                    id="sedentary_weekly_reset",
                )
        except Exception:
            pass  # 不强制要求

    # ------------------------------------------------------------------
    # 活动检测
    # ------------------------------------------------------------------

    def report_activity(self) -> None:
        """外部报告用户活动（键鼠操作时调用）。"""
        now = datetime.now()
        elapsed = (now - self._last_activity_time).total_seconds()

        if elapsed > self._pause_reset_sec:
            # 静置超过阈值，重置计时
            if self._continuous_min > 0:
                logger.debug(f"活动暂停超过{self._pause_reset_sec}秒，重置计时（之前{self._continuous_min}min）")
            self._continuous_min = 0

        self._last_activity_time = now

    def _tick(self) -> None:
        if getattr(self, '_pomodoro_paused', False):
            return
        """每分钟定时检测。"""
        now = datetime.now()
        elapsed_min = (now - self._last_activity_time).total_seconds() / 60

        if elapsed_min > self._pause_reset_sec / 60:
            # 长时间无操作
            self._continuous_min = 0
            return

        self._continuous_min += 1

        if self._continuous_min >= self._threshold_min:
            self._trigger_reminder()

    # ------------------------------------------------------------------
    # 提醒触发
    # ------------------------------------------------------------------

    def _trigger_reminder(self) -> None:
        """触发活动提醒。"""
        # 检查用户状态
        if self._state_manager:
            state = self._state_manager.user_state
            if state in (UserActivityState.BUSY, UserActivityState.SLEEP):
                return
            if not self._state_manager.can_notify():
                return

        # 随机选择活动建议
        suggestion = random.choice(self.ACTIVITY_SUGGESTIONS)
        name, guide_text, duration_min = suggestion

        message = (
            f"已经连续活动 {self._continuous_min} 分钟啦！\n"
            f"起来活动一下？试试「{name}」"
        )

        schedule_id = f"sedentary_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        bus.publish(EVENT_HEALTH_REMINDER, {
            "type": "sedentary_reminder",
            "schedule_id": schedule_id,
            "message": message,
            "activity_name": name,
            "guide_text": guide_text,
            "duration_min": duration_min,
            "continuous_min": self._continuous_min,
            "buttons": [
                ("🏃 马上休息", "accept", "primary"),
                ("⏭ 忽略", "reject", "secondary"),
            ],
        })

        if self._callback:
            self._callback("sedentary", message)

        logger.info(f"久坐提醒: {self._continuous_min}min → 建议「{name}」")

    # ------------------------------------------------------------------
    # 反馈处理
    # ------------------------------------------------------------------

    def handle_feedback(self, action: str, activity_name: str = "",
                        guide_text: str = "", duration_min: int = 3) -> str:
        """处理用户反馈。

        Args:
            action: accept / reject
            activity_name: 活动名称
            guide_text: 活动指导文字
            duration_min: 活动时长

        Returns:
            回复文本
        """
        if action == "accept":
            # 记录接受
            self._recent_feedbacks.append(True)
            self._adjust_threshold()

            # 重置计时
            self._continuous_min = 0
            self._last_activity_time = datetime.now()

            # 开始活动引导
            if guide_text:
                self._start_guide(activity_name, guide_text, duration_min)

            return f"好的！来一起做「{activity_name}」吧~ ({duration_min}分钟)"

        elif action == "reject":
            # 记录拒绝
            self._recent_feedbacks.append(False)
            self._adjust_threshold()

            # 临时增加阈值（拒绝后不打扰）
            old_threshold = self._threshold_min
            self._threshold_min = min(self._threshold_min + 10, self._max_threshold)
            logger.info(f"拒绝提醒，阈值临时调整: {old_threshold} → {self._threshold_min}min")
            return f"好吧，那我{self._threshold_min}分钟后再提醒你~ 😸"

        return ""

    def _start_guide(self, name: str, text: str, duration_min: int) -> None:
        """开始活动引导（倒计时显示）。"""
        self._is_guiding = True
        self._guide_remaining_sec = duration_min * 60
        self._guide_total_sec = duration_min * 60  # 新增：保存总时长
        self._guide_activity_name = name  # 新增：保存活动名
        self._guide_timer.setInterval(1000)
        self._guide_timer.start()

        try:
            db = registry.get("database")
            if db:
                db.execute(
                    "INSERT INTO activity_log (start_time, activity_type, source) VALUES (?, ?, 'reminder')",
                    (datetime.now().isoformat(), name),
                )
                db.commit()
        except Exception as e:
            logger.warning(f"活动记录失败: {e}")

        bus.publish(EVENT_HEALTH_REMINDER, {
            "type": "activity_guide",
            "activity_name": name,
            "guide_text": text,
            "remaining_sec": self._guide_remaining_sec,
        })

    def _on_guide_tick(self) -> None:
        """活动引导倒计时更新。"""
        self._guide_remaining_sec -= 1
        if self._guide_remaining_sec <= 0:
            self._guide_timer.stop()
            self._is_guiding = False

            try:
                db = registry.get("database")
                if db:
                    # 修正：使用保存的总时长
                    duration = max(1, self._guide_total_sec // 60)
                    db.execute(
                        "UPDATE activity_log SET end_time = ?, duration_min = ? "
                        "WHERE date(start_time) = date('now') "
                        "ORDER BY start_time DESC LIMIT 1",
                        (datetime.now().isoformat(), duration),
                    )
                    db.commit()
            except Exception:
                pass

            bus.publish(EVENT_HEALTH_REMINDER, {
                "type": "activity_complete",
                "message": "活动完成！感觉好多了吧~ 继续加油工作！💪",
            })
            logger.info("活动引导完成")

    # ------------------------------------------------------------------
    # 动态阈值
    # ------------------------------------------------------------------

    def _adjust_threshold(self) -> None:
        """根据最近反馈调整阈值。"""
        if len(self._recent_feedbacks) < self._max_feedback_history:
            return

        recent = self._recent_feedbacks[-self._max_feedback_history:]
        accept_rate = sum(1 for x in recent if x) / len(recent)

        old = self._threshold_min

        if accept_rate < 0.4:
            # 拒绝率 > 60%，放宽阈值
            self._threshold_min = min(self._threshold_min + 10, self._max_threshold)
        elif accept_rate > 0.8:
            # 接受率 > 80%，收紧阈值
            self._threshold_min = max(self._threshold_min - 5, self._min_threshold)

        if old != self._threshold_min:
            logger.info(f"阈值动态调整: {old} → {self._threshold_min}min (接受率={accept_rate:.0%})")

    def _weekly_reset(self) -> None:
        """每周一重置阈值。"""
        default = self._get_setting_int("sedentary_threshold_min", 50)
        self._threshold_min = default
        self._recent_feedbacks.clear()
        logger.info(f"阈值每周重置: {default}min")

    def _get_setting_int(self, key: str, default: int) -> int:
        """从 app_settings 读取配置。"""
        try:
            db = registry.get("database")
            if db:
                cursor = db.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
                row = cursor.fetchone()
                return int(row[0]) if row else default
        except Exception:
            pass
        return default

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """获取当前久坐监控状态。"""
        return {
            "continuous_min": self._continuous_min,
            "threshold_min": self._threshold_min,
            "is_guiding": self._is_guiding,
            "guide_remaining_sec": self._guide_remaining_sec if self._is_guiding else 0,
        }

    def is_guiding(self) -> bool:
        """是否在活动引导中。"""
        return self._is_guiding

    def update_threshold(self, minutes: int) -> None:
        """手动更新阈值。"""
        self._threshold_min = max(self._min_threshold, min(self._max_threshold, minutes))
        logger.info(f"阈值已更新: {self._threshold_min}min")

    def shutdown(self) -> None:
        """关闭监控器。"""
        self._monitor_timer.stop()
        self._guide_timer.stop()