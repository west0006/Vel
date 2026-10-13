"""事件总线跨模块投递集成测试。

验证三种订阅模式的**线程语义** —— 这是 EventBus 的核心契约：
`AGENTS.md` §4.3 要求「任何非主线程绝对不可直接操作 UI 控件」，
而该约束正是靠 `subscribe_ui` 的 Qt 队列投递来保证的。
"""

import threading
import time

import pytest

from core.event_bus import EventBus


@pytest.fixture
def bus():
    """独立 EventBus 实例（隔离全局 bus，避免影响其他测试）。"""
    instance = EventBus()
    yield instance
    instance.shutdown(wait=False)


class TestSyncDelivery:
    """同步订阅者：在发布线程内立即执行。"""

    def test_callback_runs_in_publishing_thread(self, bus):
        seen = []
        bus.subscribe_sync("evt", lambda d: seen.append((d, threading.get_ident())))
        bus.publish("evt", 42)
        assert seen == [(42, threading.get_ident())]

    def test_publish_without_subscribers_is_safe(self, bus):
        bus.publish("nobody-listens", {"x": 1})


class TestAsyncDelivery:
    """异步订阅者：在线程池执行。"""

    def test_runs_off_publishing_thread(self, bus):
        done = threading.Event()
        seen = {}

        def callback(data):
            seen["tid"] = threading.get_ident()
            seen["data"] = data
            done.set()

        bus.subscribe_async("evt", callback)
        bus.publish("evt", "payload")
        assert done.wait(3), "异步回调未在 3s 内执行"
        assert seen["tid"] != threading.get_ident()
        assert seen["data"] == "payload"


class TestUiDelivery:
    """UI 订阅者：必须经 Qt 队列投递回**主线程**。"""

    def test_worker_thread_publish_reaches_main_thread(self, bus, qt_app):
        seen = {}
        bus.subscribe_ui(
            "evt", lambda d: seen.update(tid=threading.get_ident(), data=d))

        def worker():
            bus.publish("evt", "from-worker")

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(3)

        for _ in range(50):                 # 驱动事件循环，让 QueuedConnection 投递
            qt_app.processEvents()
            if "data" in seen:
                break
            time.sleep(0.01)

        assert seen.get("data") == "from-worker"
        assert seen.get("tid") == threading.get_ident(), "UI 回调未在主线程执行"


class TestMultipleSubscribers:
    """多种订阅模式共存。"""

    def test_all_modes_receive_event(self, bus, qt_app):
        received = {"sync": 0, "async": 0, "ui": 0}

        def on_sync(_data):
            received["sync"] += 1

        def on_async(_data):
            received["async"] += 1

        def on_ui(_data):
            received["ui"] += 1

        bus.subscribe_sync("evt", on_sync)
        bus.subscribe_async("evt", on_async)
        bus.subscribe_ui("evt", on_ui)
        bus.publish("evt", None)

        for _ in range(50):
            qt_app.processEvents()
            if all(received.values()):
                break
            time.sleep(0.01)
        assert received == {"sync": 1, "async": 1, "ui": 1}

    def test_unsubscribe_stops_delivery(self, bus):
        calls = []
        callback = lambda d: calls.append(d)          # noqa: E731
        bus.subscribe_sync("evt", callback)
        bus.publish("evt", 1)
        assert bus.unsubscribe("evt", callback) is True
        bus.publish("evt", 2)
        assert calls == [1]

    def test_unsubscribe_unknown_returns_false(self, bus):
        assert bus.unsubscribe("evt", lambda d: None) is False


class TestErrorIsolation:
    """事件总线必须容错：单个订阅者异常不得影响其他订阅者。"""

    def test_sync_exception_does_not_block_others(self, bus):
        calls = []

        def boom(_data):
            raise RuntimeError("subscriber failure")

        bus.subscribe_sync("evt", boom)
        bus.subscribe_sync("evt", lambda d: calls.append(d))
        bus.publish("evt", "ok")                      # 不应向外抛出
        assert calls == ["ok"]

    def test_ui_exception_does_not_block_others(self, bus, qt_app):
        calls = []

        def boom(_data):
            raise RuntimeError("ui subscriber failure")

        bus.subscribe_ui("evt", boom)
        bus.subscribe_ui("evt", lambda d: calls.append(d))
        bus.publish("evt", "ok")

        for _ in range(50):
            qt_app.processEvents()
            if calls:
                break
            time.sleep(0.01)
        assert calls == ["ok"]
