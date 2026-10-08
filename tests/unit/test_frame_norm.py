"""帧归一化与绘制定位单元测试。

覆盖：
- ``compute_frame_rect``：底部对齐 / 水平居中 / 跟随偏移 / 缩放（纯函数，无需 Qt 应用）
- ``_alpha_bbox``：包围盒计算 / 全透明回退 / 全不透明
- ``_load_frames``：返回 QPixmap 列表、面积差异收敛、不超画布、已紧密裁切、目录缺失

背景：AI 逐帧独立生成导致帧间尺寸/位置漂移（诊断见 `doc/dev/计划-当前待办.md` §3.0），
归一化用于消除"忽大忽小"与"底部跳动"。
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

from ui.floating_pet import (
    FRAME_BOTTOM_RATIO,
    FRAME_RENDER_SIZE,
    KNOWN_EMOTIONS,
    _alpha_bbox,
    _load_frames,
    compute_frame_rect,
)


@pytest.fixture(scope="module")
def qt_app():
    """offscreen 模式下的 QApplication（QPixmap / QSvgRenderer 需要）。"""
    app = QApplication.instance() or QApplication([])
    yield app


class TestComputeFrameRect:
    """绘制矩形计算（纯函数）。"""

    def test_bottom_aligned_regardless_of_size(self):
        """不同尺寸的帧必须底边对齐 —— 消除诊断出的底边漂移（最多 36px）。"""
        expected = int(256 * FRAME_BOTTOM_RATIO) - 1
        for width, height in ((200, 440), (300, 300), (100, 220)):
            assert compute_frame_rect(width, height, 256).bottom() == expected

    def test_horizontally_centered(self):
        rect = compute_frame_rect(200, 400, 256)
        left_gap = rect.x()
        right_gap = 256 - rect.right() - 1
        assert abs(left_gap - right_gap) <= 1

    def test_track_offset_applied(self):
        base = compute_frame_rect(200, 400, 256, (0, 0))
        moved = compute_frame_rect(200, 400, 256, (3, 2))
        assert moved.x() == base.x() + 3
        assert moved.y() == base.y() + 2

    def test_scale_follows_display_size(self):
        rect = compute_frame_rect(256, 512, 512)
        assert rect.width() == 256
        assert rect.height() == 512

    def test_minimum_one_pixel(self):
        rect = compute_frame_rect(1, 1, 256)
        assert rect.width() >= 1 and rect.height() >= 1


class TestAlphaBBox:
    """alpha 包围盒计算。"""

    def test_transparent_returns_none(self, qt_app):
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        assert _alpha_bbox(pix) is None

    def test_detects_subject_region(self, qt_app):
        pix = QPixmap(128, 128)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.fillRect(10, 20, 50, 60, QColor(255, 0, 0))
        painter.end()
        box = _alpha_bbox(pix)
        assert box is not None
        assert (box.x(), box.y(), box.width(), box.height()) == (10, 20, 50, 60)

    def test_full_opaque_covers_canvas(self, qt_app):
        pix = QPixmap(32, 32)
        pix.fill(QColor(0, 0, 0))
        box = _alpha_bbox(pix)
        assert (box.x(), box.y(), box.width(), box.height()) == (0, 0, 32, 32)


class TestLoadFrames:
    """帧加载与归一化。"""

    def test_returns_pixmap_list(self, qt_app):
        """归一化版返回 QPixmap 列表（旧实现返回 (pixmap, offset, mask) 三元组）。"""
        frames = _load_frames("idle")
        assert frames
        assert all(isinstance(f, QPixmap) for f in frames)

    def test_missing_dir_returns_empty(self, qt_app):
        assert _load_frames("__not_exist__") == []

    def test_all_known_emotions_load(self, qt_app):
        for emotion in KNOWN_EMOTIONS:
            assert _load_frames(emotion), f"{emotion} 帧未加载"

    def test_area_variance_converges(self, qt_app):
        """归一化意图：同一情绪内各帧**面积**差异收敛。

        诊断显示归一化前面积比最高 2.10x（sleep），归一化后应低于 2.0x。
        """
        for emotion in ("idle", "sleep", "wake", "happy"):
            areas = [f.width() * f.height() for f in _load_frames(emotion)]
            ratio = max(areas) / min(areas)
            assert ratio < 2.0, f"{emotion} 面积比仍为 {ratio:.2f}x"

    def test_frames_fit_in_canvas(self, qt_app):
        """归一化后不得超出预渲染画布（否则绘制会被裁掉）。"""
        for emotion in KNOWN_EMOTIONS:
            for frame in _load_frames(emotion):
                assert frame.width() <= FRAME_RENDER_SIZE
                assert frame.height() <= FRAME_RENDER_SIZE

    def test_frames_are_cropped_tight(self, qt_app):
        """帧应已按包围盒紧密裁切（边缘不再残留大片透明）。"""
        for frame in _load_frames("idle"):
            box = _alpha_bbox(frame)
            assert box is not None
            # 缩放会产生少量半透明边缘像素，留 10% 容差
            assert box.width() >= frame.width() * 0.9
            assert box.height() >= frame.height() * 0.9
