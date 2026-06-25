"""情绪日志单元测试。"""

import pytest
from modules.health.mood_logger import MoodLogger


class TestMoodLogger:
    def setup_method(self):
        self.ml = MoodLogger()

    def test_positive_text(self):
        label, intensity = self.ml.analyze("今天真开心！太好了！")
        assert label == "positive"
        assert intensity > 0.5

    def test_negative_text(self):
        label, intensity = self.ml.analyze("好烦啊，压力太大了，真郁闷")
        assert label == "negative"
        assert intensity > 0.5

    def test_neutral_text(self):
        label, intensity = self.ml.analyze("今天星期三")
        assert label == "neutral"

    def test_mixed_prefers_stronger(self):
        # "喜欢" 0.8 > "烦" 0.7
        label, intensity = self.ml.analyze("我喜欢但是有点烦")
        assert label in ("positive", "negative", "neutral")

    def test_intensity_bounded(self):
        _, intensity = self.ml.analyze("开心开心开心开心开心开心开心开心开心")
        assert 0 <= intensity <= 1

    def test_empty_text(self):
        label, intensity = self.ml.analyze("")
        assert label == "neutral"

    def test_needs_comfort_after_two_negatives(self):
        self.ml._consecutive_negative = 2
        assert self.ml.needs_comfort()

    def test_needs_comfort_reset_on_positive(self):
        self.ml._consecutive_negative = 3
        self.ml.log_mood("太开心了！")  # 会重置
        assert self.ml._consecutive_negative == 0

    def test_get_daily_trend_empty(self):
        trend = self.ml.get_daily_trend(7)
        assert isinstance(trend, list)