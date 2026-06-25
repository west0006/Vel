"""
悬浮窗桌宠模块。SVG 帧动画驱动。
帧目录: ui/resources/animations/pet_svg/
"""

import os
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap, QMouseEvent, QCursor
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QWidget, QLabel, QApplication

from utils.logger import get_logger

logger = get_logger(__name__)

FRAME_DIR = os.path.join(os.path.dirname(__file__), "resources", "animations", "pet_svg")


def _load_frames(state: str) -> list:
    """加载某状态的全部 SVG 帧，预渲染为 QPixmap 列表。"""
    folder = os.path.join(FRAME_DIR, state)
    if not os.path.isdir(folder):
        return []
    files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".svg")],
        key=lambda x: int(x.split("_")[-1].replace(".svg", ""))
    )
    frames = []
    for fname in files:
        path = os.path.join(folder, fname)
        try:
            renderer = QSvgRenderer(path)
            pix = QPixmap(256, 256)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing, False)
            renderer.render(p)
            p.end()
            frames.append(pix)
        except Exception as e:
            logger.warning(f"加载帧失败: {path} -> {e}")
    if frames:
        logger.info(f"加载 [{state}] {len(frames)} 帧")
    return frames


class FloatingPet(QWidget):
    clicked = pyqtSignal()
    drag_finished = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._display_size = 256
        self._emotion = "idle"
        self._frame_idx = 0
        self._loop = True
        self._after = "idle"

        self._frames_cache = {}
        for state in ("idle", "wake", "thinking", "sleep",
                       "sad", "happy", "alert", "collapsed"):
            frames = _load_frames(state)
            if frames:
                self._frames_cache[state] = frames

        if "idle" not in self._frames_cache:
            logger.error("idle 帧未加载，UI 将不显示")

        self._setup_window()
        self._setup_ui()
        self._setup_drag()
        self._setup_edge_hide()
        self._setup_animation()

        self._tip_label = QLabel(self)
        self._tip_label.setAlignment(Qt.AlignCenter)
        self._tip_label.setStyleSheet("""
            background-color: rgba(30,30,30,180); color: white;
            border-radius: 8px; padding: 4px 10px;
            font: 600 12px 'Microsoft YaHei UI';
        """)
        self._tip_label.hide()

    def _setup_window(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self._display_size, self._display_size)
        s = QApplication.primaryScreen().geometry()
        self.move(s.width() - self._display_size - 50, s.height() - self._display_size - 100)

    def _setup_ui(self) -> None:
        pass

    def _setup_drag(self) -> None:
        self._dragging = False
        self._drag_position = QPoint()
        self._drag_start_pos = QPoint()
        self._click_threshold = 5

    def _setup_edge_hide(self) -> None:
        self._edge_timer = QTimer()
        self._edge_timer.setInterval(400)
        self._edge_timer.timeout.connect(self._check_edge)
        self._edge_timer.start()
        self._is_hidden = False
        self._hidden_edge = None
        self._normal_geometry = self.geometry()
        self._edge_anim = QPropertyAnimation(self, b"geometry")
        self._edge_anim.setDuration(200)
        self._edge_anim.setEasingCurve(QEasingCurve.InOutCubic)

    def _setup_animation(self) -> None:
        self._anim_timer = QTimer()
        self._anim_timer.setInterval(100)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start()

    def _tick(self) -> None:
        if not self.isVisible():
            return
        frames = self._frames_cache.get(self._emotion, [])
        if not frames:
            return
        self._frame_idx += 1
        if self._frame_idx >= len(frames):
            if self._loop:
                self._frame_idx = 0
            else:
                self._frame_idx = len(frames) - 1
                self.set_emotion(self._after, loop=True)
                return
        self.update()

    def paintEvent(self, event) -> None:
        frames = self._frames_cache.get(self._emotion, [])
        p = QPainter(self)
        if not frames:
            # 无SVG帧时显示emoji fallback
            p.setRenderHint(QPainter.TextAntialiasing)
            font = p.font()
            font.setPointSize(int(self._display_size * 0.6))
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter, "🐱")
            p.end()
            return
        idx = self._frame_idx % len(frames)
        pix = frames[idx]
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        scaled = pix.scaled(self._display_size, self._display_size,
                            Qt.IgnoreAspectRatio, Qt.FastTransformation)
        p.drawPixmap(0, 0, scaled)
        p.end()

    def set_emotion(self, emotion: str, loop: bool = True, after: str = "idle") -> None:
        if emotion not in self._frames_cache:
            return
        self._emotion = emotion
        self._frame_idx = 0
        self._loop = loop
        self._after = after
        self.update()

    def set_pet_size(self, size: int) -> None:
        self._display_size = max(128, min(512, size))
        self.setFixedSize(self._display_size, self._display_size)

    def show_tip(self, text: str, duration_ms: int = 3000) -> None:
        self._tip_label.setText(text)
        self._tip_label.adjustSize()
        tw, th = self._tip_label.width() + 16, self._tip_label.height() + 8
        self._tip_label.setGeometry((self._display_size - tw) // 2, -th - 5, tw, th)
        self._tip_label.show()
        QTimer.singleShot(duration_ms, self._tip_label.hide)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_position = e.globalPos()
            self._drag_start_pos = e.globalPos()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._dragging:
            self.move(self.pos() + e.globalPos() - self._drag_position)
            self._drag_position = e.globalPos()
            if self._is_hidden:
                self._restore_from_edge()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._dragging:
            self._dragging = False
            if (e.globalPos() - self._drag_start_pos).manhattanLength() < self._click_threshold:
                self.clicked.emit()
            self.drag_finished.emit(self.x(), self.y())
            self._normal_geometry = self.geometry()

    def _check_edge(self) -> None:
        if self._dragging:
            return
        screen = QApplication.primaryScreen().geometry()
        geo = self.geometry()
        t = 20
        if self._is_hidden:
            if self.rect().contains(self.mapFromGlobal(QCursor.pos())):
                self._restore_from_edge()
            return
        x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
        ss = 8
        edge, target = None, None
        if x + w < t: edge, target = "left", QRect(ss - w, y, w, h)
        elif screen.width() - x < t: edge, target = "right", QRect(screen.width() - ss, y, w, h)
        elif y + h < t: edge, target = "top", QRect(x, ss - h, w, h)
        elif screen.height() - y < t: edge, target = "bottom", QRect(x, screen.height() - ss, w, h)
        if edge:
            self._is_hidden = True
            self._hidden_edge = edge
            self._normal_geometry = geo
            self._edge_anim.setEndValue(target)
            self._edge_anim.start()
            self.set_emotion("sleep", loop=True)

    def _restore_from_edge(self) -> None:
        if not self._is_hidden:
            return
        self._is_hidden = False
        self._hidden_edge = None
        self._edge_anim.setEndValue(self._normal_geometry)
        self._edge_anim.start()
        self.set_emotion("wake", loop=False, after="idle")

    def check_fullscreen(self, fs: bool) -> None:
        flags = Qt.FramelessWindowHint | Qt.Tool
        flags |= Qt.WindowStaysOnBottomHint if fs else Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def save_position(self) -> tuple:
        return (self.x(), self.y())

    def restore_position(self, x: int, y: int) -> None:
        self.move(x, y)
        self._normal_geometry = self.geometry()

    def cleanup(self) -> None:
        self._anim_timer.stop()
        self._edge_timer.stop()
        self._edge_anim.stop()