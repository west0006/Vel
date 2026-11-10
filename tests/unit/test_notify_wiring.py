"""NOTIFY-1 通知接线单元测试。

覆盖：三条提醒事件的 UI 订阅、通知 payload、id 唯一化、按钮回调，
以及 N2 的日程 advance/due id 区分。
"""

from datetime import date

import main
from ui.notification_bubble import TYPE_BORDER, TYPE_ICON


class _FakeNotificationManager:
    def __init__(self):
        self.items = []

    def push(self, item):
        self.items.append(item)


class _FakePet:
    def __init__(self):
        self.tips = []

    def show_tip(self, text, duration_ms=3000):
        self.tips.append(text)


class _FakeRegistry:
    def __init__(self, services=None):
        self._services = services or {}

    def get(self, name, default=None):
        return self._services.get(name, default)


class _FakeBus:
    def __init__(self):
        self.subscriptions = []

    def subscribe_ui(self, event, callback):
        self.subscriptions.append((event, callback))


def _app():
    app = main.VelApplication.__new__(main.VelApplication)
    app._notification_manager = _FakeNotificationManager()
    app._floating_pet = _FakePet()
    return app


class TestEventSubscriptions:
    def test_three_reminder_events_are_subscribed(self, monkeypatch):
        fake_bus = _FakeBus()
        monkeypatch.setattr(main, "bus", fake_bus)

        app = _app()
        app._chat_bubble = type("FakeChat", (), {"show_context_hint": lambda self, text: None})()
        app._init_event_listeners()

        events = [event for event, _ in fake_bus.subscriptions]
        assert main.EVENT_HABIT_REMINDER in events
        assert main.EVENT_MEMO_REMINDER in events
        assert main.EVENT_POMODORO_END in events


class TestHabitNotification:
    def test_payload_and_checkin_callback(self, monkeypatch):
        class FakeHabit:
            def __init__(self):
                self.checked = []

            def check_in(self, hid):
                self.checked.append(hid)
                return {"streak": 3}

        habit = FakeHabit()
        monkeypatch.setattr(
            main, "registry", _FakeRegistry({"habit_manager": habit})
        )

        app = _app()
        app._on_habit_reminder({"habit_id": "h1", "name": "喝水"})

        item = app._notification_manager.items[0]
        assert item["id"] == f"habit_h1_{date.today().isoformat()}"
        assert item["message"] == "该完成「喝水」啦~"
        assert item["notif_type"] == "habit"
        assert item["buttons"][0][1] == "checkin"

        item["on_action"]("checkin")
        assert habit.checked == ["h1"]
        assert "连续 3 天" in app._floating_pet.tips[-1]

    def test_already_checked_in_feedback(self, monkeypatch):
        class FakeHabit:
            def check_in(self, hid):
                return {"streak": 3, "already": True}

        monkeypatch.setattr(
            main, "registry", _FakeRegistry({"habit_manager": FakeHabit()})
        )

        app = _app()
        app._on_habit_reminder({"habit_id": "h1", "name": "喝水"})
        app._notification_manager.items[0]["on_action"]("checkin")
        assert "已经打卡" in app._floating_pet.tips[-1]


class TestMemoNotification:
    def test_payload_and_done_callback(self, monkeypatch):
        class FakeMemo:
            def __init__(self):
                self.done = []

            def mark_done(self, memo_id):
                self.done.append(memo_id)
                return True

        memo = FakeMemo()
        monkeypatch.setattr(
            main, "registry", _FakeRegistry({"memo_manager": memo})
        )

        app = _app()
        app._on_memo_reminder(
            {
                "memo_id": "m1",
                "content": "买牛奶",
                "timestamp": "2026-11-10T12:00:00",
            }
        )

        item = app._notification_manager.items[0]
        assert item["id"] == "memo_m1_2026-11-10T12:00:00"
        assert item["message"] == "买牛奶"
        assert item["notif_type"] == "memo"

        item["on_action"]("done")
        assert memo.done == ["m1"]

    def test_id_differs_for_two_firings(self, monkeypatch):
        monkeypatch.setattr(main, "registry", _FakeRegistry())
        app = _app()
        app._on_memo_reminder({"memo_id": "m1", "content": "a", "timestamp": "t1"})
        app._on_memo_reminder({"memo_id": "m1", "content": "a", "timestamp": "t2"})

        ids = [item["id"] for item in app._notification_manager.items]
        assert ids == ["memo_m1_t1", "memo_m1_t2"]


class TestPomodoroNotification:
    def test_focus_end_payload(self, monkeypatch):
        monkeypatch.setattr(main, "registry", _FakeRegistry())
        app = _app()
        app._on_pomodoro_end({"stage": "focus_end", "break_min": 5})

        item = app._notification_manager.items[0]
        assert item["id"].startswith("pomodoro_focus_end_")
        assert "休息 5 分钟" in item["message"]
        assert item["notif_type"] == "pomodoro"

    def test_break_end_starts_next_round(self, monkeypatch):
        class FakePomodoro:
            def __init__(self):
                self.started = 0

            def start(self):
                self.started += 1

        pomodoro = FakePomodoro()
        monkeypatch.setattr(
            main, "registry", _FakeRegistry({"pomodoro_timer": pomodoro})
        )

        app = _app()
        app._on_pomodoro_end({"stage": "break_end"})
        app._notification_manager.items[0]["on_action"]("start")
        assert pomodoro.started == 1

    def test_unknown_stage_ignored(self, monkeypatch):
        monkeypatch.setattr(main, "registry", _FakeRegistry())
        app = _app()
        app._on_pomodoro_end({"stage": "unknown"})
        assert app._notification_manager.items == []

    def test_notification_type_is_registered(self):
        assert "pomodoro" in TYPE_BORDER
        assert "pomodoro" in TYPE_ICON


class TestScheduleNotificationIds:
    def test_advance_and_due_have_distinct_ids(self, monkeypatch):
        monkeypatch.setattr(main, "registry", _FakeRegistry())
        app = _app()

        app._on_schedule_alert(
            {"stage": "advance", "schedule_id": "s1", "title": "会议"}
        )
        app._on_schedule_alert(
            {"stage": "due", "schedule_id": "s1", "title": "会议"}
        )

        ids = [item["id"] for item in app._notification_manager.items]
        assert ids == ["schedule_s1_advance", "schedule_s1_due"]
