"""
动画控制器模块。

管理桌宠的动画状态切换，通过 QTimer 控制帧切换。
Alpha 版使用静态图片 + QTimer 切换，不做骨骼动画。
"""

import os
import random
from pathlib import Path
from typing import Callable, Dict, Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPixmap

from ui.theme import PetAnimation
from utils.logger import get_logger

logger = get_logger(__name__)


class AnimationController:
    """动画控制器。

    管理桌宠的情绪动画状态，通过定时器在帧图片间切换。
    Alpha 版用静态 PNG 序列模拟动画效果。
    """

    def __init__(self, resource_dir: Optional[str] = None):
        self._resource_dir = resource_dir or self._default_resource_dir()
        self._current_emotion = PetAnimation.IDLE
        self._current_frame = 0
        self._frames: Dict[str, list] = {}  # emotion -> [QPixmap, ...]
        self._timer = QTimer()
        self._timer.timeout.connect(self._next_frame)

        # 回调
        self._on_frame_change: Optional[Callable[[QPixmap], None]] = None

        # 动画结束回调
        self._on_animation_end: Optional[Callable[[], None]] = None

        # 是否暂停
        self._paused = False

    @staticmethod
    def _default_resource_dir() -> str:
        """获取默认资源目录。"""
        base = Path(__file__).parent / "resources" / "animations"
        return str(base)

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def load_frames(self, emotion: str, frame_files: list) -> None:
        """加载一组动画帧。

        Args:
            emotion: 情绪名称（与 PetAnimation 常量一致）
            frame_files: 图片文件路径列表
        """
        pixmaps = []
        for f in frame_files:
            path = f if os.path.isabs(f) else os.path.join(self._resource_dir, f)
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    pixmaps.append(pixmap)
                else:
                    logger.warning(f"动画帧加载失败（无效图片）: {path}")
            else:
                logger.warning(f"动画帧文件不存在: {path}")

        if pixmaps:
            self._frames[emotion] = pixmaps
            logger.info(f"动画帧已加载: {emotion} ({len(pixmaps)} 帧)")
        else:
            logger.warning(f"动画帧加载失败，无有效文件: {emotion}")

    def set_on_frame_change(self, callback: Callable[[QPixmap], None]) -> None:
        """设置帧切换回调（更新 QLabel 的 pixmap）。"""
        self._on_frame_change = callback

    def set_on_animation_end(self, callback: Callable[[], None]) -> None:
        """设置动画结束回调。"""
        self._on_animation_end = callback

    # ------------------------------------------------------------------
    # 播放控制
    # ------------------------------------------------------------------

    def play(self, emotion: str, loop: bool = True) -> None:
        """播放指定情绪的动画。

        Args:
            emotion: 情绪名称
            loop: 是否循环播放（一次性动画在最后一帧停止）
        """
        if emotion not in self._frames:
            logger.warning(f"未加载 {emotion} 的动画帧，切换到 idle")
            emotion = self._is_idle_loaded()
            if not emotion:
                return

        self._timer.stop()
        self._current_emotion = emotion
        self._current_frame = 0
        self._paused = False

        # 设置定时器间隔
        interval = PetAnimation.FRAME_INTERVAL_MS.get(emotion, 1000)
        self._timer.setInterval(interval)

        # 显示第一帧
        self._show_current_frame()

        # 一次性动画：在最后一帧停止
        if not loop:
            duration = PetAnimation.ANIMATION_DURATION.get(emotion, 3000)
            QTimer.singleShot(duration, self.stop)
            QTimer.singleShot(duration, self._on_animation_end or (lambda: None))

        self._timer.start()
        logger.debug(f"动画播放: {emotion}")

    def stop(self) -> None:
        """停止当前动画，回到待机状态。"""
        self._timer.stop()
        self._current_emotion = PetAnimation.IDLE
        self._current_frame = 0

        # 尝试切换到 idle
        idle_frames = self._frames.get(PetAnimation.IDLE, [])
        if idle_frames:
            self._show_frame(0)

    def pause(self) -> None:
        """暂停动画（保留当前帧）。"""
        self._paused = True
        self._timer.stop()

    def resume(self) -> None:
        """恢复播放。"""
        if self._paused:
            self._paused = False
            self._timer.start()

    def set_idle_animation(self) -> None:
        """播放随机待机动画。"""
        if self._current_emotion == PetAnimation.IDLE:
            return
        self.play(PetAnimation.IDLE, loop=True)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _next_frame(self) -> None:
        """切换到下一帧。"""
        frames = self._frames.get(self._current_emotion, [])
        if not frames:
            return

        self._current_frame = (self._current_frame + 1) % len(frames)
        self._show_current_frame()

    def _show_current_frame(self) -> None:
        """显示当前帧。"""
        frames = self._frames.get(self._current_emotion, [])
        if not frames:
            return
        if self._current_frame < len(frames):
            self._show_frame(self._current_frame)

    def _show_frame(self, index: int) -> None:
        """显示指定索引的帧。"""
        frames = self._frames.get(self._current_emotion, [])
        if not frames or index >= len(frames):
            return
        if self._on_frame_change:
            self._on_frame_change(frames[index])

    def _is_idle_loaded(self) -> Optional[str]:
        """检查 idle 动画是否已加载，若没有则返回第一个已加载的情绪。"""
        if PetAnimation.IDLE in self._frames:
            return PetAnimation.IDLE
        for emotion in self._frames:
            return emotion
        return None

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @property
    def current_emotion(self) -> str:
        return self._current_emotion

    def is_playing(self) -> bool:
        return self._timer.isActive()

    def cleanup(self) -> None:
        """清理资源。"""
        self._timer.stop()
        self._frames.clear()