"""
对话气泡模块。可拖动标题栏 + 右下角 resize + 内嵌工具栏 + 预置指令。
"""

import random
from datetime import datetime
from typing import List, Optional

from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QRect, QPoint,
    QEasingCurve, pyqtSignal, QObject
)
from PyQt5.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QKeyEvent, QMouseEvent, QCursor
)
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QScrollArea, QWidget, QApplication, QSizeGrip
)

from ui.theme import Colors, Fonts, Sizes, Styles, get_button_style, load_icon
from utils.logger import get_logger

logger = get_logger(__name__)


class ChatBubble(QFrame):
    """对话气泡组件。"""

    MAX_MESSAGES = 50
    SEND_COOLDOWN_MS = 300

    PLACEHOLDERS = [
        "给 Vel 发消息...",
        "试试说「今天天气怎么样」~",
        "贴贴~ 想聊什么？",
        "今天想做什么喵？",
        "你可以说「提醒我喝水」",
        "有什么心事都可以告诉我哦",
        "说「今天日记」生成今日记录~",
    ]

    message_sent = pyqtSignal(str)
    pomodoro_clicked = pyqtSignal()
    memo_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_visible = False
        self._messages: List[dict] = []
        self._last_time_marker: Optional[str] = None
        self._dragging = False
        self._drag_offset = QPoint()
        self._quick_cmds_visible = True
        self._send_cooling = False
        self._is_hiding = False

        self._thinking_dots: List[QLabel] = []
        self._thinking_timer = QTimer()
        self._thinking_timer.timeout.connect(self._tick_thinking)
        self._thinking_step = 0

        self._setup_window()
        self._setup_ui()
        self._setup_animation()
        self._setup_placeholder_timer()

        self._outside_filter = OutsideClickFilter(self)
        QApplication.instance().installEventFilter(self._outside_filter)

    # ------------------------------------------------------------------
    # 窗口与 UI
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setObjectName("chatBubble")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMinimumSize(Sizes.CHAT_BUBBLE_MIN_W, Sizes.CHAT_BUBBLE_MIN_H)
        self.setMaximumSize(Sizes.CHAT_BUBBLE_MAX_W, Sizes.CHAT_BUBBLE_MAX_H)
        self.resize(Sizes.CHAT_BUBBLE_WIDTH, Sizes.CHAT_BUBBLE_HEIGHT)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._container = QFrame()
        self._container.setObjectName("bubbleContainer")
        self._container.setStyleSheet(f"""
            QFrame#bubbleContainer {{
                background-color: {Colors.BG_MAIN};
                border: 1px solid {Colors.BORDER};
                border-radius: {Sizes.PANEL_RADIUS}px;
            }}
        """)
        c_layout = QVBoxLayout(self._container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        # ===== 标题栏 =====
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setCursor(Qt.OpenHandCursor)
        bar.setStyleSheet(
            f"background: {Colors.BG_CARD}; "
            f"border-bottom: 1px solid {Colors.BORDER}; "
            f"border-radius: {Sizes.PANEL_RADIUS}px {Sizes.PANEL_RADIUS}px 0 0;"
        )
        bar.mousePressEvent = self._title_press
        bar.mouseMoveEvent = self._title_move
        bar.mouseReleaseEvent = self._title_release

        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 0, 6, 0)

        icon_lb = QLabel()
        icon_lb.setPixmap(load_icon("chat", 16).pixmap(16, 16))
        icon_lb.setFixedSize(16, 16)
        icon_lb.setStyleSheet("background: transparent;")
        bl.addWidget(icon_lb)

        title = QLabel("与 Vel 聊天")
        title.setStyleSheet(
            f"{Fonts.style(Fonts.CHAT_TITLE, 600)} "
            f"color: {Colors.TEXT_PRIMARY}; background: transparent;"
        )
        bl.addWidget(title)
        bl.addStretch()

        close_btn = QPushButton()
        close_btn.setIcon(load_icon("exit", 14, Colors.TEXT_SECONDARY))
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; } "
            "QPushButton:hover { background: #FAFAFA; border-radius: 14px; }"
        )
        close_btn.clicked.connect(self.hide_bubble)
        bl.addWidget(close_btn)
        c_layout.addWidget(bar)

        # ===== 对话区 =====
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._chat_content = QWidget()
        self._chat_content.setStyleSheet("background: transparent;")
        self._chat_layout = QVBoxLayout(self._chat_content)
        self._chat_layout.setAlignment(Qt.AlignTop)
        self._chat_layout.setSpacing(10)
        self._chat_layout.setContentsMargins(10, 4, 10, 4)
        self._scroll_area.setWidget(self._chat_content)
        c_layout.addWidget(self._scroll_area, stretch=1)

        # ===== 预置指令 =====
        self._quick_cmds = QWidget()
        ql = QVBoxLayout(self._quick_cmds)
        ql.setSpacing(4)
        ql.setContentsMargins(0, 0, 0, 0)

        hdr = QHBoxLayout()
        hdr_label = QLabel("试试这些：")
        hdr_label.setStyleSheet(
            f"{Fonts.style(Fonts.SIZE_XS, 600)} "
            f"color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        hdr.addWidget(hdr_label)
        hdr.addStretch()
        close_cmds = QPushButton()
        close_cmds.setIcon(load_icon("exit", 10, Colors.TEXT_PLACEHOLDER))
        close_cmds.setFixedSize(20, 20)
        close_cmds.setCursor(Qt.PointingHandCursor)
        close_cmds.setStyleSheet("QPushButton { background: transparent; border: none; }")
        close_cmds.clicked.connect(self._hide_quick_cmds)
        hdr.addWidget(close_cmds)
        ql.addLayout(hdr)

        cmds = [
            ("⏰ 提醒我喝水", "提醒我10分钟后喝水"),
            ("🍽 今天吃什么", "今天中午吃什么"),
            ("🔍 搜天气", "今天天气怎么样"),
        ]
        for label, text in cmds:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left; padding: 6px 10px;
                    border: 1px solid {Colors.BORDER}; border-radius: 6px;
                    background: {Colors.BG_CARD};
                    {Fonts.style(Fonts.SIZE_XS)} color: {Colors.ACCENT};
                }}
                QPushButton:hover {{ background: {Colors.NAV_ACTIVE}; }}
            """)
            btn.clicked.connect(lambda checked, t=text: self._quick_fill(t))
            ql.addWidget(btn)

        self._chat_layout.addWidget(self._quick_cmds)

        # ===== 底部区 =====
        bottom = QWidget()
        bottom.setFixedHeight(50)
        bottom.setStyleSheet(
            f"background: {Colors.BG_CARD}; border-top: 1px solid {Colors.BORDER}; "
            f"border-radius: 0 0 {Sizes.PANEL_RADIUS}px {Sizes.PANEL_RADIUS}px;"
        )
        bl2 = QHBoxLayout(bottom)
        bl2.setContentsMargins(8, 0, 8, 0)
        bl2.setSpacing(6)

        pomo_btn = QPushButton()
        pomo_btn.setIcon(load_icon("rest", 16))
        pomo_btn.setToolTip("番茄钟")
        pomo_btn.setFixedSize(30, 30)
        pomo_btn.setCursor(Qt.PointingHandCursor)
        pomo_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; } "
            f"QPushButton:hover {{ background: {Colors.BG_CARD}; border-radius: 6px; }}"
        )
        pomo_btn.clicked.connect(self.pomodoro_clicked.emit)
        bl2.addWidget(pomo_btn)

        memo_btn = QPushButton()
        memo_btn.setIcon(load_icon("memo", 16, Colors.TEXT_SECONDARY))
        memo_btn.setToolTip("备忘录")
        memo_btn.setFixedSize(30, 30)
        memo_btn.setCursor(Qt.PointingHandCursor)
        memo_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; } "
            f"QPushButton:hover {{ background: {Colors.BG_CARD}; border-radius: 6px; }}"
        )
        memo_btn.clicked.connect(self.memo_clicked.emit)
        bl2.addWidget(memo_btn)

        self._input_edit = QTextEdit()
        self._input_edit.setFixedHeight(36)
        self._input_edit.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {Colors.BORDER}; border-radius: 8px;
                padding: 6px 10px;
                font: 400 {Fonts.CHAT_INPUT}px '{Fonts.FAMILY_CUSTOM}', '{Fonts.FAMILY}';
                background: {Colors.BG_MAIN}; color: {Colors.TEXT_PRIMARY};
            }}
            QTextEdit:focus {{ border: 1px solid {Colors.BORDER_FOCUS}; }}
        """)
        self._input_edit.installEventFilter(self)
        self._rotate_placeholder()
        bl2.addWidget(self._input_edit, stretch=1)

        send_btn = QPushButton("发送")
        send_btn.setFixedSize(50, 30)
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.setStyleSheet(get_button_style("primary", Fonts.SIZE_XS))
        send_btn.clicked.connect(self._on_send)
        bl2.addWidget(send_btn)

        c_layout.addWidget(bottom)

        # ===== grip =====
        grip = QSizeGrip(self._container)
        grip.setFixedSize(12, 12)
        grip.setCursor(Qt.SizeFDiagCursor)
        grip.setStyleSheet(
            f"background-color: rgba(255,107,53,40); "
            f"border-radius: 0 0 {Sizes.PANEL_RADIUS - 2}px 0;"
        )
        grip.raise_()
        main_layout.addWidget(self._container)
        self._grip = grip

        # 欢迎消息
        self.add_message("assistant", "喵~你好！我是 Vel，你的桌面小猫咪伙伴 💕")

    def _setup_placeholder_timer(self) -> None:
        """占位符轮换定时器。"""
        self._ph_timer = QTimer()
        self._ph_timer.setInterval(8000)
        self._ph_timer.timeout.connect(self._rotate_placeholder)
        self._ph_timer.start()

    def _rotate_placeholder(self) -> None:
        """随机切换输入框占位符。"""
        text = random.choice(self.PLACEHOLDERS)
        self._input_edit.setPlaceholderText(text)

    def _hide_quick_cmds(self) -> None:
        self._quick_cmds.setVisible(False)
        self._quick_cmds_visible = False

    # ------------------------------------------------------------------
    # 拖拽 & 动画
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, '_grip'):
            self._grip.move(
                self._container.width() - self._grip.width(),
                self._container.height() - self._grip.height(),
            )

    def _title_press(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = e.globalPos() - self.frameGeometry().topLeft()

    def _title_move(self, e: QMouseEvent) -> None:
        if self._dragging:
            self.move(e.globalPos() - self._drag_offset)

    def _title_release(self, e: QMouseEvent) -> None:
        self._dragging = False

    def _setup_animation(self) -> None:
        self._animation = QPropertyAnimation(self, b"geometry")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        ts = 6
        cx, ch = self.width() // 2, self._container.height()
        path = QPainterPath()
        path.moveTo(cx - ts, ch)
        path.lineTo(cx, self.height())
        path.lineTo(cx + ts, ch)
        path.closeSubpath()
        p.fillPath(path, QColor(Colors.BG_MAIN))
        p.setPen(QPen(QColor(Colors.BORDER), 1))
        p.drawLine(cx - ts, ch, cx, self.height())
        p.drawLine(cx + ts, ch, cx, self.height())
        p.end()
        super().paintEvent(event)

    # ------------------------------------------------------------------
    # 显示 / 隐藏
    # ------------------------------------------------------------------

    def show_bubble(self, pet_geometry: Optional[QRect] = None) -> None:
        if self.parent() and isinstance(self.parent(), QWidget):
            pet_geo = self.parent().geometry()
            x = pet_geo.x() + (pet_geo.width() - self.width()) // 2
            y = pet_geo.y() - self.height() + 10
        elif pet_geometry:
            x = pet_geometry.x() + (pet_geometry.width() - self.width()) // 2
            y = pet_geometry.y() - self.height() + 10
        else:
            s = QApplication.primaryScreen().geometry()
            x = (s.width() - self.width()) // 2
            y = (s.height() - self.height()) // 2

        s = QApplication.primaryScreen().geometry()
        x = max(10, min(x, s.width() - self.width() - 10))
        y = max(10, y)

        sr = QRect(x + self.width() // 2, y + self.height() // 2, 0, 0)
        er = QRect(x, y, self.width(), self.height())
        self.setGeometry(sr)
        self.show()
        self.raise_()
        self._is_hiding = False
        self._animation.setStartValue(sr)
        self._animation.setEndValue(er)
        self._animation.start()
        self._is_visible = True
        self._input_edit.setFocus()
        QTimer.singleShot(250, self._outside_filter.on_bubble_shown)

    def hide_bubble(self) -> None:
        if not self._is_visible:
            return
        if self._is_hiding:
            # 正在隐藏中，直接强制完成
            self._animation.stop()
            self._on_hide_finished()
            return
        self._is_hiding = True
        g = self.geometry()
        er = QRect(g.x() + g.width() // 2, g.y() + g.height() // 2, 0, 0)
        self._animation.setStartValue(g)
        self._animation.setEndValue(er)
        self._animation.finished.connect(self._on_hide_finished)
        self._animation.start()

    def _on_hide_finished(self) -> None:
        self.hide()
        self._is_visible = False
        self._is_hiding = False
        try:
            self._animation.finished.disconnect(self._on_hide_finished)
        except TypeError:
            logger.exception("_on_hide_finished 执行失败")

    @property
    def is_bubble_visible(self) -> bool:
        return self._is_visible

    # ------------------------------------------------------------------
    # 消息管理
    # ------------------------------------------------------------------

    def show_context_hint(self, text: str) -> None:
        """显示灰色小字上下文提示。"""
        m = QLabel(f"📎 {text}")
        m.setAlignment(Qt.AlignLeft)
        m.setWordWrap(True)
        m.setMaximumWidth(260)
        m.setStyleSheet(
            f"color: {Colors.TEXT_PLACEHOLDER}; {Fonts.style(Fonts.SIZE_XS, 400)} "
            f"padding: 2px 0; background: transparent; font-style: italic;"
        )
        self._chat_layout.addWidget(m)

    def add_message(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})
        self._maybe_add_time_marker()
        self._chat_layout.addWidget(self._msg_widget(role, content))
        QTimer.singleShot(50, self._scroll_to_bottom)

        # 超出上限时删除最早的消息 widget 和记录
        while len(self._messages) > self.MAX_MESSAGES:
            self._messages.pop(0)
            item = self._chat_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def remove_last_message(self) -> None:
        c = self._chat_layout.count()
        if c > 0:
            i = self._chat_layout.itemAt(c - 1)
            if i and i.widget():
                i.widget().deleteLater()
        if self._messages:
            self._messages.pop()

    def clear_messages(self) -> None:
        self._messages.clear()
        self._last_time_marker = None
        for i in reversed(range(self._chat_layout.count())):
            w = self._chat_layout.itemAt(i).widget()
            if w:
                w.deleteLater()

    def show_thinking(self) -> None:
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setAlignment(Qt.AlignLeft)
        l.setSpacing(4)
        self._thinking_dots.clear()
        for _ in range(3):
            d = QLabel("●")
            d.setFixedSize(12, 12)
            d.setAlignment(Qt.AlignCenter)
            d.setStyleSheet(
                f"color:{Colors.TEXT_PLACEHOLDER}; font-size:9px; background:transparent;"
            )
            self._thinking_dots.append(d)
            l.addWidget(d)
        self._chat_layout.addWidget(w)
        self._thinking_step = 0
        self._thinking_timer.start(400)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def hide_thinking(self) -> None:
        self._thinking_timer.stop()
        for d in self._thinking_dots:
            d.deleteLater()
        self._thinking_dots.clear()
        c = self._chat_layout.count()
        if c > 0:
            i = self._chat_layout.itemAt(c - 1)
            if i and i.widget():
                i.widget().deleteLater()

    # ────────────── 流式输出 ──────────────

    def stream_begin(self) -> None:
        """开始流式：隐藏 think dots，创建空白占位。"""
        self.hide_thinking()
        self._stream_label = QLabel("")
        self._stream_label.setWordWrap(True)
        self._stream_label.setMaximumWidth(260)
        self._stream_label.setStyleSheet(
            f"background: {Colors.BG_CARD}; "
            f"color: {Colors.TEXT_PRIMARY}; border-left: 3px solid #FFD166; "
            f"border-radius: 10px; padding: 10px 14px; "
            f"{Fonts.style(Fonts.CHAT_MSG, 400)}"
        )
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(self._stream_label)
        l.addStretch()
        self._stream_widget = w
        self._chat_layout.addWidget(w)
        QTimer.singleShot(10, self._scroll_to_bottom)

    def stream_append(self, text: str) -> None:
        """流式追加文字。"""
        if not hasattr(self, '_stream_label') or self._stream_label is None:
            self.stream_begin()
        self._stream_label.setText(self._stream_label.text() + text)
        QTimer.singleShot(10, self._scroll_to_bottom)

    def stream_finish(self) -> None:
        """流式结束，固化消息。"""
        if not hasattr(self, '_stream_label') or self._stream_label is None:
            return
        content = self._stream_label.text()
        self._messages.append({"role": "assistant", "content": content})
        self._stream_label = None
        self._stream_widget = None

    def stream_clear(self) -> None:
        """清除流式内容（用于 tool_call 场景）。"""
        if hasattr(self, '_stream_widget') and self._stream_widget:
            self._stream_widget.deleteLater()
            self._stream_widget = None
        self._stream_label = None

    # ──────────────

    def _tick_thinking(self) -> None:
        self._thinking_step = (self._thinking_step + 1) % 3
        for i, d in enumerate(self._thinking_dots):
            c = Colors.ACCENT if i == self._thinking_step else Colors.TEXT_PLACEHOLDER
            d.setStyleSheet(f"color:{c}; font-size:9px; background:transparent;")

    def _msg_widget(self, role: str, content: str) -> QWidget:
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        lb = QLabel(content)
        lb.setWordWrap(True)
        lb.setMaximumWidth(260)
        if role == "user":
            lb.setStyleSheet(
                f"background: {Colors.BG_USER_BUBBLE}; "
                f"color: {Colors.TEXT_SECONDARY}; border-radius: 10px; "
                f"padding: 10px 14px; {Fonts.style(Fonts.CHAT_MSG, 400)}"
            )
            l.addStretch()
            l.addWidget(lb)
        else:
            lb.setStyleSheet(
                f"background: {Colors.BG_CARD}; "
                f"color: {Colors.TEXT_PRIMARY}; border-left: 3px solid #FFD166; "
                f"border-radius: 10px; padding: 10px 14px; "
                f"{Fonts.style(Fonts.CHAT_MSG, 400)}"
            )
            l.addWidget(lb)
            l.addStretch()
        return w

    def _maybe_add_time_marker(self) -> None:
        now = datetime.now().strftime("%H:%M")
        if self._last_time_marker == now:
            return
        self._last_time_marker = now
        m = QLabel(f"— {now} —")
        m.setAlignment(Qt.AlignCenter)
        m.setStyleSheet(
            f"color:{Colors.TEXT_PLACEHOLDER}; "
            f"{Fonts.style(Fonts.SIZE_XS, 400)} padding:4px 0; background:transparent;"
        )
        self._chat_layout.addWidget(m)

    def _scroll_to_bottom(self) -> None:
        self._scroll_area.verticalScrollBar().setValue(
            self._scroll_area.verticalScrollBar().maximum()
        )

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        if self._send_cooling:
            return
        t = self._input_edit.toPlainText().strip()
        if not t:
            return
        self._input_edit.clear()
        self.add_message("user", t)
        self.message_sent.emit(t)

        # 发送冷却
        self._send_cooling = True
        QTimer.singleShot(self.SEND_COOLDOWN_MS, self._reset_cooling)

    def _reset_cooling(self) -> None:
        self._send_cooling = False

    def _quick_fill(self, text: str) -> None:
        self._input_edit.setText(text)
        self._on_send()

    # ------------------------------------------------------------------
    # 事件过滤
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj == self._input_edit and event.type() == event.KeyPress:
            ke: QKeyEvent = event
            if ke.key() == Qt.Key_Return:
                if ke.modifiers() & Qt.ShiftModifier:
                    return False
                self._on_send()
                return True
            if ke.key() == Qt.Key_Escape:
                self.hide_bubble()
                return True
        return super().eventFilter(obj, event)


class OutsideClickFilter(QObject):
    def __init__(self, bubble: ChatBubble):
        super().__init__()
        self._bubble = bubble
        self._active = False

    def on_bubble_shown(self) -> None:
        self._active = True

    def eventFilter(self, obj, event) -> bool:
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.MouseButtonPress:
            if self._active and self._bubble.is_bubble_visible:
                if not self._bubble.geometry().contains(event.globalPos()):
                    self._active = False
                    self._bubble.hide_bubble()
        return False
