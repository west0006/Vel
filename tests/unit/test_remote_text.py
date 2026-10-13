"""utils/remote_text.py 单元测试。

覆盖：缓存命中/未命中/过期、后台刷新（含并发去重）、网络失败不破坏旧值、
非 200 与空响应不写入、批量预热跳过未过期项。
"""

import time

import pytest
import requests

from utils.remote_text import RemoteTextCache


def _wait(predicate, timeout=2.0):
    """轮询等待条件成立（后台线程是 daemon thread，需等待）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _Resp:
    def __init__(self, text="sunny 25C", status=200):
        self.text = text
        self.status_code = status


class TestBasicCaching:
    """基本缓存语义。"""

    def test_miss_returns_none(self):
        """未命中必须返回 None 而不是阻塞等待。"""
        assert RemoteTextCache().get("k") is None

    def test_put_then_get(self):
        cache = RemoteTextCache()
        cache.put("k", "v")
        assert cache.get("k") == "v"

    def test_expired_entry_miss(self):
        cache = RemoteTextCache(ttl_seconds=1)
        cache.put("k", "v")
        with cache._lock:                       # 把时间戳推回过去
            cache._cache["k"] = (time.time() - 60, "v")
        assert cache.get("k") is None
        assert cache.peek("k") == "v"           # 旧值仍在，只是视为过期

    def test_clear(self):
        cache = RemoteTextCache()
        cache.put("k", "v")
        cache.clear()
        assert cache.get("k") is None
        assert cache.peek("k") is None


class TestStaleness:
    def test_missing_is_stale(self):
        assert RemoteTextCache().is_stale("k") is True

    def test_fresh_is_not_stale(self):
        cache = RemoteTextCache()
        cache.put("k", "v")
        assert cache.is_stale("k") is False


class TestRefresh:
    """后台刷新。"""

    def test_refresh_populates_cache(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp("sunny 25C"))
        cache = RemoteTextCache()
        assert cache.refresh("weather", "http://example.test") is True
        assert _wait(lambda: cache.peek("weather") == "sunny 25C")
        assert cache.get("weather") == "sunny 25C"

    def test_get_triggers_background_refresh(self, monkeypatch):
        """首次 get 返回 None（不阻塞），后台填充后二次 get 命中。"""
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp("cloudy"))
        cache = RemoteTextCache()
        started = time.time()
        assert cache.get("weather", "http://example.test") is None
        assert time.time() - started < 0.2, "get 不应阻塞"
        assert _wait(lambda: cache.peek("weather") == "cloudy")
        assert cache.get("weather") == "cloudy"

    def test_concurrent_refresh_deduped(self, monkeypatch):
        """同一 key 的在途请求应去重，避免并发重复拉取。"""
        calls = []

        def _slow(*args, **kwargs):
            calls.append(1)
            time.sleep(0.15)
            return _Resp()

        monkeypatch.setattr(requests, "get", _slow)
        cache = RemoteTextCache()
        assert cache.refresh("k", "u") is True
        assert cache.refresh("k", "u") is False
        assert _wait(lambda: cache.peek("k") is not None)
        assert len(calls) == 1

    def test_network_failure_does_not_cache(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise requests.Timeout("timeout")

        monkeypatch.setattr(requests, "get", _boom)
        cache = RemoteTextCache()
        cache.refresh("k", "u")
        time.sleep(0.2)
        assert cache.peek("k") is None

    def test_failure_keeps_previous_value(self, monkeypatch):
        """刷新失败不应清掉旧缓存（用户仍能看到上次的天气）。"""
        cache = RemoteTextCache()
        cache.put("k", "old")

        def _boom(*args, **kwargs):
            raise requests.Timeout("timeout")

        monkeypatch.setattr(requests, "get", _boom)
        cache.refresh("k", "u")
        time.sleep(0.2)
        assert cache.get("k") == "old"

    def test_non_200_not_cached(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp("err", status=500))
        cache = RemoteTextCache()
        cache.refresh("k", "u")
        time.sleep(0.2)
        assert cache.peek("k") is None

    def test_blank_body_not_cached(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp("   ", status=200))
        cache = RemoteTextCache()
        cache.refresh("k", "u")
        time.sleep(0.2)
        assert cache.peek("k") is None

    def test_pending_cleared_after_failure(self, monkeypatch):
        """失败后必须释放 pending，否则该 key 再也不会重试。"""
        monkeypatch.setattr(requests, "get",
                            lambda *a, **k: (_ for _ in ()).throw(requests.Timeout()))
        cache = RemoteTextCache()
        cache.refresh("k", "u")
        assert _wait(lambda: "k" not in cache._pending)


class TestPrefetch:
    """启动预热。"""

    def test_prefetch_fills_all_keys(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda url, **k: _Resp(f"from {url}"))
        cache = RemoteTextCache()
        cache.prefetch({"a": "http://a", "b": "http://b"})
        assert _wait(lambda: cache.peek("a") and cache.peek("b"))
        assert cache.peek("a") == "from http://a"

    def test_prefetch_skips_fresh_entries(self, monkeypatch):
        calls = []
        monkeypatch.setattr(requests, "get",
                            lambda *a, **k: calls.append(1) or _Resp())
        cache = RemoteTextCache()
        cache.put("a", "cached")
        cache.prefetch({"a": "http://a"})
        time.sleep(0.15)
        assert calls == []
