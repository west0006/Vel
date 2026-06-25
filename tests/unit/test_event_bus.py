"""EventBus 单元测试。"""

import threading
import time
import pytest

from core.event_bus import EventBus, EVENT_SCHEDULE_ALERT, EVENT_HEALTH_REMINDER


class TestEventBus:
    def setup_method(self):
        self.bus = EventBus()

    def test_subscribe_sync_called(self):
        results = []
        self.bus.subscribe_sync("test", lambda d: results.append(d))
        self.bus.publish("test", {"value": 42})
        assert results == [{"value": 42}]

    def test_subscribe_sync_multiple(self):
        r1, r2 = [], []
        self.bus.subscribe_sync("t", lambda d: r1.append(1))
        self.bus.subscribe_sync("t", lambda d: r2.append(2))
        self.bus.publish("t")
        assert r1 == [1] and r2 == [2]

    def test_subscribe_async_runs(self):
        results = []
        event = threading.Event()
        def cb(d):
            results.append(d)
            event.set()
        self.bus.subscribe_async("t", cb)
        self.bus.publish("t", 99)
        event.wait(timeout=3)
        assert 99 in results

    def test_unsubscribe(self):
        results = []
        cb = lambda d: results.append(d)
        self.bus.subscribe_sync("t", cb)
        self.bus.publish("t", 1)
        assert self.bus.unsubscribe("t", cb)
        self.bus.publish("t", 2)
        assert results == [1]

    def test_event_constants_defined(self):
        assert EVENT_SCHEDULE_ALERT == "schedule_alert"
        assert EVENT_HEALTH_REMINDER == "health_reminder"

    def test_publish_no_subscribers_no_error(self):
        self.bus.publish("no_such_event")

    def test_callback_exception_does_not_crash(self):
        def bad_cb(d): raise ValueError("test")
        self.bus.subscribe_sync("t", bad_cb)
        self.bus.publish("t")  # 不应抛出

    def test_async_exception_does_not_crash(self):
        event = threading.Event()
        def bad_cb(d):
            event.set()
            raise ValueError("async fail")
        self.bus.subscribe_async("t", bad_cb)
        self.bus.publish("t")
        event.wait(timeout=3)

    def test_shutdown_stops_async(self):
        self.bus.shutdown(wait=True)
        # publish 后不崩溃
        self.bus.publish("t")