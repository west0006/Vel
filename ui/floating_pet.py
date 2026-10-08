"""
悬浮窗桌宠模块。SVG 帧动画驱动。
帧目录: ui/resources/animations/pet_svg/
"""

import json
import math
import os
import random
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap, QMouseEvent, QCursor, QBitmap, QImage
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QWidget, QLabel, QApplication

from ui.pet_fx import PetEffects
from utils.logger import get_logger

logger = get_logger(__name__)

FRAME_DIR = os.path.join(os.path.dirname(__file__), "resources", "animations", "pet_svg")

#: 帧归一化参数
FRAME_RENDER_SIZE = 512            # 预渲染尺寸（2x，保证缩放质量）
FRAME_TARGET_HEIGHT_RATIO = 0.86   # 归一化目标高度占预渲染高度的比例
FRAME_TARGET_WIDTH_RATIO = 0.94    # 归一化目标宽度上限占预渲染宽度的比例
FRAME_AREA_FILL = 0.92             # 目标面积填充系数（按面积归一化：人眼对面积更敏感）
FRAME_SCALE_LIMITS = (0.40, 3.00)  # 极端缩放保护（避免异常帧被放大到失真）
FRAME_BOTTOM_RATIO = 0.96          # 主题底部在窗口中的相对位置（留白 4%）
ALPHA_THRESHOLD = 30               # 不透明判定阈值（绘制与点击判定共用）


def _alpha_bbox(pix: QPixmap, threshold: int = ALPHA_THRESHOLD) -> "Optional[QRect]":
    """计算 pixmap 的不透明区域包围盒。

    这是帧归一化的基础：AI 生成的帧尺寸与位置**逐帧漂移**（诊断数据见
    `doc/dev/计划-当前待办.md` §3.0 —— 尺寸差异最高近 2 倍、底边跳动 36px），
    必须先量出主题的实际范围，才能统一缩放与对齐。

    Args:
        pix: 已渲染的帧。
        threshold: alpha 阈值。

    Returns:
        包围盒；全透明或计算失败时返回 ``None``（调用方回退整幅绘制）。
    """
    try:
        import numpy as np

        img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
        width, height = img.width(), img.height()
        ptr = img.constBits()
        ptr.setsize(img.byteCount())
        alpha = np.frombuffer(ptr, np.uint8).reshape(height, width, 4)[:, :, 3]
        mask = alpha > threshold
        if not mask.any():
            return None
        ys, xs = np.where(mask)
        return QRect(int(xs.min()), int(ys.min()),
                     int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
    except Exception:
        logger.exception("计算帧包围盒失败，回退整幅绘制")
        return None


def _load_frames(state: str) -> list:
    """加载某状态的全部 SVG 帧，**裁切包围盒并归一化到统一高度**。

    归一化针对诊断出的两个最刺眼的跳变（依据见 `doc/dev/计划-当前待办.md` §3.0）：

    - **尺寸跳变**：各帧主题宽高差异最高近 2 倍（如 sleep 123~231px）→ 等比统一缩放；
    - **位置跳变**：各帧主题位置漂移（底边跳动最多 36px）→ 由绘制方按底部对齐。

    Returns:
        ``QPixmap`` 列表，每帧已裁切 + 等比缩放；目录缺失时返回空列表。
    """
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
            canvas = QPixmap(FRAME_RENDER_SIZE, FRAME_RENDER_SIZE)
            canvas.fill(Qt.transparent)
            ph = QPainter(canvas)
            ph.setRenderHint(QPainter.Antialiasing, False)
            renderer.render(ph)
            ph.end()

            box = _alpha_bbox(canvas)
            if box is None or box.width() <= 0 or box.height() <= 0:
                logger.warning(f"帧 {path} 无有效主题区域，已跳过")
                continue
            subject = canvas.copy(box)

            # 归一化：按面积对齐（人眼对面积更敏感），并用目标框约束避免超框。
            # 仅按高度归一化时，横向姿态帧（如 sleep 蜷缩）宽度可达纵向帧的 2.6 倍，
            # 观感仍是"忽大忽小"，故改为面积优先 + 框约束。
            target_h = FRAME_RENDER_SIZE * FRAME_TARGET_HEIGHT_RATIO
            target_w = FRAME_RENDER_SIZE * FRAME_TARGET_WIDTH_RATIO
            target_area = target_h * target_w * FRAME_AREA_FILL
            area_scale = (target_area / (subject.width() * subject.height())) ** 0.5
            scale = min(area_scale,
                        target_h / subject.height(),
                        target_w / subject.width())
            lo, hi = FRAME_SCALE_LIMITS
            scale = max(lo, min(hi, scale))
            frames.append(subject.scaled(
                max(1, int(subject.width() * scale)),
                max(1, int(subject.height() * scale)),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            ))
        except Exception as e:
            logger.warning(f"加载帧失败: {path} -> {e}")
    if frames:
        logger.info(f"加载 [{state}] {len(frames)} 帧（已按包围盒归一化）")
    return frames


def compute_track_offset(mouse_x: float, mouse_y: float, size: int,
                         max_offset: float = 3.0,
                         radius: float = 220.0) -> tuple:
    """计算鼠标视线跟随的渲染偏移量。

    模块级纯函数（便于单元测试，不依赖任何 Qt 对象）。

    Args:
        mouse_x: 鼠标在窗口内的 x 坐标。
        mouse_y: 鼠标在窗口内的 y 坐标。
        size: 窗口边长（逻辑像素）。
        max_offset: 单轴最大偏移量（像素）。
        radius: 有效跟随半径（像素）；超出则偏移归零。

    Returns:
        ``(tx, ty)`` 浮点偏移量，两轴均被限制在 ``±max_offset`` 内。
    """
    center = size / 2.0
    dx, dy = mouse_x - center, mouse_y - center
    if (dx * dx + dy * dy) ** 0.5 > radius:
        return (0.0, 0.0)
    # 归一化到 [-1, 1] 后限幅，保证偏移不会随鼠标距离无限增长
    tx = max(-1.0, min(1.0, dx / center)) * max_offset
    ty = max(-1.0, min(1.0, dy / center)) * max_offset
    return (tx, ty)


#: 微动作配置文件（数据驱动，改 JSON 即可增删动作）
MICRO_CONF_PATH = os.path.join(os.path.dirname(__file__), "resources", "pet_conf.json")
#: 支持的情绪名（与 ui/resources/animations/pet_svg/ 下的帧目录一一对应）
KNOWN_EMOTIONS = ("idle", "wake", "thinking", "sleep",
                  "sad", "happy", "alert", "collapsed")
#: 配置缺失时的兜底动作表（动作名, 权重）
DEFAULT_MICRO_ACTIONS = (("alert", 0.6), ("wake", 0.3), ("happy", 0.6))
#: 配置缺失时的兜底间隔范围（毫秒）
DEFAULT_MICRO_INTERVAL = (15000, 35000)


def weighted_pick(actions) -> "str | None":
    """按权重抽签选出一个动作名。

    设计借鉴 DyberPet 的 `random_act.act_prob` 权重表（仅借鉴设计，未复制代码）。

    Args:
        actions: ``(动作名, 权重)`` 序列；权重 ``<= 0`` 的项会被忽略。

    Returns:
        选中的动作名；无有效候选时返回 ``None``。
    """
    candidates = [(name, weight) for name, weight in actions if weight > 0]
    if not candidates:
        return None
    names = [name for name, _ in candidates]
    weights = [weight for _, weight in candidates]
    return random.choices(names, weights=weights, k=1)[0]


def _load_micro_config():
    """读取 ``ui/resources/pet_conf.json`` 的微动作配置。

    Returns:
        ``(动作权重表, (最小间隔ms, 最大间隔ms), 是否启用)``；
        文件缺失、JSON 损坏或字段类型错误时一律回退默认值（不抛异常）。
    """
    actions = list(DEFAULT_MICRO_ACTIONS)
    interval = DEFAULT_MICRO_INTERVAL
    enabled = True
    try:
        if os.path.exists(MICRO_CONF_PATH):
            with open(MICRO_CONF_PATH, "r", encoding="utf-8") as fp:
                conf = json.load(fp)
            if not isinstance(conf, dict):
                logger.warning("pet_conf.json 顶层不是对象，使用默认微动作配置")
                return actions, interval, enabled
            enabled = bool(conf.get("micro_actions_enabled", True))
            loaded = []
            for item in conf.get("micro_actions", []):
                if not isinstance(item, dict):
                    continue
                weight = float(item.get("act_prob", 1.0))
                for act in item.get("act_list", []):
                    loaded.append((str(act), weight))
            if loaded:
                actions = loaded
            low = int(conf.get("idle_min_interval_ms", interval[0]))
            high = int(conf.get("idle_max_interval_ms", interval[1]))
            interval = (low, max(low, high))
    except Exception:
        logger.exception("读取 pet_conf.json 失败，使用默认微动作配置")
    return actions, interval, enabled


def compute_frame_rect(pix_width: int, pix_height: int, display_size: int,
                       track_offset: tuple = (0, 0),
                       bottom_ratio: float = FRAME_BOTTOM_RATIO) -> QRect:
    """计算归一化帧在窗口内的绘制矩形（模块级纯函数，便于单元测试）。

    归一化后的帧已按包围盒裁切，故只需：水平居中 + **底部对齐** + 视线跟随偏移。
    底部对齐用于消除各帧底边漂移（诊断：原始帧底边跳动最多 36px）。

    Args:
        pix_width: 归一化帧宽度（预渲染坐标系）。
        pix_height: 归一化帧高度（预渲染坐标系）。
        display_size: 窗口边长（逻辑像素）。
        track_offset: 视线跟随偏移 ``(tx, ty)``。
        bottom_ratio: 主题底部在窗口中的相对位置。

    Returns:
        绘制矩形（窗口局部坐标）。
    """
    scale = display_size / float(FRAME_RENDER_SIZE)
    width = max(1, int(round(pix_width * scale)))
    height = max(1, int(round(pix_height * scale)))
    tx, ty = track_offset
    x = (display_size - width) // 2 + int(tx)
    y = int(display_size * bottom_ratio) - height + int(ty)
    return QRect(x, y, width, height)


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
        for state in KNOWN_EMOTIONS:
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

        # 程序化特效层（Zzz / 爱心 / 汗滴…），纯 QPainter 绘制，不依赖素材
        self._fx = PetEffects(self._emotion)

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

    # 呼吸形变：周期（秒）与幅度（±1.6%）
    BREATH_PERIOD = 3.5
    BREATH_AMPLITUDE = 0.016
    # 情绪切换时的淡入时长（秒）。注意：帧间不做淡化 —— 帧间隔仅 100~200ms，
    # 每帧淡化会让相邻两帧永久叠加成像（画面发糊）；像素动画的标准做法是直接切帧。
    EMOTION_FADE_TIME = 0.18

    def _setup_animation(self) -> None:
        self._anim_timer = QTimer()
        self._anim_timer.setInterval(100)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start()
        # 鼠标跟踪平滑插值
        self._smooth_mouse = (0.0, 0.0)
        # 呼吸相位（弧度）与情绪切换淡入进度（0→1）
        self._breath_phase = 0.0
        self._emotion_fade = 1.0

    # ────────────── 交互系统 ──────────────

    def _setup_interaction(self) -> None:
        # 微动作配置（数据驱动；改 ui/resources/pet_conf.json 即可增删动作）
        self._micro_actions, self._micro_interval, self._micro_enabled = _load_micro_config()

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
        """按配置区间随机安排下一次微动作。"""
        low, high = self._micro_interval
        self._idle_micro_timer.start(random.randint(low, max(low, high)))

    def _do_micro_action(self) -> None:
        """按权重抽签触发一次微动作，播完自动回到 idle。

        仅在 idle 且未拖拽/未贴边隐藏时触发；动作名无对应帧时跳过并记日志。
        """
        self._idle_micro_timer.stop()
        if self._emotion != "idle" or self._is_hidden or getattr(self, '_dragging', False):
            self._schedule_micro_action()
            return
        if self._micro_enabled:
            action = weighted_pick(self._micro_actions)
            if action and action in self._frames_cache:
                self.set_emotion(action, loop=False, after="idle")
            elif action:
                logger.debug("微动作 %s 无对应帧目录，已跳过", action)
        self._schedule_micro_action()

    TRACK_MAX_OFFSET = 3.0     # 单轴最大渲染偏移(px)
    TRACK_RADIUS = 220.0       # 有效跟随半径(px)，超出则偏移归零
    TRACK_SMOOTHING = 0.3      # 平滑插值系数

    def _track_mouse(self) -> None:
        """按鼠标位置计算视线跟随偏移（带平滑与限幅）。

        修复要点：原实现用"偏移量的模"判断距离（最大约 4.2，永远小于阈值 180），
        且偏移未限幅 —— 鼠标远离时 `(pt.x()-cx)/cx*3` 会超出 ±3px 让猫咪飘出窗口。
        现改为按"鼠标到猫中心的实际距离"判断，并对偏移限幅。
        """
        pt = self.mapFromGlobal(QCursor.pos())
        tx, ty = compute_track_offset(
            pt.x(), pt.y(), self._display_size,
            max_offset=self.TRACK_MAX_OFFSET, radius=self.TRACK_RADIUS,
        )
        sx, sy = self._smooth_mouse
        k = self.TRACK_SMOOTHING
        self._smooth_mouse = (sx + (tx - sx) * k, sy + (ty - sy) * k)
        self._mouse_track_offset = (
            int(round(self._smooth_mouse[0])),
            int(round(self._smooth_mouse[1])),
        )

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

        # 时间步（秒）：以定时器间隔为准，使呼吸/淡入与帧率解耦
        dt = max(1, self._anim_timer.interval()) / 1000.0
        # 呼吸相位推进
        self._breath_phase = (
            self._breath_phase + (2.0 * math.pi / self.BREATH_PERIOD) * dt
        ) % (2.0 * math.pi)
        # 情绪切换淡入
        if self._emotion_fade < 1.0:
            self._emotion_fade = min(
                1.0, self._emotion_fade + dt / self.EMOTION_FADE_TIME
            )
        # 特效层推进（按毫秒）
        self._fx.advance(dt * 1000.0, self._display_size)

        frames = self._frames_cache.get(self._emotion, [])
        if not frames:
            self.update()
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

    def _breath_scale(self) -> float:
        """返回当前呼吸缩放系数（以窗口底部为锚点，纵向轻微起伏）。"""
        return 1.0 + self.BREATH_AMPLITUDE * math.sin(self._breath_phase)

    def _frame_rect(self, pix: QPixmap) -> QRect:
        """计算当前帧的绘制矩形（居中 + 底部对齐 + 视线跟随偏移）。

        Args:
            pix: 归一化后的帧。

        Returns:
            绘制矩形（窗口局部坐标）。
        """
        return compute_frame_rect(
            pix.width(), pix.height(), self._display_size,
            self._mouse_track_offset, FRAME_BOTTOM_RATIO,
        )

    def paintEvent(self, event) -> None:
        frames = self._frames_cache.get(self._emotion, [])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if not frames:
            p.setRenderHint(QPainter.TextAntialiasing)
            font = p.font()
            font.setPointSize(int(self._display_size * 0.6))
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter, "🐱")
            p.end()
            return
        pix = frames[self._frame_idx % len(frames)]
        rect = self._frame_rect(pix)

        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 1) 呼吸形变：以主题底部为锚点纵向缩放，让脚不悬空
        breath = self._breath_scale()
        if abs(breath - 1.0) > 1e-4:
            anchor = float(rect.bottom())
            p.translate(0.0, anchor)
            p.scale(1.0, breath)
            p.translate(0.0, -anchor)

        # 2) 情绪切换淡入
        p.setOpacity(self._emotion_fade)

        # 3) 绘制当前帧（归一化后按矩形缩放绘制）
        p.drawPixmap(rect, pix)

        # 4) 特效层：重置变换与不透明度，按窗口原始坐标系绘制
        p.setOpacity(1.0)
        p.resetTransform()
        self._fx.paint(p, self._display_size)
        p.end()

    def set_emotion(self, emotion: str, loop: bool = True, after: str = "idle") -> None:
        if emotion not in self._frames_cache:
            return
        self._emotion = emotion
        self._frame_idx = 0
        self._loop = loop
        self._after = after
        # 同步特效层并触发淡入（情绪切换是低频操作，淡化在此处才有意义）
        self._fx.set_emotion(emotion)
        self._emotion_fade = 0.0
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
        """检查点击位置是否落在猫咪身体上（按归一化帧的 alpha 判定）。

        与 ``paintEvent`` 共用 ``_frame_rect``，保证命中区域与实际绘制像素一致
        （归一化改变了绘制几何，若两处不共用会错位）。
        """
        frames = self._frames_cache.get(self._emotion, [])
        if not frames:
            return True
        pix = frames[self._frame_idx % len(frames)]
        rect = self._frame_rect(pix)
        if not rect.contains(pos):
            return False
        # 映射回归一化帧的位图坐标
        lx = int((pos.x() - rect.x()) * pix.width() / max(1, rect.width()))
        ly = int((pos.y() - rect.y()) * pix.height() / max(1, rect.height()))
        image = pix.toImage()
        return image.pixelColor(lx, ly).alpha() > ALPHA_THRESHOLD

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