"""
事件总线模块。

提供发布-订阅模式的事件通信机制，支持三种订阅模式：
- subscribe_sync: 回调在发布线程同步执行（纯数据操作）
- subscribe_async: 回调在线程池异步执行（耗时操作）
- subscribe_ui: 回调通过 Qt 信号槽在主线程执行（UI 更新必须用此模式）
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from utils.logger import get_logger

logger = get_logger(__name__)

# 预定义事件类型
EVENT_SCHEDULE_ALERT = "schedule_alert"
EVENT_HEALTH_REMINDER = "health_reminder"
EVENT_USER_ACTIVITY_CHANGE = "user_activity_change"
EVENT_MOOD_DETECTED = "mood_detected"
EVENT_MEMORY_CREATED = "memory_created"
EVENT_PREFERENCE_UPDATED = "preference_updated"
EVENT_SYSTEM_STATUS = "system_status"
EVENT_UI_ACTION = "ui_action"
EVENT_EXIT_REQUEST = "exit_request"
EVENT_MODE_CHANGE = "mode_change"


class UiSignals(QObject):
    """Qt 信号中转对象，确保 UI 线程安全。"""

    event_emitted = pyqtSignal(str, object)


class EventBus:
    """事件总线，支持同步/异步/UI 线程安全三种订阅模式。"""

    def __init__(self):
        self._sync_subscribers: Dict[str, List[Callable]] = {}
        self._async_subscribers: Dict[str, List[Callable]] = {}
        self._ui_subscribers: Dict[str, List[Callable]] = {}
        self._ui_signals: Optional[UiSignals] = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="eventbus")
        self._lock = threading.RLock()

    def _get_ui_signals(self) -> Optional[UiSignals]:
        """延迟创建 UiSignals。QApplication 不存在时返回 None。"""
        if self._ui_signals is not None:
            return self._ui_signals
        try:
            from PyQt5.QtWidgets import QApplication
            if QApplication.instance() is None:
                return None
            self._ui_signals = UiSignals()
            self._ui_signals.event_emitted.connect(self._on_ui_event)
            return self._ui_signals
        except Exception:
            return None

    def _on_ui_event(self, event_type: str, data: Any) -> None:
        """收到 UI 信号后，在主线程执行对应回调。"""
        with self._lock:
            callbacks = self._ui_subscribers.get(event_type, [])[:]
        for cb in callbacks:
            try:
                cb(data)
            except Exception:
                logger.exception(f"UI 事件回调异常 (event={event_type})")

    # ------------------------------------------------------------------
    # 订阅接口
    # ------------------------------------------------------------------

    def subscribe_sync(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """注册同步订阅者。回调在发布线程中同步执行，不得操作 UI。"""
        with self._lock:
            self._sync_subscribers.setdefault(event_type, []).append(callback)

    def subscribe_async(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """注册异步订阅者。回调在线程池中异步执行。"""
        with self._lock:
            self._async_subscribers.setdefault(event_type, []).append(callback)

    def subscribe_ui(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """注册 UI 订阅者（线程安全）。回调通过 Qt 信号槽调度到主线程。"""
        with self._lock:
            self._ui_subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> bool:
        """取消订阅指定的回调。"""
        removed = False
        with self._lock:
            for store in (self._sync_subscribers, self._async_subscribers, self._ui_subscribers):
                subs = store.get(event_type, [])
                if callback in subs:
                    subs.remove(callback)
                    removed = True
        return removed

    # ------------------------------------------------------------------
    # 发布接口（线程安全）
    # ------------------------------------------------------------------

    def publish(self, event_type: str, data: Any = None) -> None:
        """发布事件。

        在锁内取所有回调快照，锁外执行，避免死锁。
        """
        logger.debug(f"事件发布: {event_type}")

        # 在锁内取快照
        with self._lock:
            ui_subs = self._ui_subscribers.get(event_type, [])[:]
            sync_subs = self._sync_subscribers.get(event_type, [])[:]
            async_subs = self._async_subscribers.get(event_type, [])[:]

        # 1) UI 订阅者（主线程安全）
        if ui_subs:
            signals = self._get_ui_signals()
            if signals:
                signals.event_emitted.emit(event_type, data)

        # 2) 同步订阅者
        for cb in sync_subs:
            try:
                cb(data)
            except Exception:
                logger.exception(f"同步事件回调异常 (event={event_type})")

        # 3) 异步订阅者
        for cb in async_subs:
            self._executor.submit(self._safe_async_callback, event_type, cb, data)

    def _safe_async_callback(self, event_type: str, callback: Callable, data: Any) -> None:
        """安全执行异步回调。"""
        try:
            callback(data)
        except Exception:
            logger.exception(f"异步事件回调异常 (event={event_type})")

    def shutdown(self, wait: bool = True) -> None:
        """关闭事件总线，释放线程池。"""
        self._executor.shutdown(wait=wait)
        logger.info("事件总线已关闭")


# 全局单例
bus = EventBus()