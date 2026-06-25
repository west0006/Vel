"""
番茄钟模块。

状态机：idle → running → break → idle
工具栏按钮启动/暂停，专注期间久坐计时暂停。
"""

import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import QTimer, QObject, pyqtSignal

from core.event_bus import bus
from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class PomodoroTimer(QObject):
    """番茄钟状态机。"""

    tick = pyqtSignal(int)          # 剩余秒数
    state_changed = pyqtSignal(str) # idle/running/break

    def __init__(self, focus_min: int = 25, break_min: int = 5, parent=None):
        super().__init__(parent)
        self._focus_sec = focus_min * 60
        self._break_sec = break_min * 60
        self._remaining = 0
        self._state = "idle"
        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        self._long_break_interval = 4
        self._completed_count = 0
        self._start_time: Optional[datetime] = None
        self._paused_remaining = 0

    @property
    def state(self) -> str:
        return self._state

    @property
    def remaining_seconds(self) -> int:
        return self._remaining

    def start(self) -> None:
        """启动番茄钟。idle→running，break中直接进入新一轮专注。"""
        if self._state == "running":
            return
        if self._state == "break":
            # 休息中点击 → 直接开始新的一轮专注（跳过 idle）
            self._timer.stop()
            self._state = "running"
            self._remaining = self._focus_sec
            self._start_time = datetime.now()
            self._timer.start()
            self.state_changed.emit("running")
            bus.publish("POMODORO_START", {"focus_min": self._focus_sec // 60})
            logger.info(f"番茄钟（休息后直接启动）: {self._focus_sec // 60}分钟")
            return
        self._state = "running"
        self._remaining = self._focus_sec
        self._start_time = datetime.now()
        self._timer.start()
        self.state_changed.emit("running")
        bus.publish("POMODORO_START", {"focus_min": self._focus_sec // 60})
        logger.info(f"番茄钟启动: {self._focus_sec // 60}分钟")
    def pause(self) -> None:
        if self._state != "running":
            return
        self._paused_remaining = self._remaining
        self._timer.stop()
        self._state = "paused"
        self.state_changed.emit("paused")
        bus.publish("POMODORO_PAUSE", {})

    def resume(self) -> None:
        if self._state != "paused":
            return
        self._remaining = self._paused_remaining
        self._state = "running"
        self._timer.start()
        self.state_changed.emit("running")
        bus.publish("POMODORO_RESUME", {})

    def cancel(self) -> None:
        self._timer.stop()
        self._state = "idle"
        self._remaining = 0
        self.state_changed.emit("idle")
        bus.publish("POMODORO_CANCEL", {})
        logger.info("番茄钟已取消")

    def _on_tick(self) -> None:
        self._remaining -= 1
        self.tick.emit(self._remaining)
        if self._remaining <= 0:
            if self._state == "running":
                self._completed_count += 1
                self._enter_break()
            elif self._state == "break":
                self._state = "idle"
                self._timer.stop()
                self._remaining = 0
                self.state_changed.emit("idle")
                self.tick.emit(0)
                bus.publish("POMODORO_END", {"stage": "break_end"})

    def _enter_break(self) -> None:
        is_long = (self._completed_count % self._long_break_interval == 0)
        break_sec = self._break_sec * 3 if is_long else self._break_sec
        self._state = "break"
        self._remaining = break_sec
        self.state_changed.emit("break")
        bus.publish("POMODORO_END", {
            "stage": "focus_end",
            "break_min": break_sec // 60,
            "is_long": is_long,
        })
        logger.info(f"番茄钟结束，进入休息 {break_sec // 60}分钟")

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self._state,
            "remaining": self._remaining,
            "completed": self._completed_count,
            "focus_min": self._focus_sec // 60,
            "break_min": self._break_sec // 60,
        }

    def update_settings(self, focus_min: int, break_min: int) -> None:
        self._focus_sec = max(5, min(120, focus_min)) * 60
        self._break_sec = max(1, min(30, break_min)) * 60