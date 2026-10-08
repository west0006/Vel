"""
系统托盘模块。SVG 图标渲染。
"""
import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction

from ui.theme import Colors, Fonts, Styles, load_icon
from utils.logger import get_logger

logger = get_logger(__name__)


class SystemTray(QSystemTrayIcon):
    show_chat = pyqtSignal()
    show_schedule = pyqtSignal()
    toggle_quiet_hour = pyqtSignal()
    toggle_quiet_till_morning = pyqtSignal()
    toggle_pause_all = pyqtSignal(bool)
    show_settings = pyqtSignal()
    show_about = pyqtSignal()
    request_exit = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._quiet_mode = False
        self._pause_all = False
        self._setup_menu()
        self.activated.connect(self._on_activated)
        self._normal_icon = None
        self._dim_icon = None

    def _setup_menu(self) -> None:
        self._menu = QMenu()
        self._menu.setStyleSheet(f"""
            QMenu {{ background:{Colors.BG_MAIN}; border:1px solid {Colors.BORDER};
                     border-radius:{6}px; padding:4px; }}
            QMenu::item {{ padding:6px 20px; font:400 {Fonts.SIZE_SM}px '{Fonts.FAMILY_CUSTOM}', '{Fonts.FAMILY}';
                          color:{Colors.TEXT_PRIMARY}; }}
            QMenu::item:selected {{ background:{Colors.BG_CARD}; }}
            QMenu::separator {{ height:1px; background:{Colors.BORDER}; margin:4px 8px; }}
        """)

        for icon, text, slot in [
            ("chat",     "对话",     self.show_chat.emit),
            ("schedule", "今日日程", self.show_schedule.emit),
        ]:
            a = QAction(load_icon(icon, 16), text, self._menu)
            a.triggered.connect(slot); self._menu.addAction(a)

        self._menu.addSeparator()

        self._pause_action = QAction(load_icon("pause_all", 16), "暂停所有提醒", self._menu)
        self._pause_action.triggered.connect(self._toggle_pause_all_emu)
        self._menu.addAction(self._pause_action)

        self._quiet_h = QAction(load_icon("quiet", 16), "免打扰1小时", self._menu)
        self._quiet_h.triggered.connect(self._toggle_quiet_h)
        self._menu.addAction(self._quiet_h)

        self._quiet_n = QAction(load_icon("quiet", 16), "免打扰至明早", self._menu)
        self._quiet_n.triggered.connect(self._toggle_quiet_n)
        self._menu.addAction(self._quiet_n)

        self._menu.addSeparator()

        for icon, text, slot in [
            ("settings", "设置",     self.show_settings.emit),
            ("about",    "关于",     self.show_about.emit),
        ]:
            a = QAction(load_icon(icon, 16), text, self._menu)
            a.triggered.connect(slot); self._menu.addAction(a)

        self._menu.addSeparator()

        a = QAction(load_icon("exit", 16), "退出", self._menu)
        a.triggered.connect(self.request_exit.emit)
        self._menu.addAction(a)

        self.setContextMenu(self._menu)

    def _on_activated(self, r):
        if r == QSystemTrayIcon.Trigger: self.show_chat.emit()

    def _toggle_quiet_h(self):
        self._quiet_mode = not self._quiet_mode
        self.toggle_quiet_hour.emit()
        self._quiet_h.setText("退出免打扰" if self._quiet_mode else "免打扰1小时")
        self._quiet_n.setVisible(not self._quiet_mode)

    def _toggle_quiet_n(self):
        self._quiet_mode = True
        self.toggle_quiet_till_morning.emit()
        self._quiet_h.setText("退出免打扰")

    def _toggle_pause_all_emu(self):
        self._pause_all = not self._pause_all
        self._pause_action.setText("恢复所有提醒" if self._pause_all else "暂停所有提醒")
        self.toggle_pause_all.emit(self._pause_all)

    def set_quiet_mode(self, e: bool):
        self._quiet_mode = e

    def set_degraded_mode(self, degraded: bool):
        self.setIcon(self._dim_icon if degraded else self._normal_icon)

    def initialize(self):
        """使用自定义猫咪 SVG 图标。"""
        svg_path = os.path.join(os.path.dirname(__file__), "resources", "icons", "vel-cat.svg")

        if os.path.exists(svg_path):
            pix = QPixmap(32, 32)
            pix.fill(Qt.transparent)
            renderer = QSvgRenderer(svg_path)
            p = QPainter(pix)
            renderer.render(p)
            p.end()
            self._normal_icon = QIcon(pix)

            dim = QPixmap(32, 32)
            dim.fill(Qt.transparent)
            p2 = QPainter(dim)
            p2.setOpacity(0.4)
            renderer.render(p2)
            p2.end()
            self._dim_icon = QIcon(dim)
        else:
            # 回退 emoji
            pix = QPixmap(32, 32);
            pix.fill(Qt.transparent)
            p = QPainter(pix);
            p.setFont(QFont("Segoe UI Emoji", 22))
            p.drawText(pix.rect(), Qt.AlignCenter, "🐱");
            p.end()
            self._normal_icon = QIcon(pix)

        self.setIcon(self._normal_icon)
        self.setToolTip(Styles.TRAY_TOOLTIP)
        self.show()
        logger.info("系统托盘已初始化")