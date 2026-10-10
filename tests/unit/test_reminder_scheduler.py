"""ReminderScheduler 与 RecurrenceEngine 单元测试。

覆盖两类"出错不报错"的逻辑：
- **提醒偏移学习**（`record_feedback` / `get_learned_offset`）：连续推迟 3 次应把偏移 +5 分钟并上限 60；
- **重复规则日期生成**（RFC 5545 子集）：频率/间隔/星期选择与不支持频率的兜底。
"""

from datetime import datetime, timedelta

import pytest

from modules.schedule.recurrence import RecurrenceEngine
from modules.schedule.reminder_scheduler import ReminderScheduler


class _FakeStore:
    """最小 ScheduleStore 替身。"""

    def __init__(self, schedules=None):
        self._schedules = schedules or {}

    def get_schedule(self, schedule_id):
        return self._schedules.get(schedule_id)


@pytest.fixture
def sched():
    """构造一个未接 APScheduler 的调度器实例（只测学习逻辑）。"""
    instance = ReminderScheduler(snapshot_path="test-snapshot.json")
    instance._store = _FakeStore()
    return instance


class TestLearnedOffset:
    """提醒偏移学习。"""

    def test_default_offset_is_15(self, sched):
        assert sched.get_learned_offset() == 15
        assert sched.get_learned_offset("meeting") == 15

    def test_unknown_schedule_is_ignored(self, sched):
        sched.record_feedback("__not_exist__", "snooze")
        assert sched._offset_learning == {}

    def test_non_snooze_only_counts_total(self, sched):
        sched._store = _FakeStore({"s1": {"title": "部门会议", "reminder_offset_min": 15}})
        sched.record_feedback("s1", "complete")
        learning = sched._offset_learning["meeting"]
        assert learning["total_count"] == 1
        assert learning["snooze_count"] == 0
        assert learning["current_offset"] == 15

    def test_three_snoozes_increase_offset_by_5(self, sched):
        sched._store = _FakeStore({"s1": {"title": "部门会议", "reminder_offset_min": 15}})
        for _ in range(3):
            sched.record_feedback("s1", "snooze")
        learning = sched._offset_learning["meeting"]
        assert learning["current_offset"] == 20
        assert learning["snooze_count"] == 0        # 生效后重置，重新累计

    def test_offset_capped_at_60(self, sched):
        sched._store = _FakeStore({"s1": {"title": "会议", "reminder_offset_min": 60}})
        for _ in range(3):
            sched.record_feedback("s1", "snooze")
        assert sched._offset_learning["meeting"]["current_offset"] == 60

    def test_get_learned_offset_after_learning(self, sched):
        sched._store = _FakeStore({"s1": {"title": "约会", "reminder_offset_min": 15}})
        for _ in range(3):
            sched.record_feedback("s1", "snooze")
        assert sched.get_learned_offset("date") == 20

    def test_title_categorisation(self, sched):
        """标题关键词决定分类，未匹配则归 default。"""
        cases = {
            # 实现按关键词子串匹配（"会议"/"团建"/"医疗"/"约会"/"上课"/"面试"）
            "部门会议": "meeting",
            "团建活动": "gathering",
            "医疗检查": "medical",
            "晚餐约会": "date",
            "英语上课": "class",
            "面试通知": "interview",
            "随便写写": "default",
        }
        for index, (title, expected) in enumerate(cases.items()):
            key = f"s{index}"
            sched._store._schedules[key] = {"title": title, "reminder_offset_min": 15}
            sched.record_feedback(key, "complete")
            assert expected in sched._offset_learning, f"{title} 未归类到 {expected}"


class TestRecurrenceParsing:
    """RFC 5545 规则解析。"""

    def test_parse_weekly_with_byday(self):
        rule = RecurrenceEngine().parse_rule("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE")
        assert rule["freq"] == "WEEKLY"
        assert rule["interval"] == 2
        assert rule["byday"] == ["MO", "WE"]

    def test_interval_defaults_to_one(self):
        assert RecurrenceEngine().parse_rule("FREQ=DAILY")["interval"] == 1

    def test_empty_rule_is_safe(self):
        assert RecurrenceEngine().parse_rule("")["interval"] == 1

    def test_to_rule_string_roundtrip(self):
        engine = RecurrenceEngine()
        text = engine.to_rule_string("WEEKLY", interval=1, byday=["MO", "FR"])
        parsed = engine.parse_rule(text)
        assert parsed["freq"] == "WEEKLY"
        assert parsed["interval"] == 1
        assert parsed["byday"] == ["MO", "FR"]


class TestRecurrenceDates:
    """日期生成。"""

    def _engine(self):
        return RecurrenceEngine()

    def test_daily_skips_first_day(self):
        """首次日程已单独存在，生成器跳过第一天。"""
        engine = self._engine()
        start = datetime(2026, 1, 1, 9, 0)
        dates = engine.generate_dates(start, start + timedelta(hours=1),
                                      "FREQ=DAILY", window_months=1)
        assert dates, "应生成后续日期"
        assert dates[0] == start + timedelta(days=1)
        assert all(d.hour == 9 and d.minute == 0 for d in dates)

    def test_daily_interval(self):
        engine = self._engine()
        start = datetime(2026, 1, 1, 9, 0)
        dates = engine.generate_dates(start, start, "FREQ=DAILY;INTERVAL=3",
                                      window_months=1)
        assert dates[0] == start + timedelta(days=3)
        assert dates[1] == start + timedelta(days=6)

    def test_weekly_uses_start_weekday_when_no_byday(self):
        engine = self._engine()
        start = datetime(2026, 1, 5, 8, 0)          # 2026-01-05 是周一
        dates = engine.generate_dates(start, start, "FREQ=WEEKLY", window_months=1)
        assert dates
        assert all(d.weekday() == start.weekday() for d in dates)

    def test_weekly_byday_selection(self):
        """BYDAY 指定多个星期时，所有实例都应落在这些星期上。"""
        engine = self._engine()
        start = datetime(2026, 1, 5, 8, 0)          # 周一
        dates = engine.generate_dates(start, start, "FREQ=WEEKLY;BYDAY=MO,WE",
                                      window_months=1)
        assert dates
        assert all(d.weekday() in (0, 2) for d in dates)

    def test_unsupported_freq_returns_empty(self):
        engine = self._engine()
        start = datetime(2026, 1, 1, 9, 0)
        assert engine.generate_dates(start, start, "FREQ=HOURLY") == []

    def test_monthly_falls_back_to_start_day(self):
        engine = self._engine()
        start = datetime(2026, 1, 15, 9, 0)
        dates = engine.generate_dates(start, start, "FREQ=MONTHLY", window_months=2)
        assert dates
        assert all(d.day == 15 for d in dates)

    def test_unknown_byday_falls_back_to_start_weekday(self):
        """非法星期缩写应回退到起始日星期，而不是生成空列表。"""
        engine = self._engine()
        start = datetime(2026, 1, 5, 8, 0)
        dates = engine.generate_dates(start, start, "FREQ=WEEKLY;BYDAY=XX",
                                      window_months=1)
        assert dates
        assert all(d.weekday() == start.weekday() for d in dates)
