"""
悬浮窗桌宠模块。SVG 帧动画驱动。
帧目录: ui/resources/animations/pet_svg/
"""

import os
import random
import xml.etree.ElementTree as ET
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap, QMouseEvent, QCursor, QBitmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QWidget, QLabel, QApplication

from utils.logger import get_logger

logger = get_logger(__name__)

FRAME_DIR = os.path.join(os.path.dirname(__file__), "resources", "animations", "pet_svg")

# 暖色调（猫身体、肚皮、腮红），用于计算视觉重心
_BODY_HEX_PREFIXES = ("#f", "#e", "#d", "#c")


def _compute_body_center(svg_path: str) -> tuple:
    """解析像素画 SVG，返回暖色 rect 的包围盒中心 (cx, cy)。

    排除深色轮廓（#0-#4 开头），只计算身体部分的几何中心。
    """
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
        min_x, min_y = 256, 256
        max_x, max_y = 0, 0
        count = 0
        for rect in root.iter("{http://www.w3.org/2000/svg}rect"):
            fill = rect.get("fill", "")
            if not fill.startswith(_BODY_HEX_PREFIXES):
                continue
            x = int(rect.get("x", 0))
            y = int(rect.get("y", 0))
            w = int(rect.get("width", 4))
            h = int(rect.get("height", 4))
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)
            count += 1
        if count == 0:
            return (0, 0)
        cx = (min_x + max_x) // 2
        cy = (min_y + max_y) // 2
        # 返回偏移量：画布中心(128,128) 到 身体中心的差值
        return (128 - cx, 128 - cy)
    except Exception:
        return (0, 0)


def _load_frames(state: str) -> list:
    """加载某状态的全部 SVG 帧，预渲染为 (QPixmap, offset, mask) 列表。"""
    folder = os.path.join(FRAME_DIR, state)
    if not os.path.isdir(folder):
        return []
    files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".svg")],
        key=lambda x: int(x.split("_")[-1].replace(".svg", "")) if "_" in x else 0,
    )
    frames = []
    for fname in files:
        path = os.path.join(folder, fname)
        try:
            renderer = QSvgRenderer(path)
            # 2x 预渲染：512×512 → SmoothTransformation 缩至 256
            hi = QPixmap(512, 512)
            hi.fill(Qt.transparent)
            ph = QPainter(hi)
            ph.setRenderHint(QPainter.Antialiasing, False)
            renderer.render(ph)
            ph.end()
            pix = hi.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            offset = _compute_body_center(path)
            mask = pix.createMaskFromColor(Qt.transparent, Qt.MaskOutColor)
            frames.append((pix, offset, mask))
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
        self._setup_interaction()

        self._tip_label = QLabel(self)
        self._tip_label.setAlignment(Qt.AlignCenter)
        self._tip_label.setStyleSheet("""
            background-color: rgba(30,30,30,180); color: white;
            border-radius: 8px; padding: 4px 10px;
            font: 600 12px 'MaokenAssortedSans', 'Microsoft YaHei UI';
        """)
        self._tip_label.hide()

    def _setup_window(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self._display_size, self._display_size)

        # 多屏：吸附到鼠标所在屏幕右下角
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        s = screen.availableGeometry()
        self.move(s.right() - self._display_size - 50, s.bottom() - self._display_size - 100)

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

    # 每情绪帧间隔(ms)
    EMOTION_INTERVALS = {
        "idle": 150, "wake": 80, "thinking": 120, "sleep": 200,
        "sad": 120, "happy": 100, "alert": 100, "collapsed": 200,
    }

    def _setup_animation(self) -> None:
        self._anim_timer = QTimer()
        self._anim_timer.setInterval(100)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start()
        # 鼠标跟踪平滑插值
        self._smooth_mouse = (0.0, 0.0)

    # ────────────── 交互系统 ──────────────

    MICRO_ACTIONS = [None, None, None, None, "happy"]  # 大部分时间不动，偶尔 happy 微表情

    def _setup_interaction(self) -> None:
        # 随机微动作
        self._idle_micro_timer = QTimer()
        self._idle_micro_timer.timeout.connect(self._do_micro_action)
        self._schedule_micro_action()

        # 鼠标视线跟随
        self._mouse_track_offset = (0, 0)
        self._mouse_track_timer = QTimer()
        self._mouse_track_timer.setInterval(200)
        self._mouse_track_timer.timeout.connect(self._track_mouse)
        self._mouse_track_timer.start()

        # 抚摸检测
        self._hover_timer = QTimer()
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._on_petted)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)

    def _schedule_micro_action(self) -> None:
        delay = random.randint(15000, 35000)
        self._idle_micro_timer.start(delay)

    def _do_micro_action(self) -> None:
        self._idle_micro_timer.stop()
        if self._emotion != "idle" or self._is_hidden or getattr(self, '_dragging', False):
            self._schedule_micro_action()
            return
        action = random.choice(self.MICRO_ACTIONS)
        if action and action in self._frames_cache:
            self.set_emotion(action, loop=False, after="idle")
        self._schedule_micro_action()

    def _track_mouse(self) -> None:
        pt = self.mapFromGlobal(QCursor.pos())
        cx, cy = self._display_size // 2, self._display_size // 2
        tx = (pt.x() - cx) / cx * 3
        ty = (pt.y() - cy) / cy * 3
        d = (tx ** 2 + ty ** 2) ** 0.5
        if d > 180:
            tx, ty = 0.0, 0.0
        # 平滑插值
        sx, sy = self._smooth_mouse
        self._smooth_mouse = (sx + (tx - sx) * 0.3, sy + (ty - sy) * 0.3)
        self._mouse_track_offset = (int(self._smooth_mouse[0]), int(self._smooth_mouse[1]))

    def _on_petted(self) -> None:
        if self._emotion == "idle" and not getattr(self, '_dragging', False):
            self.show_tip("呼噜呼噜~ 💕", 2000)
            self.set_emotion("happy", loop=False, after="idle")

    def enterEvent(self, event) -> None:
        self._hover_timer.start(1500)

    def leaveEvent(self, event) -> None:
        self._hover_timer.stop()

    # ────────────── 动画 ──────────────

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
        # 动态帧间隔
        interval = self.EMOTION_INTERVALS.get(self._emotion, 100)
        self._anim_timer.setInterval(interval)
        self.update()

    def paintEvent(self, event) -> None:
        frames = self._frames_cache.get(self._emotion, [])
        p = QPainter(self)
        if not frames:
            p.setRenderHint(QPainter.TextAntialiasing)
            font = p.font()
            font.setPointSize(int(self._display_size * 0.6))
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter, "🐱")
            p.end()
            return
        idx = self._frame_idx % len(frames)
        pix, offset, _ = frames[idx]
        dx, dy = offset
        scale = self._display_size / 256
        ox, oy = int(dx * scale), int(dy * scale)
        tx, ty = self._mouse_track_offset
        ox += tx
        oy += ty

        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        scaled = pix.scaled(self._display_size, self._display_size,
                            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # 居中绘制
        px = (self._display_size - scaled.width()) // 2
        py = (self._display_size - scaled.height()) // 2
        p.drawPixmap(px + ox, py + oy, scaled)
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
        # 点击穿透：透明区域不处理，让事件传递给下层窗口
        if not self._is_click_on_body(e.pos()):
            e.ignore()
            return
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_position = e.globalPos()
            self._drag_start_pos = e.globalPos()

    def _is_click_on_body(self, pos: QPoint) -> bool:
        """检查点击位置是否在猫咪身体上（非透明区域）。"""
        frames = self._frames_cache.get(self._emotion, [])
        if not frames:
            return True
        idx = self._frame_idx % len(frames)
        pix, offset, _ = frames[idx]
        sx = int(pos.x() * 256 / self._display_size)
        sy = int(pos.y() * 256 / self._display_size)
        if sx < 0 or sy < 0 or sx >= 256 or sy >= 256:
            return False
        img = pix.toImage()
        return img.pixelColor(sx, sy).alpha() > 30

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
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        geo = self.geometry()
        screen_geo = screen.availableGeometry()
        t = 20
        if self._is_hidden:
            if self.rect().contains(self.mapFromGlobal(QCursor.pos())):
                self._restore_from_edge()
            return
        x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
        ss = 8
        edge, target = None, None
        if x + w < screen_geo.left() + t:
            edge = "left"
            target = QRect(screen_geo.left() + ss - w, y, w, h)
        elif screen_geo.right() - x - w < t:
            edge = "right"
            target = QRect(screen_geo.right() - ss, y, w, h)
        elif y + h < screen_geo.top() + t:
            edge = "top"
            target = QRect(x, screen_geo.top() + ss - h, w, h)
        elif screen_geo.bottom() - y - h < t:
            edge = "bottom"
            target = QRect(x, screen_geo.bottom() - ss, w, h)
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
        self._idle_micro_timer.stop()
        self._mouse_track_timer.stop()
        self._hover_timer.stop()