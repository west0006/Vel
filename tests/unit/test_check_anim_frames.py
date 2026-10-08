"""动画帧体检工具（tools/check_anim_frames.py）单元测试。

用 pytest 验证工具的核心测量与判定逻辑（脚本入口本身是薄壳）。
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

from tools.check_anim_frames import MIN_FRAMES, THRESHOLDS, check_emotion, measure


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _block_pixmap(x, y, w, h, size=512):
    """构造指定区域不透明的位图。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.fillRect(x, y, w, h, QColor(200, 120, 60))
    painter.end()
    return pix


class TestThresholds:
    """阈值配置本身要合理（防止误配导致工具失效）。"""

    def test_all_thresholds_positive(self):
        for key, value in THRESHOLDS.items():
            assert value > 0, f"{key} 阈值必须为正"

    def test_min_frames(self):
        assert MIN_FRAMES >= 4


class TestMeasure:
    def test_returns_metrics(self, qt_app):
        metrics = measure(_block_pixmap(10, 20, 100, 200))
        assert metrics is not None
        assert metrics["width"] == 100
        assert metrics["height"] == 200
        assert metrics["area"] == 20000
        assert metrics["bottom"] == 219          # y + h - 1
        assert metrics["center_x"] == pytest.approx(59.5)

    def test_transparent_returns_none(self, qt_app):
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        assert measure(pix) is None


class TestCheckEmotion:
    def test_flags_current_material_as_failing(self, qt_app, capsys):
        """当前素材应当被判为不达标 —— 这同时验证了判据有区分度。

        诊断（doc/dev/计划-当前待办.md §3.0）显示现有帧的面积差异最高 2.10x、
        底边跳动 36px，远超阈值，故必须 FAIL。
        """
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "ui", "resources", "animations", "pet_svg")
        folder = os.path.join(base, "sleep")
        if not os.path.isdir(folder):
            pytest.skip("素材目录不存在")
        assert check_emotion(folder) is False
        captured = capsys.readouterr().out
        assert "FAIL" in captured

    def test_empty_dir_fails(self, qt_app, tmp_path, capsys):
        assert check_emotion(str(tmp_path)) is False
        assert "FAIL" in capsys.readouterr().out

    def test_consistent_frames_pass(self, qt_app, tmp_path, capsys):
        """尺寸/位置一致的帧序列应当 PASS（工具的正向能力）。"""
        import shutil

        base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "ui", "resources", "animations", "pet_svg")
        source = os.path.join(base, "idle")
        if not os.path.isdir(source):
            pytest.skip("素材目录不存在")

        # 用同一帧复制 8 份：尺寸与位置完全一致 → 应判 PASS
        first = sorted(f for f in os.listdir(source) if f.endswith(".svg"))[0]
        for index in range(MIN_FRAMES):
            shutil.copy(os.path.join(source, first),
                        str(tmp_path / f"idle_{index + 1:02d}.svg"))
        assert check_emotion(str(tmp_path)) is True
        assert "PASS" in capsys.readouterr().out
