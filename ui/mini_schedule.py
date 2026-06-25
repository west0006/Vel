"""
迷你日程悬浮窗口。无边框，从托盘位置弹出。
"""

from datetime import datetime
from typing import List

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QScrollArea, QWidget, QApplication, QSystemTrayIcon
)

from core.service_registry import registry
from ui.theme import Colors, Fonts, Sizes, Styles
from utils.logger import get_logger

logger = get_logger(__name__)


class MiniScheduleWidget(QFrame):
    """今日日程迷你列表。无边框，点击外部自动关闭。"""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(None)
        self._tray = parent if isinstance(parent, QSystemTrayIcon) else None
        self._setup_window()
        self._setup_ui()
        self._setup_outside_close()

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(280, 360)

    def _setup_ui(self) -> None:
        self._container = QFrame()
        self._container.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_MAIN};
                border: 1px solid {Colors.BORDER};
                border-radius: {Sizes.CARD_RADIUS}px;
            }}
        """)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel("今日日程")
        title.setStyleSheet(f"{Fonts.style(Fonts.SIZE_MD, 600)} color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(title)

        self._list = QWidget()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._list_layout.setSpacing(4)
        self._list_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(Styles.SCROLL_AREA)
        scroll.setWidget(self._list)
        layout.addWidget(scroll, stretch=1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

    def _setup_outside_close(self) -> None:
        self._close_timer = QTimer()
        self._close_timer.setInterval(300)
        self._close_timer.timeout.connect(self._check_focus)
        self._close_timer.start()

    def _check_focus(self) -> None:
        if not self.isVisible():
            return
        if not self.underMouse() and not self._container.underMouse():
            self.hide()
            self.closed.emit()

    def refresh(self) -> None:
        """从数据库刷新今日日程。"""
        # 清空
        for i in reversed(range(self._list_layout.count())):
            w = self._list_layout.itemAt(i).widget()
            if w:
                w.deleteLater()

        try:
            db = registry.get("database")
            if db is None:
                self._show_empty()
                return

            today = datetime.now().strftime("%Y-%m-%d")
            cursor = db.execute(
                "SELECT title, start_time, status, priority FROM schedule "
                "WHERE date(start_time) = ? AND status != 'cancelled' "
                "ORDER BY start_time ASC",
                (today,)
            )
            rows = cursor.fetchall()

            if not rows:
                self._show_empty()
                return

            for title, start_time, status, priority in rows:
                time_str = start_time[11:16] if len(start_time) > 10 else "全天"
                icon = {2: "🔴", 1: "🟡", 0: "⚪"}.get(priority, "⚪")
                done = " ✅" if status == "completed" else ""

                item = QLabel(f"{icon} {time_str}  {title}{done}")
                item.setWordWrap(True)
                item.setStyleSheet(f"""
                    background: {Colors.BG_CARD};
                    border-radius: 6px;
                    padding: 8px 10px;
                    {Fonts.style(Fonts.SIZE_SM, 400)}
                    color: {Colors.TEXT_PRIMARY};
                """)
                self._list_layout.addWidget(item)

        except Exception as e:
            logger.warning(f"迷你日程加载失败: {e}")

    def _show_empty(self) -> None:
        empty = QLabel("今天没有日程 🎉")
        empty.setAlignment(Qt.AlignCenter)
        empty.setStyleSheet(f"{Fonts.style(Fonts.SIZE_SM)} color: {Colors.TEXT_PLACEHOLDER}; padding: 20px;")
        self._list_layout.addWidget(empty)

    def show_at_tray(self) -> None:
        self.refresh()
        if self._tray:
            geo = self._tray.geometry()
            x = geo.x() - self.width() // 2
            y = geo.y() - self.height() - 10
        else:
            screen = QApplication.primaryScreen().geometry()
            x = screen.width() - self.width() - 20
            y = screen.height() - self.height() - 80
        self.move(max(0, x), max(0, y))
        self.show()
        self.raise_()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()