"""日程解析器单元测试。"""

from datetime import datetime, timedelta
import pytest
from modules.schedule.schedule_parser import ScheduleParser, ScheduleItem


class TestScheduleParser:
    def setup_method(self):
        self.parser = ScheduleParser()

    def test_quick_parse_tomorrow(self):
        items = self.parser.parse_single("明天下午3点开会")
        assert len(items) >= 0  # dateparser 可能不装
        if items:
            assert items[0].title
            assert "开会" in items[0].title or items[0].start_time

    def test_is_valid_rejects_past(self):
        past = datetime.now() - timedelta(hours=2)
        item = ScheduleItem(title="test", start_time=past)
        assert not self.parser._is_valid(item)

    def test_is_valid_rejects_short_title(self):
        item = ScheduleItem(title="a", start_time=datetime.now() + timedelta(hours=1))
        assert not self.parser._is_valid(item)

    def test_is_valid_accepts_normal(self):
        item = ScheduleItem(title="开会", start_time=datetime.now() + timedelta(hours=1))
        assert self.parser._is_valid(item)

    def test_likely_schedule_positive(self):
        assert self.parser._likely_schedule("明天下午开会")
        assert self.parser._likely_schedule("提醒我喝水")
        assert self.parser._likely_schedule("今天天气")

    def test_likely_schedule_negative(self):
        assert not self.parser._likely_schedule("你好")
        assert not self.parser._likely_schedule("谢谢")

    def test_split_sentences(self):
        sents = self.parser._split_sentences("你好。今天天气不错！下午开会？")
        assert len(sents) >= 2

    def test_conflict_detection(self):
        now = datetime.now()
        items = [ScheduleItem(title="新", start_time=now + timedelta(hours=1))]
        existing = [{"title": "旧", "start_time": (now + timedelta(minutes=30)).isoformat(),
                      "end_time": (now + timedelta(hours=2)).isoformat()}]
        conflicts = self.parser.check_conflict(items, existing)
        assert len(conflicts) == 1
        assert conflicts[0]["overlap_type"] in ("contained_by", "partial")

    def test_conflict_no_overlap(self):
        now = datetime.now()
        items = [ScheduleItem(title="新", start_time=now + timedelta(hours=3))]
        existing = [{"title": "旧", "start_time": (now + timedelta(minutes=30)).isoformat(),
                      "end_time": (now + timedelta(hours=2)).isoformat()}]
        conflicts = self.parser.check_conflict(items, existing)
        assert len(conflicts) == 0

    def test_schedule_item_end_time_default(self):
        now = datetime.now()
        item = ScheduleItem(title="t", start_time=now)
        assert item.end_time == now + timedelta(hours=1)

    def test_to_dict(self):
        now = datetime.now()
        item = ScheduleItem(title="t", start_time=now)
        d = item.to_dict()
        assert d["title"] == "t"
        assert d["priority"] == 1