"""`tools/gen_pet_frames.py` 的变换与画布约束测试。

覆盖 P3（squash & stretch）引入的 ``scale_x`` 支持，以及一条容易踩的守护：
**任何情绪的帧都不能超出画布被裁切** —— 起跳帧同时要"拉长 + 上移"，
参数调大一点就会把猫头顶切掉，而肉眼在缩略图里不容易发现。
"""

import pytest
from PIL import Image

from tools.gen_pet_frames import (
    BOTTOM_RATIO,
    CANVAS,
    EMOTION_RULES,
    SUBJECT_HEIGHT,
    place_on_canvas,
    transform,
)


def _subject(width: int = 300, height: int = 0) -> Image.Image:
    """造一个不透明矩形假主体（比真实猫图更严格：无透明边距可退让）。"""
    return Image.new("RGBA", (width, height or SUBJECT_HEIGHT), (255, 120, 60, 255))


class TestTransform:
    """单帧变换：`scale_x` / `scale_y` / `angle`。"""

    def test_identity_keeps_size(self):
        assert transform(_subject(), {}).size == (300, SUBJECT_HEIGHT)

    def test_scale_x_widens_only(self):
        """只给 scale_x 时只影响宽度。"""
        result = transform(_subject(), {"scale_x": 1.10})
        assert result.width > 300
        assert result.height == SUBJECT_HEIGHT

    def test_squash_is_wider_and_shorter(self):
        """压扁（squash）：横向变宽、纵向变矮 —— 体积守恒的挤压。"""
        result = transform(_subject(), {"scale_y": 0.90, "scale_x": 1.07})
        assert result.width > 300
        assert result.height < SUBJECT_HEIGHT

    def test_stretch_is_narrower_and_taller(self):
        """拉长（stretch）：横向变窄、纵向变高。"""
        result = transform(_subject(), {"scale_y": 1.08, "scale_x": 0.94})
        assert result.width < 300
        assert result.height > SUBJECT_HEIGHT

    def test_angle_keeps_canvas_size(self):
        """旋转使用 expand=False，尺寸不变（避免凭空长高导致画布溢出）。"""
        result = transform(_subject(), {"angle": -11})
        assert result.size == (300, SUBJECT_HEIGHT)


class TestFramesFitCanvas:
    """守护：所有情绪的每一帧都必须完整落在画布内。"""

    def test_every_frame_stays_inside_canvas(self):
        subject = _subject(width=int(CANVAS * 0.76))

        for emotion, rules in EMOTION_RULES.items():
            for index, rule in enumerate(rules, start=1):
                frame = place_on_canvas(
                    transform(subject, rule), dy=rule.get("dy", 0.0)
                )
                assert frame.size == (CANVAS, CANVAS), f"{emotion}_{index:02d} 画布尺寸不对"

                bbox = frame.getbbox()
                assert bbox is not None, f"{emotion}_{index:02d} 全透明（内容丢失）"
                left, top, right, bottom = bbox
                assert top > 0, (
                    f"{emotion} 第 {index} 帧顶部被裁切（top={top}）—— "
                    "检查该帧的 scale_y 与 dy 组合是否过大"
                )
                assert bottom < CANVAS, (
                    f"{emotion} 第 {index} 帧底部被裁切（bottom={bottom}）"
                )
                assert left >= 0 and right <= CANVAS

    def test_bottom_alignment_respected(self):
        """未给 dy 的帧，主体底部应落在 BOTTOM_RATIO 基线上（脚不离地）。"""
        subject = _subject()
        frame = place_on_canvas(subject, dy=0)
        assert frame.getbbox()[3] == int(CANVAS * BOTTOM_RATIO)


class TestEmotionRules:
    """规则数据本身的一致性。"""

    def test_all_rules_have_known_keys_only(self):
        """只允许 dy / scale_x / scale_y / angle —— 拼错键会被静默忽略。"""
        allowed = {"dy", "scale_x", "scale_y", "angle"}
        for emotion, rules in EMOTION_RULES.items():
            for rule in rules:
                assert set(rule) <= allowed, f"{emotion} 含未知键: {set(rule) - allowed}"

    def test_happy_has_squash_and_stretch(self):
        """happy 必须同时含"压扁"与"拉长"帧，否则只是整体平移。"""
        happy = EMOTION_RULES["happy"]
        assert any(r.get("scale_y", 1.0) < 1.0 for r in happy), "缺少压扁帧"
        assert any(r.get("scale_y", 1.0) > 1.0 for r in happy), "缺少拉长帧"
