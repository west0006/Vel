"""GreetingService 单元测试。

核心验收：`check_and_greet()` 在**网络极慢时也必须立即返回** ——
它由 UI 回调链直接调用（点击桌宠 → 展开气泡），此前含两个同步网络调用
（天气 timeout=3、模型推理 timeout=10），会卡住界面数秒。
"""

import time

import pytest
import requests

from core.service_registry import registry
from modules.greeting import (
    GREETING_TIMEOUT,
    WEATHER_CACHE_KEY,
    WEATHER_URL,
    GreetingService,
)
from utils.remote_text import remote_text


@pytest.fixture
def no_context(monkeypatch):
    """剥离所有外部依赖（数据库 / LLM / 画像），并阻断真实网络。"""
    monkeypatch.setattr(registry, "get", lambda name: None)
    # 避免 _collect_context 触发的后台天气刷新真的发请求（测试不应依赖外网）
    monkeypatch.setattr(remote_text, "refresh", lambda key, url: True)
    remote_text.clear()
    return monkeypatch


class TestNoUIBlocking:
    """UI 线程阻塞回归（本模块最重要的保障）。"""

    def test_returns_promptly_when_network_hangs(self, no_context):
        """把网络调用改成"睡 2 秒"，check_and_greet 仍须立即返回。"""

        def _hanging(*args, **kwargs):
            time.sleep(2.0)
            raise requests.Timeout("hang")

        no_context.setattr(requests, "get", _hanging)
        no_context.setattr(requests, "post", _hanging)

        service = GreetingService()
        started = time.time()
        message = service.check_and_greet()
        elapsed = time.time() - started

        assert elapsed < 0.5, f"check_and_greet 阻塞了 {elapsed:.2f}s（应 < 0.5s）"
        assert message, "仍应给出降级问候"

    def test_weather_failure_does_not_block(self, no_context):
        """天气拉取失败时，问候语照常返回（只是不含天气）。"""
        no_context.setattr(requests, "get",
                           lambda *a, **k: (_ for _ in ()).throw(requests.Timeout()))
        service = GreetingService()
        started = time.time()
        assert service.check_and_greet()
        assert time.time() - started < 0.5


class TestWeatherCache:
    """天气只读缓存。"""

    def test_uses_cached_weather(self, no_context):
        remote_text.put(WEATHER_CACHE_KEY, "☀️ +22°C")
        ctx = GreetingService()._collect_context()
        assert ctx["weather"] == "☀️ +22°C"

    def test_empty_cache_leaves_weather_blank(self, no_context):
        ctx = GreetingService()._collect_context()
        assert ctx["weather"] == ""

    def test_get_triggers_background_prefetch(self, no_context):
        """未命中时应触发后台刷新（而非同步等待）。"""
        no_context.setattr(requests, "get", lambda *a, **k: None)
        calls = []
        no_context.setattr(remote_text, "refresh",
                           lambda key, url: calls.append(key) or True)
        GreetingService()._collect_context()
        assert calls == [WEATHER_CACHE_KEY]


class TestGreetingGeneration:
    """问候语生成策略：缓存优先、未命中降级模板 + 后台生成。"""

    def _ctx(self):
        return {"period": "早上", "nickname": "小明", "weather": "", "mood": ""}

    def test_template_when_no_llm(self, no_context):
        service = GreetingService()
        assert service._generate(self._ctx()) == service._template(self._ctx())

    def test_cache_hit_returned_directly(self, no_context):
        no_context.setattr(registry, "get", lambda name: object() if name == "llm_service" else None)
        service = GreetingService()
        ctx = self._ctx()
        service._greeting_cache[service._cache_key(ctx)] = "缓存里的问候"
        assert service._generate(ctx) == "缓存里的问候"

    def test_miss_returns_template_and_spawns_background(self, no_context):
        no_context.setattr(registry, "get", lambda name: object() if name == "llm_service" else None)
        service = GreetingService()
        spawned = []
        no_context.setattr(service, "_spawn_generation",
                           lambda key, ctx: spawned.append(key) or True)
        ctx = self._ctx()
        assert service._generate(ctx) == service._template(ctx)
        assert spawned == [service._cache_key(ctx)]

    def test_cache_key_includes_date_and_period(self, no_context):
        service = GreetingService()
        ctx = self._ctx()
        key = service._cache_key(ctx)
        assert "早上" in key and key.count(":") == 1

    def test_session_dedupes_background_generation(self, no_context):
        """同一 key 不应重复起线程（首次生成在途时，第二次应被拒绝）。"""
        service = GreetingService()
        ctx = self._ctx()

        def _slow_generate(_ctx):
            time.sleep(0.3)          # 制造"在途"状态
            return "生成结果"

        no_context.setattr(service, "_llm_generate", _slow_generate)
        key = service._cache_key(ctx)
        assert service._spawn_generation(key, ctx) is True
        assert service._spawn_generation(key, ctx) is False   # 在途去重
        deadline = time.time() + 2
        while time.time() < deadline and service._greeting_cache.get(key) is None:
            time.sleep(0.01)
        assert service._greeting_cache.get(key) == "生成结果"

    def test_prewarm_skipped_without_llm(self, no_context):
        service = GreetingService()
        spawned = []
        no_context.setattr(service, "_spawn_generation", lambda k, c: spawned.append(1))
        service.prewarm()
        assert spawned == []

    def test_prewarm_spawns_when_llm_present(self, no_context):
        no_context.setattr(registry, "get", lambda name: object() if name == "llm_service" else None)
        service = GreetingService()
        spawned = []
        no_context.setattr(service, "_spawn_generation",
                           lambda key, ctx: spawned.append(key) or True)
        service.prewarm()
        assert len(spawned) == 1


class TestPromptBuilding:
    """提示词拼装。"""

    def test_includes_weather_and_mood_when_present(self, no_context):
        service = GreetingService()
        ctx = {"period": "晚上", "nickname": "小明", "weather": "☀️ 22°C", "mood": "开心"}
        prompt = service._build_prompt(ctx)
        assert "晚上" in prompt and "小明" in prompt
        assert "☀️ 22°C" in prompt and "开心" in prompt

    def test_omits_missing_fields(self, no_context):
        service = GreetingService()
        ctx = {"period": "早上", "nickname": "用户", "weather": "", "mood": ""}
        prompt = service._build_prompt(ctx)
        assert "天气" not in prompt and "心情" not in prompt

    def test_config_constants_sane(self):
        assert WEATHER_URL.startswith("https://")
        assert 0 < GREETING_TIMEOUT <= 30
