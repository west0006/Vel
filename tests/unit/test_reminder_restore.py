"""习惯 / 备忘录提醒恢复单元测试（N1）。

覆盖：进程重启后从数据库重注册 job；禁用 / 过期 / 无时间项跳过；
重复调用使用 ``replace_existing=True``，不会产生重复 job。
"""

import sqlite3
from datetime import datetime, timedelta

import pytest

from core.service_registry import registry
from modules.habit import HabitManager
from modules.memo import MemoManager

_SCHEMA = """
CREATE TABLE IF NOT EXISTS habit (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    target_time TEXT NOT NULL DEFAULT '21:00',
    streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    total_completions INTEGER DEFAULT 0,
    last_check_date TEXT,
    enabled INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS memo (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    remind_at DATETIME,
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


class _FakeScheduler:
    """只记录 add_job 调用，不启动 APScheduler 线程。

    用 ``jobs`` 字典按 id 存放，模拟真实调度器 ``replace_existing=True`` 的覆盖语义。
    """

    def __init__(self):
        self._scheduler = self
        self.jobs = {}

    def add_job(self, func=None, trigger=None, id=None, replace_existing=False, **kwargs):
        self.jobs[id] = {
            "func": func,
            "trigger": trigger,
            "id": id,
            "replace_existing": replace_existing,
            **kwargs,
        }


@pytest.fixture
def db():
    """内存数据库，只建 habit / memo 两张表。"""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    yield conn
    conn.close()


@pytest.fixture
def scheduler():
    return _FakeScheduler()


@pytest.fixture
def bind_registry(monkeypatch, db, scheduler):
    """把 registry.get 指向内存库与假调度器。"""

    def fake_get(name, default=None):
        if name == "database":
            return db
        if name == "reminder_scheduler":
            return scheduler
        return default

    monkeypatch.setattr(registry, "get", fake_get)
    return scheduler


def _insert_habit(db, hid, name, target_time="21:00", enabled=1):
    db.execute(
        "INSERT INTO habit (id, name, target_time, enabled) VALUES (?, ?, ?, ?)",
        (hid, name, target_time, enabled),
    )
    db.commit()


def _insert_memo(db, memo_id, content, remind_at, status="active"):
    db.execute(
        "INSERT INTO memo (id, content, remind_at, status) VALUES (?, ?, ?, ?)",
        (memo_id, content, remind_at, status),
    )
    db.commit()


class TestHabitRestore:
    def test_registers_only_enabled_habits(self, db, bind_registry):
        _insert_habit(db, "h1", "喝水", "08:30", 1)
        _insert_habit(db, "h2", "阅读", "21:00", 1)
        _insert_habit(db, "h3", "已停用", "07:00", 0)

        assert HabitManager().restore_reminders() == 2
        assert set(bind_registry.jobs) == {"habit_h1", "habit_h2"}
        assert all(job["replace_existing"] for job in bind_registry.jobs.values())

    def test_restore_is_idempotent_for_same_ids(self, db, bind_registry):
        _insert_habit(db, "h1", "喝水", "08:30", 1)

        manager = HabitManager()
        assert manager.restore_reminders() == 1
        assert manager.restore_reminders() == 1
        assert set(bind_registry.jobs) == {"habit_h1"}

    def test_restore_without_habits_returns_zero(self, bind_registry):
        assert HabitManager().restore_reminders() == 0
        assert bind_registry.jobs == {}


class TestMemoRestore:
    def test_registers_only_future_active_memos(self, db, bind_registry):
        future = datetime.now() + timedelta(days=1)
        past = datetime.now() - timedelta(days=1)
        _insert_memo(db, "m1", "买牛奶", future.isoformat())
        _insert_memo(db, "m2", "已过期", past.isoformat())
        _insert_memo(db, "m3", "已完成", future.isoformat(), status="completed")
        _insert_memo(db, "m4", "无时间", None)

        assert MemoManager().restore_reminders() == 1
        assert set(bind_registry.jobs) == {"memo_m1"}
        assert bind_registry.jobs["memo_m1"]["replace_existing"] is True

    def test_accepts_space_separated_datetime(self, db, bind_registry):
        future = datetime.now() + timedelta(days=1)
        _insert_memo(db, "m1", "买牛奶", future.strftime("%Y-%m-%d %H:%M:%S"))

        assert MemoManager().restore_reminders() == 1
        assert "memo_m1" in bind_registry.jobs

    def test_invalid_datetime_is_skipped(self, db, bind_registry):
        _insert_memo(db, "m1", "坏时间", "not-a-datetime")

        assert MemoManager().restore_reminders() == 0
        assert bind_registry.jobs == {}
