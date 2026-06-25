"""
通知气泡模块。按类型左边框颜色，支持打断逻辑和键盘快捷键。
"""

from typing import Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QColor
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QApplication

from ui.theme import Colors, Fonts, Sizes, get_button_style
from utils.logger import get_logger

logger = get_logger(__name__)

TYPE_BORDER = {
    "schedule": "#FF6B35",
    "health": "#6B9E7A",
    "greeting": "#FFD166",
    "warning": "#D98C7A",
    "memo": "#5A5A5A",
    "habit": "#FF6B35",
}
TYPE_ICON = {
    "schedule": "📅", "health": "💧", "greeting": "☀️",
    "warning": "⚠️", "memo": "📋", "habit": "🏆",
}


class NotificationBubble(QFrame):
    action_taken = pyqtSignal(str, str)

    def __init__(self, parent=None, manager=None):
        super().__init__(parent)
        self._manager = manager
        self._setup_window()
        self._setup_ui()
        self._setup_animation()
        self._notification_id = ""
        self._buttons_spec: List[Tuple[str, str, str]] = []
        self._auto_hide_timer = QTimer()
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.dismiss)
        self._is_dismissing = False
        self.installEventFilter(self)

    def _setup_window(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(320, 120)

    def _setup_ui(self) -> None:
        self._container = QFrame()
        self._container.setStyleSheet(f"""
            QFrame {{ background: {Colors.BG_MAIN}; border: 1px solid {Colors.BORDER}; border-radius: {Sizes.CARD_RADIUS}px; }}
        """)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title_layout = QHBoxLayout()
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(20, 20)
        self._icon_label.setStyleSheet("background: transparent;")
        title_layout.addWidget(self._icon_label)

        self._title_label = QLabel()
        self._title_label.setStyleSheet(f"{Fonts.style(Fonts.SIZE_SM, 600)} color: {Colors.TEXT_PRIMARY}; background: transparent;")
        title_layout.addWidget(self._title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet(f"{Fonts.style(Fonts.SIZE_SM, 400)} color: {Colors.TEXT_SECONDARY}; background: transparent;")
        layout.addWidget(self._message_label)

        self._button_layout = QHBoxLayout()
        self._button_layout.setSpacing(10)
        layout.addLayout(self._button_layout)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

    def _setup_animation(self) -> None:
        self._animation = QPropertyAnimation(self, b"geometry")
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    def show_notification(self, notification_id, notif_type="health", title="", message="",
                          icon="", duration_ms=8000, buttons=None):
        self._notification_id = notification_id
        self._buttons_spec = buttons or []
        border_color = TYPE_BORDER.get(notif_type, Colors.BORDER)

        self._container.setStyleSheet(f"""
            QFrame {{ background: {Colors.BG_MAIN}; border: 1px solid {Colors.BORDER}; border-radius: {Sizes.CARD_RADIUS}px; border-left: 4px solid {border_color}; }}
        """)

        self._icon_label.setText(icon or TYPE_ICON.get(notif_type, "📌"))
        self._title_label.setText(title)
        self._message_label.setText(message)
        self._clear_buttons()

        for btext, action, style in self._buttons_spec:
            btn = QPushButton(btext)
            if style == "primary": btn.setStyleSheet(get_button_style("primary", Fonts.SIZE_XS))
            elif style == "secondary": btn.setStyleSheet(get_button_style("secondary", Fonts.SIZE_XS))
            else: btn.setStyleSheet(get_button_style("text", Fonts.SIZE_XS))
            btn.clicked.connect(lambda checked, a=action: self._on_action(a))
            self._button_layout.addWidget(btn)

        content_height = 80 + (30 if buttons else 0)
        self.setFixedHeight(content_height)
        self._container.setFixedHeight(content_height)

        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.width() - 20; y = 50
        sr = QRect(x + self.width(), y, 0, content_height)
        er = QRect(x, y, self.width(), content_height)
        self.setGeometry(sr); self.show(); self.raise_()
        self._animation.setStartValue(sr); self._animation.setEndValue(er); self._animation.start()
        if duration_ms > 0: self._auto_hide_timer.start(duration_ms)

    def dismiss(self) -> None:
        if self._is_dismissing: return
        self._is_dismissing = True; self._auto_hide_timer.stop()
        geo = self.geometry(); er = QRect(geo.x() + geo.width(), geo.y(), 0, geo.height())
        self._animation.setStartValue(geo); self._animation.setEndValue(er)
        self._animation.finished.connect(self._on_dismiss_finished); self._animation.start()

    def _on_dismiss_finished(self) -> None:
        self.hide(); self._is_dismissing = False
        try: self._animation.finished.disconnect(self._on_dismiss_finished)
        except TypeError: pass
        if self._manager: self._manager._on_notification_closed(self._notification_id)

    def _on_action(self, action: str) -> None:
        self.action_taken.emit(self._notification_id, action); self.dismiss()

    def _clear_buttons(self) -> None:
        for i in reversed(range(self._button_layout.count())):
            w = self._button_layout.itemAt(i).widget()
            if w: w.deleteLater()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == event.KeyPress:
            ke: QKeyEvent = event
            if ke.key() == Qt.Key_Escape:
                for _, action, _ in self._buttons_spec:
                    if action in ("skip", "reject", "snooze"): self._on_action(action); return True
                self.dismiss(); return True
            if ke.key() == Qt.Key_1 and len(self._buttons_spec) >= 1: self._on_action(self._buttons_spec[0][1]); return True
            if ke.key() == Qt.Key_2 and len(self._buttons_spec) >= 2: self._on_action(self._buttons_spec[1][1]); return True
            if ke.key() == Qt.Key_3 and len(self._buttons_spec) >= 3: self._on_action(self._buttons_spec[2][1]); return True
        return super().eventFilter(obj, event)


class NotificationManager:
    def __init__(self):
        self._queue: List[Dict] = []; self._current: Optional[NotificationBubble] = None
        self._shown_ids: set = set(); self._callbacks: Dict[str, Callable] = {}

    def set_notification_bubble(self, bubble: NotificationBubble) -> None:
        self._current = bubble; bubble.action_taken.connect(self._on_action_taken)

    def push(self, notification: Dict) -> None:
        nid = notification["id"]
        if nid in self._shown_ids: return
        priority = notification.get("priority", 0)
        on_action = notification.get("on_action")
        if on_action: self._callbacks[nid] = on_action
        if self._current and self._current.isVisible() and self._current._notification_id:
            current_priority = 0
            for qn in self._queue:
                if qn["id"] == self._current._notification_id: current_priority = qn.get("priority", 0); break
            if priority > current_priority:
                self._current.dismiss(); self._current._notification_id = ""
                self._queue.insert(0, notification); return
        self._queue.append(notification)
        self._queue.sort(key=lambda n: n.get("priority", 0), reverse=True)
        if self._current and not self._current.isVisible(): self._show_next()

    def _show_next(self) -> None:
        if not self._queue or not self._current: return
        n = self._queue.pop(0); self._shown_ids.add(n["id"])
        self._current.show_notification(
            notification_id=n["id"], title=n.get("title",""), message=n.get("message",""),
            icon=n.get("icon",""), notif_type=n.get("notif_type","health"),
            duration_ms=n.get("duration_ms",8000), buttons=n.get("buttons"),
        )

    def _on_action_taken(self, nid: str, action: str) -> None:
        cb = self._callbacks.pop(nid, None)
        if cb:
            try: cb(action)
            except Exception: logger.exception(f"通知回调异常")
        self._show_next()

    def _on_notification_closed(self, nid: str) -> None:
        self._callbacks.pop(nid, None); self._show_next()