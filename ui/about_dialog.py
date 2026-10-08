"""
关于 Vel 对话框模块。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from ui.theme import Colors, Fonts, Sizes, get_button_style
from utils.logger import get_logger

logger = get_logger(__name__)


class AboutDialog(QDialog):
    """关于 Vel 对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_window()
        self._setup_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle("关于 Vel")
        self.setFixedSize(420, 420)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setStyleSheet(f"background-color: {Colors.BG_MAIN};")

        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - 420) // 2,
            (screen.height() - 420) // 2,
        )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 20)
        layout.setSpacing(10)

        # —— 猫咪图标 ——
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(80, 80)
        icon_label.setStyleSheet("background: transparent;")

        import os
        svg_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ui", "resources", "icons", "vel-cat.svg",
        )
        if os.path.exists(svg_path):
            pix = QPixmap(80, 80)
            pix.fill(Qt.transparent)
            renderer = QSvgRenderer(svg_path)
            painter = QPainter(pix)
            renderer.render(painter)
            painter.end()
            icon_label.setPixmap(pix)
        else:
            icon_label.setText("🐱")
            icon_label.setStyleSheet("font-size: 64px; background: transparent;")

        icon_container = QHBoxLayout()
        icon_container.addStretch()
        icon_container.addWidget(icon_label)
        icon_container.addStretch()
        layout.addLayout(icon_container)

        # —— 标题 ——
        title = QLabel("Vel 智能AI桌宠")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"{Fonts.style(Fonts.SIZE_XXL, 600)} "
            f"color: {Colors.ACCENT}; background: transparent;"
        )
        layout.addWidget(title)

        # —— 版本 ——
        version = QLabel("v0.1.0-alpha")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet(
            f"{Fonts.style(Fonts.SIZE_SM, 400)} "
            f"color: {Colors.TEXT_PLACEHOLDER}; background: transparent;"
        )
        layout.addWidget(version)

        # —— 分隔线 ——
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {Colors.BORDER}; max-height: 1px;")
        layout.addWidget(line)

        # —— 说明 ——
        desc = QLabel(
            "一只住在你桌面右下角的猫咪伙伴 🐱\n"
            "陪你聊天、提醒你喝水、帮你记日程\n"
            "所有数据都在你的电脑上，完全本地运行"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"{Fonts.style(Fonts.SIZE_SM, 400)} "
            f"color: {Colors.TEXT_SECONDARY}; background: transparent; line-height: 1.6;"
        )
        layout.addWidget(desc)

        # —— 技术栈 ——
        tech = QLabel(
            "PyQt5 · Ollama · SQLite · FAISS · Faster-Whisper · PaddleOCR"
        )
        tech.setAlignment(Qt.AlignCenter)
        tech.setWordWrap(True)
        tech.setStyleSheet(
            f"{Fonts.style(Fonts.SIZE_XS, 400)} "
            f"color: {Colors.TEXT_PLACEHOLDER}; background: transparent;"
        )
        layout.addWidget(tech)

        layout.addStretch()

        # —— 版权 ——
        copyright_label = QLabel("© 2026 Vel Desktop Pet · 本地运行 · 隐私优先")
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setStyleSheet(
            f"{Fonts.style(Fonts.SIZE_XS, 400)} "
            f"color: {Colors.TEXT_PLACEHOLDER}; background: transparent;"
        )
        layout.addWidget(copyright_label)

        # —— 关闭按钮 ——
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("好的喵~")
        close_btn.setFixedSize(100, 34)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(get_button_style("primary", Fonts.SIZE_SM))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)