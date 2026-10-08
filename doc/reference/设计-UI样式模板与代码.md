## 全场景模板代码文件（第一部分）

以下输出项目核心 UI 模块的完整代码，基于前文所有设计规范。

---

### 1. 主样式表：`ui/resources/styles.qss`

```css
/* =============================================
   智能AI桌宠 — 扁平圆润极简线条样式表
   暖橙 #FF6B35 / 背景 #FFFBF5 / 卡片 #FAFAFA
   字体：猫啃什锦 (标题) / 微软雅黑 (正文)
   圆角：6~16px，阴影极少量
   ============================================= */

/* ----- 全局默认 ----- */
QWidget {
    background: #FFFBF5;
    color: #2C2C2C;
    font-family: "Microsoft YaHei";
    font-weight: normal;
    font-size: 13px;
}

/* ----- 无边框圆角窗口容器 ----- */
QWidget#roundedWindow {
    background: #FFFBF5;
    border: 1px solid #E8E4E0;
    border-radius: 16px;
}

/* ----- 内部标题栏 ----- */
QWidget#titleBar {
    background: #FAFAFA;
    border-bottom: 1px solid #E8E4E0;
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
    padding: 8px 16px;
}
QLabel#windowTitle {
    color: #2C2C2C;
    font-family: "猫啃什锦", "Microsoft YaHei";
    font-weight: bold;
    font-size: 15px;
}

/* ----- 卡片（设置面板分组、健康看板等） ----- */
QFrame#card {
    background: #FFFFFF;
    border: 1px solid #E8E4E0;
    border-radius: 12px;
    padding: 16px;
}

/* ----- 次级卡片（列表行、嵌入式区块） ----- */
QFrame#subCard {
    background: #FAFAFA;
    border: 1px solid #E8E4E0;
    border-radius: 10px;
    padding: 12px;
}

/* ----- 文字层级 ----- */
QLabel#h1 {
    font-family: "猫啃什锦", "Microsoft YaHei";
    font-weight: bold;
    font-size: 18px;
    color: #2C2C2C;
}
QLabel#h2 {
    font-family: "猫啃什锦", "Microsoft YaHei";
    font-weight: bold;
    font-size: 15px;
    color: #2C2C2C;
}
QLabel#body {
    font-weight: normal;
    font-size: 13px;
    color: #4A4A4A;
}
QLabel#caption {
    font-weight: normal;
    font-size: 11px;
    color: #8A8A8A;
}

/* ----- 输入框 ----- */
QLineEdit, QTextEdit, QPlainTextEdit {
    background: #FFFFFF;
    border: 1px solid #E8E4E0;
    border-radius: 8px;
    padding: 6px 10px;
    color: #2C2C2C;
    font-weight: normal;
    font-size: 13px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #FF6B35;
}

/* ----- 主要按钮（暖橙实心） ----- */
QPushButton#primaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #FF7D4D, stop:1 #FF6B35);
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton#primaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #E55A2B, stop:1 #E55A2B);
}
QPushButton#primaryBtn:pressed {
    background: #CC4F20;
}
QPushButton#primaryBtn:disabled {
    background: #F0EDEA;
    color: #8A8A8A;
}

/* ----- 次要按钮（线框） ----- */
QPushButton#secondaryBtn {
    background: transparent;
    border: 1px solid #FF6B35;
    border-radius: 8px;
    padding: 6px 16px;
    color: #FF6B35;
    font-weight: bold;
    font-size: 13px;
}
QPushButton#secondaryBtn:hover {
    background: #FFF2ED;
}
QPushButton#secondaryBtn:pressed {
    background: #FFE8DC;
}
QPushButton#secondaryBtn:disabled {
    border-color: #C4BFBA;
    color: #C4BFBA;
}

/* ----- 文字按钮 ----- */
QPushButton#textBtn {
    background: transparent;
    border: none;
    color: #FF6B35;
    font-weight: bold;
    font-size: 13px;
    padding: 4px 8px;
}
QPushButton#textBtn:hover {
    color: #E55A2B;
}
QPushButton#textBtn:disabled {
    color: #C4BFBA;
}

/* ----- 列表控件 ----- */
QListWidget, QTableWidget, QTreeWidget {
    background: #FAFAFA;
    border: 1px solid #E8E4E0;
    border-radius: 12px;
    outline: none;
    font-weight: normal;
}
QListWidget::item, QTableWidget::item, QTreeWidget::item {
    padding: 8px 12px;
    color: #4A4A4A;
    background: transparent;
}
QListWidget::item:selected, QTableWidget::item:selected, QTreeWidget::item:selected {
    background: #FFF2ED;
    color: #2C2C2C;
}
QHeaderView::section {
    background: #FFFBF5;
    color: #2C2C2C;
    font-weight: bold;
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid #E8E4E0;
}

/* ----- 滚动条 ----- */
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #E0DCD8;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #C4BFBA;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 6px;
}
QScrollBar::handle:horizontal {
    background: #E0DCD8;
    border-radius: 3px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #C4BFBA;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ----- 复选框 / 单选框 ----- */
QCheckBox, QRadioButton {
    spacing: 8px;
    font-weight: normal;
    color: #4A4A4A;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #E8E4E0;
    border-radius: 4px;
    background: #FFFFFF;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: #FF6B35;
    border: 1px solid #FF6B35;
}
QRadioButton::indicator {
    border-radius: 9px;
}

/* ----- 滑块 ----- */
QSlider::groove:horizontal {
    height: 6px;
    background: #E8E4E0;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -5px 0;
    background: #FF6B35;
    border-radius: 8px;
    border: none;
}
QSlider::handle:horizontal:hover {
    background: #E55A2B;
}

/* ----- 进度条 ----- */
QProgressBar {
    border: 1px solid #E8E4E0;
    border-radius: 8px;
    text-align: center;
    background: #FAFAFA;
    font-weight: bold;
    color: #4A4A4A;
}
QProgressBar::chunk {
    background: #FF6B35;
    border-radius: 6px;
}

/* ----- 工具提示 ----- */
QToolTip {
    background: #2C2C2C;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    color: #FFFFFF;
    font-weight: normal;
    font-size: 12px;
}

/* ----- 菜单 ----- */
QMenu {
    background: #FFFFFF;
    border: 1px solid #E8E4E0;
    border-radius: 12px;
    padding: 4px 0;
}
QMenu::item {
    padding: 8px 24px;
    color: #4A4A4A;
    font-weight: normal;
}
QMenu::item:selected {
    background: #FFF2ED;
    color: #2C2C2C;
}
QMenu::separator {
    height: 1px;
    background: #E8E4E0;
    margin: 4px 12px;
}

/* ----- 日历控件 ----- */
QCalendarWidget {
    background: #FFFFFF;
    border: 1px solid #E8E4E0;
    border-radius: 12px;
}
QCalendarWidget QToolButton {
    color: #2C2C2C;
    font-weight: bold;
    border: none;
    padding: 6px;
}
```

---

### 2. 圆角无边框窗口基类：`ui/rounded_window.py`

```python
"""
圆角无边框窗口基类
所有设置面板、弹窗均应继承此类
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QPainter, QBrush, QColor, QPen, QMouseEvent


class RoundedWindow(QWidget):
    """带自定义标题栏的圆角窗口"""

    def __init__(self, parent=None, title: str = ""):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._drag_pos = None

        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(2, 2, 2, 2)

        # 标题栏
        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(36)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(12, 0, 8, 0)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("windowTitle")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("textBtn")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.clicked.connect(self.close)
        title_layout.addWidget(self.close_btn)

        self.main_layout.addWidget(self.title_bar)

        # 内容区域
        self.content_widget = QWidget()
        self.main_layout.addWidget(self.content_widget)

    def set_title(self, title: str):
        self.title_label.setText(title)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # 圆角白色背景
        painter.setBrush(QBrush(QColor("#FFFBF5")))
        painter.setPen(QPen(QColor("#E8E4E0"), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 16, 16)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self.title_bar.geometry().contains(event.pos()):
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
```

---

## 全场景模板代码文件（第二部分）

### 3. 对话气泡：`ui/chat_bubble.py`

```python
"""
对话气泡组件
极简温暖风格，像素猫头顶弹出
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QScrollArea
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt5.QtGui import QFont
from core.event_bus import bus


class ChatBubble(QWidget):
    """猫头顶对话气泡"""

    message_sent = pyqtSignal(str)

    def __init__(self, pet, model: str = "qwen2.5:7b-instruct-q4_K_M"):
        super().__init__()
        self.pet = pet
        self.model = model

        # 窗口设置
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName("chatBubble")
        self.setStyleSheet("""
            QWidget#chatBubble {
                background: #FFFFFF;
                border: 1px solid #E8E4E0;
                border-radius: 16px;
            }
        """)
        self.resize(360, 380)

        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 消息区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("chatScroll")
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QWidget#chatContent { background: transparent; }
        """)

        self.chat_content = QWidget()
        self.chat_content.setObjectName("chatContent")
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setContentsMargins(12, 12, 12, 4)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch()
        self.scroll_area.setWidget(self.chat_content)
        self.main_layout.addWidget(self.scroll_area)

        # 工具栏
        self.toolbar = QWidget()
        self.toolbar.setFixedHeight(36)
        self.toolbar.setStyleSheet("background: #FAFAFA; border-top: 1px solid #E8E4E0;")
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(12, 0, 12, 0)

        self.pomodoro_btn = QPushButton("🍅")
        self.pomodoro_btn.setObjectName("textBtn")
        self.pomodoro_btn.setToolTip("番茄钟")
        self.memo_btn = QPushButton("📋")
        self.memo_btn.setObjectName("textBtn")
        self.memo_btn.setToolTip("备忘录")
        toolbar_layout.addWidget(self.pomodoro_btn)
        toolbar_layout.addWidget(self.memo_btn)
        toolbar_layout.addStretch()
        self.main_layout.addWidget(self.toolbar)

        # 输入区域
        self.input_area = QWidget()
        self.input_area.setFixedHeight(44)
        self.input_area.setStyleSheet("background: #FAFAFA; border-top: 1px solid #E8E4E0;")
        input_layout = QHBoxLayout(self.input_area)
        input_layout.setContentsMargins(12, 4, 8, 4)

        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("想喝杯水吗？")
        self.input_line.setObjectName("chatInput")
        self.input_line.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_line)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primaryBtn")
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)

        self.main_layout.addWidget(self.input_area)

        # 对话历史
        self.history = []

        # 位置
        self.hide()

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self._position_above_pet()
            self.input_line.setFocus()
            self._animate_show()

    def _position_above_pet(self):
        pet_geo = self.pet.geometry()
        screen = self.pet.screen().availableGeometry()
        x = pet_geo.center().x() - self.width() // 2
        y = pet_geo.top() - self.height() - 12
        # 边界检测
        if x < screen.left():
            x = screen.left() + 8
        elif x + self.width() > screen.right():
            x = screen.right() - self.width() - 8
        if y < screen.top():
            y = pet_geo.bottom() + 12
        self.move(x, y)

    def _animate_show(self):
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(200)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.start()

    def send_message(self):
        text = self.input_line.text().strip()
        if not text:
            return
        self.input_line.clear()
        self.add_message("user", text)
        self.message_sent.emit(text)

    def add_message(self, role: str, content: str):
        """添加消息到聊天历史"""
        bubble = QLabel()
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(260)
        bubble.setFont(QFont("Microsoft YaHei", 10))

        if role == "user":
            bubble.setStyleSheet("""
                background: #F5F2EF;
                border-right: 3px solid #FF6B35;
                border-radius: 10px 2px 10px 10px;
                padding: 8px 10px;
                color: #4A4A4A;
            """)
            bubble.setAlignment(Qt.AlignLeft)
            container_layout = QHBoxLayout()
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.addStretch()
            container_layout.addWidget(bubble)
        else:
            bubble.setStyleSheet("""
                background: #FAFAFA;
                border-left: 3px solid #FFD166;
                border-radius: 2px 10px 10px 10px;
                padding: 8px 10px;
                color: #2C2C2C;
            """)
            bubble.setAlignment(Qt.AlignLeft)
            container_layout = QHBoxLayout()
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.addWidget(bubble)
            container_layout.addStretch()

        bubble.setText(content)

        container = QWidget()
        container.setLayout(container_layout)

        # 插入到stretch之前
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, container)

        # 自动滚动到底部
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        self.hide()
        event.ignore()
```

---

### 4. 通知气泡：`ui/notification_bubble.py`

```python
"""
通知气泡组件
按类型左边框颜色，支持多按钮操作
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt5.QtGui import QFont


class NotificationBubble(QWidget):
    """弹出式通知气泡"""

    action_triggered = pyqtSignal(str, str)  # action_id, notification_id

    TYPE_STYLES = {
        "schedule": "#FF6B35",
        "health": "#6B9E7A",
        "greeting": "#FFD166",
        "warning": "#D98C7A",
        "memo": "#5A5A5A",
        "habit": "#FF6B35",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("""
            QWidget#notifyContainer {
                background: #FFFFFF;
                border: 1px solid #E8E4E0;
                border-radius: 12px;
            }
        """)
        self.setObjectName("notifyContainer")
        self.resize(320, 130)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 内部容器（用于左边框颜色）
        self.inner = QWidget()
        self.inner.setObjectName("notifyInner")
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(12, 12, 12, 12)
        self.inner_layout.setSpacing(6)

        # 标题行
        title_row = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        title_row.addWidget(self.icon_label)

        self.title_label = QLabel()
        self.title_label.setObjectName("h2")
        title_row.addWidget(self.title_label)
        title_row.addStretch()

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("textBtn")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self._on_close)
        title_row.addWidget(self.close_btn)
        self.inner_layout.addLayout(title_row)

        # 正文
        self.body_label = QLabel()
        self.body_label.setObjectName("body")
        self.body_label.setWordWrap(True)
        self.inner_layout.addWidget(self.body_label)

        # 按钮组
        self.btn_layout = QHBoxLayout()
        self.btn_layout.addStretch()
        self.inner_layout.addLayout(self.btn_layout)

        self.main_layout.addWidget(self.inner)

        self.notification_id = ""
        self._current_type = ""
        self.hide()

    def show_notification(self, notif_id: str, notif_type: str,
                         title: str, body: str,
                         actions: list = None,
                         duration_ms: int = 0):
        """
        显示通知
        actions: [{"id": "done", "text": "已完成", "primary": True}, ...]
        """
        self.notification_id = notif_id
        self._current_type = notif_type
        border_color = self.TYPE_STYLES.get(notif_type, "#E8E4E0")

        # 应用左边框颜色
        self.inner.setStyleSheet(f"""
            QWidget#notifyInner {{
                background: #FFFFFF;
                border-left: 4px solid {border_color};
                border-radius: 8px;
                border-top: none;
                border-right: none;
                border-bottom: none;
            }}
        """)

        self.title_label.setText(title)
        self.body_label.setText(body)

        # 图标根据类型
        icons = {
            "schedule": "🔔", "health": "💧", "greeting": "☀️",
            "warning": "⚠️", "memo": "📋", "habit": "🏆"
        }
        self.icon_label.setText(icons.get(notif_type, "📌"))

        # 清空旧按钮
        for i in reversed(range(self.btn_layout.count())):
            widget = self.btn_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # 添加操作按钮
        if actions:
            for action in actions:
                btn = QPushButton(action["text"])
                if action.get("primary"):
                    btn.setObjectName("primaryBtn")
                else:
                    btn.setObjectName("secondaryBtn")
                btn.clicked.connect(lambda _, aid=action["id"]: self._on_action(aid))
                self.btn_layout.addWidget(btn)

        self.show()
        self._animate_show()

        # 自动消失
        if duration_ms > 0:
            QTimer.singleShot(duration_ms, self._on_close)

    def _animate_show(self):
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(200)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.start()

    def _on_action(self, action_id: str):
        self.action_triggered.emit(action_id, self.notification_id)
        self.hide()

    def _on_close(self):
        self.action_triggered.emit("ignore", self.notification_id)
        self.hide()
```

---

## 全场景模板代码文件（第三部分）

### 5. 设置面板框架：`ui/settings_window.py`

```python
"""
设置面板 — 左侧导航 + 右侧内容区
基于圆角无边框窗口基类
"""
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
    QListWidgetItem, QStackedWidget, QLabel, QScrollArea
)
from PyQt5.QtCore import Qt
from ui.rounded_window import RoundedWindow


class SettingsWindow(RoundedWindow):
    """主设置窗口"""

    def __init__(self, parent=None):
        super().__init__(parent, title="设置")
        self.resize(700, 500)
        self.setMinimumSize(600, 420)

        # 内容区水平布局：导航 + 页面栈
        content_layout = QHBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # --- 左侧导航 ---
        nav_widget = QWidget()
        nav_widget.setFixedWidth(180)
        nav_widget.setStyleSheet("background: #FAFAFA; border-right: 1px solid #E8E4E0;")
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navList")
        self.nav_list.setStyleSheet("""
            QListWidget#navList {
                background: transparent;
                border: none;
                font-size: 14px;
            }
            QListWidget#navList::item {
                padding: 10px 16px;
                color: #4A4A4A;
                background: transparent;
                border: none;
            }
            QListWidget#navList::item:selected {
                color: #FF6B35;
                background: #FFF2ED;
            }
            QListWidget#navList::item:hover:!selected {
                background: #F5F2EF;
            }
        """)
        self.nav_items = [
            ("📝 习惯", "habit"),
            ("📅 日程", "schedule"),
            ("❤️ 健康", "health"),
            ("💬 对话", "chat"),
            ("🎨 外观", "appearance"),
            ("🔄 更新", "update"),
            ("📊 数据", "data"),
        ]
        for text, key in self.nav_items:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, key)
            self.nav_list.addItem(item)

        self.nav_list.currentRowChanged.connect(self._on_nav_change)
        nav_layout.addWidget(self.nav_list)
        content_layout.addWidget(nav_widget)

        # --- 右侧页面栈 ---
        self.page_stack = QStackedWidget()
        self.page_stack.setStyleSheet("background: #FFFBF5;")

        # 创建各占位页面
        for _, key in self.nav_items:
            page = self._create_placeholder_page(key)
            self.page_stack.addWidget(page)

        content_layout.addWidget(self.page_stack)

        # 默认选中第一项
        self.nav_list.setCurrentRow(0)

    def _create_placeholder_page(self, key: str) -> QWidget:
        """创建占位页面，后续可替换为真实内容"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        title_label = QLabel(self._get_page_title(key))
        title_label.setObjectName("h1")
        layout.addWidget(title_label)

        # 内容区域（滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
        """)
        content = QWidget()
        content.setObjectName("pageContent")
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 16, 0, 0)
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        return page

    def _get_page_title(self, key: str) -> str:
        titles = {
            "habit": "习惯孵化",
            "schedule": "日程管理",
            "health": "健康设置",
            "chat": "对话记录",
            "appearance": "外观与养成",
            "update": "更新与版本",
            "data": "数据管理",
        }
        return titles.get(key, key)

    def _on_nav_change(self, index: int):
        self.page_stack.setCurrentIndex(index)
```

---

### 6. 养成商店组件：`ui/unlock_shop.py`

```python
"""
养成商店 — 猫粮点数展示 + 物品网格
用于设置面板 "外观" 页
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGridLayout, QPushButton, QDialog, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont


class UnlockShop(QWidget):
    """养成商店组件"""

    item_purchased = pyqtSignal(str)  # item_id
    item_equipped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.unlockables = []  # 物品列表，由外部设置
        self.cat_food = 0
        self.equipped_ids = set()

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)

        # 猫粮余额
        food_row = QHBoxLayout()
        self.food_icon = QLabel("🍪")
        self.food_icon.setFont(QFont("Segoe UI Emoji", 14))
        food_row.addWidget(self.food_icon)

        self.food_label = QLabel("猫粮：0")
        self.food_label.setObjectName("h2")
        food_row.addWidget(self.food_label)
        food_row.addStretch()
        main_layout.addLayout(food_row)

        # 标签页切换
        tab_row = QHBoxLayout()
        self.tab_accessory = QPushButton("配饰")
        self.tab_accessory.setObjectName("secondaryBtn" if False else "primaryBtn")
        self.tab_accessory.clicked.connect(lambda: self._show_category("accessory"))
        self.tab_color = QPushButton("毛色")
        self.tab_color.setObjectName("secondaryBtn")
        self.tab_color.clicked.connect(lambda: self._show_category("color"))
        tab_row.addWidget(self.tab_accessory)
        tab_row.addWidget(self.tab_color)
        tab_row.addStretch()
        main_layout.addLayout(tab_row)

        # 物品网格
        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        main_layout.addWidget(self.grid_widget)

        self.current_category = "accessory"
        self._refresh_grid()

    def set_data(self, unlockables: list, cat_food: int, equipped_ids: set):
        """外部更新数据"""
        self.unlockables = unlockables
        self.cat_food = cat_food
        self.equipped_ids = equipped_ids
        self.food_label.setText(f"猫粮：{cat_food}")
        self._refresh_grid()

    def _show_category(self, category: str):
        self.current_category = category
        # 更新标签按钮样式
        if category == "accessory":
            self.tab_accessory.setObjectName("primaryBtn")
            self.tab_color.setObjectName("secondaryBtn")
        else:
            self.tab_color.setObjectName("primaryBtn")
            self.tab_accessory.setObjectName("secondaryBtn")
        # 刷新样式
        self.tab_accessory.style().unpolish(self.tab_accessory)
        self.tab_accessory.style().polish(self.tab_accessory)
        self.tab_color.style().unpolish(self.tab_color)
        self.tab_color.style().polish(self.tab_color)
        self._refresh_grid()

    def _refresh_grid(self):
        # 清空网格
        for i in reversed(range(self.grid.count())):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        items = [u for u in self.unlockables if u.get("type") == self.current_category]
        cols = 4
        for idx, item in enumerate(items):
            card = self._create_item_card(item)
            row = idx // cols
            col = idx % cols
            self.grid.addWidget(card, row, col)

    def _create_item_card(self, item: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setFixedSize(140, 160)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(6)
        card_layout.setAlignment(Qt.AlignCenter)

        # 物品图标
        icon_label = QLabel(item.get("icon", "🎁"))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFont(QFont("Segoe UI Emoji", 28))
        icon_label.setStyleSheet("background: transparent; border: none;")
        card_layout.addWidget(icon_label)

        # 名称
        name_label = QLabel(item.get("name", "???"))
        name_label.setObjectName("body")
        name_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(name_label)

        unlocked = item.get("unlocked", False)
        equipped = item.get("id") in self.equipped_ids

        if unlocked:
            if equipped:
                status_btn = QPushButton("已装备")
                status_btn.setObjectName("primaryBtn")
                status_btn.setEnabled(False)
            else:
                status_btn = QPushButton("装备")
                status_btn.setObjectName("secondaryBtn")
                status_btn.clicked.connect(lambda: self.item_equipped.emit(item["id"]))
        else:
            price = item.get("price", 10)
            status_btn = QPushButton(f"解锁 {price}🍪")
            if self.cat_food >= price:
                status_btn.setObjectName("primaryBtn")
                status_btn.clicked.connect(lambda: self.item_purchased.emit(item["id"]))
            else:
                status_btn.setObjectName("secondaryBtn")
                status_btn.setEnabled(False)
            status_btn.setToolTip(f"花费 {price} 猫粮解锁")
        card_layout.addWidget(status_btn)

        return card
```

---

## 全场景模板代码文件（第四部分）

### 7. 通知管理器：`ui/notification_manager.py`

```python
"""
通知管理器 — 多提醒优先级队列，与猫咪动画联动
"""
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass(order=True)
class NotificationItem:
    priority: int          # 0最高(到期提醒) 1(预警) 2(健康)
    notif_id: str = field(compare=False)
    notif_type: str = field(compare=False)
    title: str = field(compare=False)
    body: str = field(compare=False)
    actions: list = field(compare=False, default_factory=list)
    on_action: Optional[Callable] = field(compare=False, default=None)


class NotificationManager(QObject):
    """通知队列管理器"""

    request_show = pyqtSignal(dict)   # 请求显示通知
    request_hide = pyqtSignal()       # 请求隐藏当前通知

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = deque()
        self._current = None
        self._lock_timer = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._unlock)
        self._locked = False

    def push(self, item: NotificationItem):
        """添加通知到队列"""
        self._queue.append(item)
        if not self._locked and not self._current:
            self._show_next()

    def _show_next(self):
        if not self._queue or self._locked:
            return
        # 排序取最高优先级
        sorted_items = sorted(self._queue, key=lambda x: x.priority)
        next_item = sorted_items[0]
        self._queue.remove(next_item)
        self._current = next_item
        self.request_show.emit({
            "notif_id": next_item.notif_id,
            "type": next_item.notif_type,
            "title": next_item.title,
            "body": next_item.body,
            "actions": next_item.actions,
        })
        # 锁定一段时间防止快速切换
        self._locked = True
        self._lock_timer.start(3000)  # 3秒后才能显示下一个

    def handle_action(self, action_id: str):
        """用户操作反馈"""
        if self._current:
            if self._current.on_action:
                self._current.on_action(action_id, self._current.notif_id)
            self._current = None
            self._unlock()
            self._show_next()

    def _unlock(self):
        self._locked = False
        if self._queue:
            self._show_next()
        else:
            self.request_hide.emit()

    def clear_all(self):
        self._queue.clear()
        self._current = None
        self._locked = False
        self._lock_timer.stop()
        self.request_hide.emit()
```

---

### 8. 空状态组件：`ui/empty_state.py`

```python
"""
空状态组件 — 无数据时的温暖引导
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt


class EmptyState(QWidget):
    """空状态提示"""

    def __init__(self, icon: str = "🐱", title: str = "还没有内容",
                 desc: str = "试试创建一个吧~", action_text: str = "",
                 on_action=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        self.icon_label = QLabel(icon)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        layout.addWidget(self.icon_label)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("h2")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("caption")
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        if action_text and on_action:
            btn = QPushButton(action_text)
            btn.setObjectName("primaryBtn")
            btn.clicked.connect(on_action)
            layout.addWidget(btn, alignment=Qt.AlignCenter)
```

---

### 9. 主程序整合：`main.py`（更新版）

```python
"""
智能AI桌宠主入口
整合所有组件、加载样式表、启动事件总线
"""
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QFile, QTextStream
from PyQt5.QtGui import QFont

from core.event_bus import bus
from ui.floating_pet import FloatingPet
from ui.chat_bubble import ChatBubble
from ui.notification_bubble import NotificationBubble
from ui.notification_manager import NotificationManager, NotificationItem
from ui.settings_window import SettingsWindow


def load_stylesheet(app: QApplication):
    """加载全局样式表"""
    style_file = QFile("ui/resources/styles.qss")
    if style_file.open(QFile.ReadOnly | QFile.Text):
        stream = QTextStream(style_file)
        app.setStyleSheet(stream.readAll())
        style_file.close()
    else:
        # 最小回退样式
        app.setStyleSheet("""
            QWidget {
                font-family: "Microsoft YaHei";
                font-weight: normal;
                background: #FFFBF5;
                color: #2C2C2C;
            }
        """)

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 加载样式
    load_stylesheet(app)

    # 初始化核心组件
    pet = FloatingPet()
    pet.show()

    chat_bubble = ChatBubble(pet)
    pet.chat_bubble = chat_bubble

    notif_bubble = NotificationBubble()
    notif_manager = NotificationManager()

    # 通知管理器与气泡绑定
    def show_notif(data: dict):
        notif_bubble.show_notification(
            data["notif_id"], data["type"],
            data["title"], data["body"],
            data.get("actions", []),
            duration_ms=0
        )

    def hide_notif():
        notif_bubble.hide()

    notif_manager.request_show.connect(show_notif)
    notif_manager.request_hide.connect(hide_notif)
    notif_bubble.action_triggered.connect(notif_manager.handle_action)

    # 示例：事件总线订阅——日程提醒时创建通知
    def on_schedule_alert(data: dict):
        item = NotificationItem(
            priority=0,
            notif_id=data.get("id", ""),
            notif_type="schedule",
            title="日程提醒",
            body=data.get("title", ""),
            actions=[
                {"id": "done", "text": "已完成", "primary": True},
                {"id": "snooze", "text": "推迟5分钟", "primary": False},
                {"id": "ignore", "text": "忽略", "primary": False},
            ],
            on_action=lambda aid, nid: print(f"Action {aid} for {nid}")
        )
        notif_manager.push(item)

    bus.subscribe_ui("SCHEDULE_ALERT", "schedule_alert", on_schedule_alert)

    # 设置窗口（延迟创建）
    settings_window = None
    def open_settings():
        nonlocal settings_window
        if settings_window is None:
            settings_window = SettingsWindow()
        settings_window.show()
        settings_window.raise_()

    # 绑定托盘菜单动作示例（需在 FloatingPet 中设置）
    # 此处由 FloatingPet 内部调用 open_settings

    # 启动事件循环
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
```

---

