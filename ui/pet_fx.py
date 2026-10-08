"""
桌面宠物程序化特效层。

用 ``QPainter`` 直接绘制几何图形来表达情绪，**不需要任何美术素材**：

| 情绪 | 特效 |
|---|---|
| `sleep` | 飘动上升的 Zzz |
| `happy` | 上升的爱心 |
| `sad` | 滴落的汗滴 |
| `alert` | 脉冲扩散的惊叹号 |
| `thinking` | 漂浮的问号 |
| `wake` | 上升的小星星 |

设计依据见 `doc/dev/方案-动画与气泡系统设计笔记.md` §3.2「特效层」：

- 纯代码绘制，不引入新依赖、不改动 SVG 素材（AGENTS §1.2 / §7）；
- 坐标为**窗口局部逻辑像素**，由 `FloatingPet.paintEvent` 调用 ``paint()``；
- 粒子状态自维护，`advance()` 按毫秒推进，无后台线程、无定时器内部实现（由主窗口的
  动画定时器驱动），符合 AGENTS §4.3 的主线程 UI 约束；
- 发射与推进均为纯计算 + 随机数，可脱离 Qt 窗口做单元测试。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from utils.logger import get_logger

logger = get_logger(__name__)

#: 粒子生命期上限（秒），防止异常配置导致粒子永久驻留
MAX_LIFE_SECONDS = 6.0
#: 同时存在的粒子数上限（性能护栏）
MAX_PARTICLES = 24
#: 单次推进的最大时间步（秒）：系统休眠/卡顿恢复后裁剪巨大间隔，避免粒子瞬移
MAX_STEP_SECONDS = 0.5


@dataclass
class Particle:
    """单个特效粒子。"""

    x: float
    y: float
    vx: float
    vy: float
    life: float           # 剩余寿命（秒）
    max_life: float       # 总寿命（秒）
    size: float = 10.0    # 基础尺寸（像素）
    kind: str = "heart"   # 形状：heart / zzz / drop / bang / question / star

    @property
    def alpha(self) -> float:
        """归一化不透明度：随剩余寿命线性衰减。"""
        if self.max_life <= 0:
            return 0.0
        return max(0.0, min(1.0, self.life / self.max_life))

    @property
    def progress(self) -> float:
        """归一化生命进度 0→1（用于尺寸/旋转变化）。"""
        if self.max_life <= 0:
            return 1.0
        return 1.0 - max(0.0, min(1.0, self.life / self.max_life))

    def step(self, dt: float) -> None:
        """按秒推进粒子（位置积分 + 寿命递减）。"""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt


@dataclass(frozen=True)
class EmitterConfig:
    """某情绪的特效发射配置。"""

    kind: str
    color: Tuple[int, int, int]
    interval: float                     # 发射间隔（秒）
    life: Tuple[float, float] = (1.4, 2.2)   # 寿命范围（秒）
    speed: Tuple[float, float] = (-26.0, -14.0)  # vy 范围（负值向上）
    drift: Tuple[float, float] = (-6.0, 6.0)     # vx 范围
    size: Tuple[float, float] = (9.0, 14.0)      # 尺寸范围
    origin: Tuple[float, float] = (0.66, 0.26)   # 相对窗口的发射点


#: 情绪 → 发射配置。未列出的情绪不产生特效。
EMOTION_EFFECTS: Dict[str, EmitterConfig] = {
    "sleep": EmitterConfig(
        kind="zzz", color=(150, 170, 220), interval=1.5,
        life=(2.0, 2.8), speed=(-22.0, -13.0), size=(11.0, 18.0),
        origin=(0.72, 0.20),
    ),
    "happy": EmitterConfig(
        kind="heart", color=(255, 110, 140), interval=0.45,
        life=(1.2, 1.9), speed=(-34.0, -20.0), size=(8.0, 14.0),
        origin=(0.70, 0.30),
    ),
    "sad": EmitterConfig(
        kind="drop", color=(120, 170, 230), interval=0.8,
        life=(1.0, 1.6), speed=(6.0, 16.0), size=(6.0, 10.0),
        origin=(0.62, 0.42),
    ),
    "alert": EmitterConfig(
        kind="bang", color=(255, 170, 60), interval=0.55,
        life=(0.6, 1.0), speed=(-16.0, -8.0), size=(10.0, 14.0),
        origin=(0.74, 0.24),
    ),
    "thinking": EmitterConfig(
        kind="question", color=(150, 160, 200), interval=1.1,
        life=(1.6, 2.4), speed=(-15.0, -8.0), size=(10.0, 15.0),
        origin=(0.70, 0.28),
    ),
    "wake": EmitterConfig(
        kind="star", color=(255, 215, 110), interval=0.7,
        life=(0.9, 1.5), speed=(-28.0, -16.0), size=(7.0, 12.0),
        origin=(0.68, 0.32),
    ),
}


class PetEffects:
    """情绪特效管理器：按情绪发射、推进并绘制粒子。"""

    def __init__(self, emotion: str = "idle") -> None:
        """
        Args:
            emotion: 初始情绪；仅 ``EMOTION_EFFECTS`` 中登记的情绪会产生特效。
        """
        self._emotion = emotion
        self._particles: List[Particle] = []
        self._since_emit = 0.0
        self._enabled = True

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    @property
    def emotion(self) -> str:
        """当前情绪。"""
        return self._emotion

    @property
    def particle_count(self) -> int:
        """当前存活粒子数。"""
        return len(self._particles)

    @property
    def has_visible(self) -> bool:
        """是否有粒子需要绘制（供主窗口决定是否重绘）。"""
        return bool(self._particles)

    def set_enabled(self, enabled: bool) -> None:
        """总开关（设置面板"特效"选项可接入）。"""
        self._enabled = bool(enabled)
        if not self._enabled:
            self._particles.clear()

    def set_emotion(self, emotion: str) -> None:
        """切换情绪：清空当前粒子，切换到新发射器。"""
        if emotion == self._emotion:
            return
        self._emotion = emotion
        # 情绪切换时清空，避免上一个情绪的特效残留造成语义混乱
        self._particles.clear()
        self._since_emit = 0.0

    def clear(self) -> None:
        """清空所有粒子。"""
        self._particles.clear()
        self._since_emit = 0.0

    # ------------------------------------------------------------------
    # 推进
    # ------------------------------------------------------------------

    def advance(self, dt_ms: float, size: int) -> None:
        """按毫秒推进特效（发射 + 积分 + 回收）。

        Args:
            dt_ms: 距上次推进的毫秒数；非正值或异常值会被忽略。
            size: 窗口边长（逻辑像素）。
        """
        if not self._enabled:
            return
        try:
            dt = float(dt_ms) / 1000.0
        except (TypeError, ValueError):
            return
        if dt <= 0.0 or size <= 0:
            return
        # 长时间挂起后恢复时裁剪时间步（此前实现误把大 dt 裁到 0.1 并丢弃剩余时间）
        dt = min(dt, MAX_STEP_SECONDS)

        for particle in self._particles:
            particle.step(dt)
        self._particles = [p for p in self._particles if p.life > 0.0]

        config = EMOTION_EFFECTS.get(self._emotion)
        if config is None:
            return
        self._since_emit += dt
        while self._since_emit >= config.interval:
            self._since_emit -= config.interval
            if len(self._particles) >= MAX_PARTICLES:
                break
            self._particles.append(self._spawn(config, size))

    def _spawn(self, config: EmitterConfig, size: int) -> Particle:
        """在配置的发射点生成一个粒子。"""
        ox, oy = config.origin
        life = random.uniform(*config.life)
        return Particle(
            x=ox * size + random.uniform(-6.0, 6.0),
            y=oy * size + random.uniform(-6.0, 6.0),
            vx=random.uniform(*config.drift),
            vy=random.uniform(*config.speed),
            life=min(life, MAX_LIFE_SECONDS),
            max_life=min(life, MAX_LIFE_SECONDS),
            size=random.uniform(*config.size),
            kind=config.kind,
        )

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------

    def color_for(self, kind: str) -> QColor:
        """返回某形状对应的基础颜色（未登记的 kind 回退白色）。"""
        for config in EMOTION_EFFECTS.values():
            if config.kind == kind:
                r, g, b = config.color
                return QColor(r, g, b)
        return QColor(255, 255, 255)

    def paint(self, painter: QPainter, size: int) -> None:
        """把当前所有粒子绘制到 painter 上。

        Args:
            painter: 已激活的 QPainter（调用方负责 begin/end）。
            size: 窗口边长（逻辑像素）。
        """
        if not self._particles:
            return
        try:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            for particle in self._particles:
                self._draw_particle(painter, particle, size)
            painter.restore()
        except Exception:
            logger.exception("特效绘制失败")

    def _draw_particle(self, painter: QPainter, particle: Particle, size: int) -> None:
        """按形状分派绘制。"""
        color = self.color_for(particle.kind)
        color.setAlphaF(particle.alpha)
        # 尺寸随生命进度轻微放大
        scale = 1.0 + 0.35 * particle.progress
        half = particle.size * scale / 2.0
        cx, cy = particle.x, particle.y

        if particle.kind == "zzz":
            self._draw_text(painter, "Z", cx, cy, particle.size * scale, color)
        elif particle.kind == "question":
            self._draw_text(painter, "?", cx, cy, particle.size * scale, color)
        elif particle.kind == "heart":
            self._draw_heart(painter, cx, cy, half, color)
        elif particle.kind == "drop":
            self._draw_drop(painter, cx, cy, half, color)
        elif particle.kind == "bang":
            self._draw_bang(painter, cx, cy, half, color)
        elif particle.kind == "star":
            self._draw_star(painter, cx, cy, half, color)
        else:
            painter.setBrush(color)
            painter.drawEllipse(QPointF(cx, cy), half, half)

    @staticmethod
    def _draw_text(painter: QPainter, text: str, cx: float, cy: float,
                   px: float, color: QColor) -> None:
        """用字体绘制字母类特效（Zzz / ?）。"""
        font = QFont()
        font.setPointSizeF(max(6.0, px))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(color))
        rect = QRectF(cx - px, cy - px, px * 2.0, px * 2.0)
        painter.drawText(rect, Qt.AlignCenter, text)

    @staticmethod
    def _draw_heart(painter: QPainter, cx: float, cy: float, half: float,
                    color: QColor) -> None:
        """贝塞尔心形。"""
        w, h = half * 2.0, half * 2.0
        path = QPainterPath()
        path.moveTo(cx, cy + h * 0.35)
        path.cubicTo(cx - w * 0.9, cy - h * 0.25, cx - w * 0.32, cy - h * 0.85,
                     cx, cy - h * 0.22)
        path.cubicTo(cx + w * 0.32, cy - h * 0.85, cx + w * 0.9, cy - h * 0.25,
                     cx, cy + h * 0.35)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

    @staticmethod
    def _draw_drop(painter: QPainter, cx: float, cy: float, half: float,
                   color: QColor) -> None:
        """水滴：上方尖角 + 下方圆弧。"""
        path = QPainterPath()
        path.moveTo(cx, cy - half * 1.25)
        path.cubicTo(cx + half * 0.95, cy - half * 0.1,
                     cx + half, cy + half, cx, cy + half)
        path.cubicTo(cx - half, cy + half,
                     cx - half * 0.95, cy - half * 0.1, cx, cy - half * 1.25)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

    @staticmethod
    def _draw_bang(painter: QPainter, cx: float, cy: float, half: float,
                   color: QColor) -> None:
        """惊叹号：竖条 + 圆点。"""
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(
            QRectF(cx - half * 0.28, cy - half * 1.3, half * 0.56, half * 1.6),
            half * 0.28, half * 0.28,
        )
        painter.drawEllipse(QPointF(cx, cy + half * 0.85), half * 0.32, half * 0.32)

    @staticmethod
    def _draw_star(painter: QPainter, cx: float, cy: float, half: float,
                   color: QColor) -> None:
        """四角星（用两个旋转的菱形叠加近似）。"""
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        for angle in (0.0, math.pi / 4.0):
            path = QPainterPath()
            for index, (sx, sy) in enumerate(
                ((0.0, -1.4), (0.34, -0.34), (1.4, 0.0), (0.34, 0.34),
                 (0.0, 1.4), (-0.34, 0.34), (-1.4, 0.0), (-0.34, -0.34))
            ):
                px = sx * math.cos(angle) - sy * math.sin(angle)
                py = sx * math.sin(angle) + sy * math.cos(angle)
                point = QPointF(cx + px * half, cy + py * half)
                if index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            path.closeSubpath()
            painter.drawPath(path)
