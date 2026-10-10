"""SearchService 单元测试。

重点覆盖**降级链**（DDG 库 → Bing → SearXNG → DDG HTML）与 Bing 的各类降级触发条件 ——
这些逻辑出错会"静默降级"，用户只看到搜索结果变差却无任何报错。
"""

import pytest
import requests

from services.search_service import SearchService


@pytest.fixture
def svc(monkeypatch):
    """构造一个已隔离缓存与网络的服务实例。"""
    service = SearchService()
    service._degraded_to_duckduckgo = False
    monkeypatch.setattr(service, "_check_cache", lambda query: None)
    monkeypatch.setattr(service, "_save_cache", lambda query, result: None)
    return service


class TestFallbackChain:
    """降级链的先后顺序（实现约定：DDG 库为主通道，Bing 仅在库失败时尝试）。"""

    def test_duckduckgo_lib_is_primary(self, svc, monkeypatch):
        """DDG 库命中即返回，且**不**调用 Bing。"""
        bing_calls = []
        monkeypatch.setattr(svc, "_search_duckduckgo_lib", lambda q, n: "lib-result")
        monkeypatch.setattr(svc, "_search_bing", lambda q, n: bing_calls.append(1))
        assert svc.search("query") == "lib-result"
        assert bing_calls == []

    def test_bing_used_when_lib_fails(self, svc, monkeypatch):
        monkeypatch.setattr(svc, "_search_duckduckgo_lib", lambda q, n: None)
        monkeypatch.setattr(svc, "_search_bing", lambda q, n: "bing-result")
        assert svc.search("query") == "bing-result"

    def test_searxng_after_bing_fails(self, svc, monkeypatch):
        monkeypatch.setattr(svc, "_search_duckduckgo_lib", lambda q, n: None)
        monkeypatch.setattr(svc, "_search_bing", lambda q, n: None)
        monkeypatch.setattr(svc, "_search_searxng", lambda q, n: "searxng-result")
        assert svc.search("query") == "searxng-result"

    def test_duckduckgo_html_is_last_resort(self, svc, monkeypatch):
        monkeypatch.setattr(svc, "_search_duckduckgo_lib", lambda q, n: None)
        monkeypatch.setattr(svc, "_search_bing", lambda q, n: None)
        monkeypatch.setattr(svc, "_search_searxng", lambda q, n: None)
        monkeypatch.setattr(svc, "_search_duckduckgo", lambda q, n: "html-result")
        assert svc.search("query") == "html-result"

    def test_bing_skipped_when_degraded(self, svc, monkeypatch):
        """已降级时不再尝试 Bing，直接走 SearXNG。"""
        bing_calls = []
        svc._degraded_to_duckduckgo = True
        monkeypatch.setattr(svc, "_search_duckduckgo_lib", lambda q, n: None)
        monkeypatch.setattr(svc, "_search_bing", lambda q, n: bing_calls.append(1))
        monkeypatch.setattr(svc, "_search_searxng", lambda q, n: "searxng")
        assert svc.search("query") == "searxng"
        assert bing_calls == []

    def test_all_channels_fail_returns_friendly_message(self, svc, monkeypatch):
        for name in ("_search_duckduckgo_lib", "_search_bing",
                     "_search_searxng", "_search_duckduckgo"):
            monkeypatch.setattr(svc, name, lambda q, n: None)
        result = svc.search("query")
        assert "暂不可用" in result

    def test_blank_query_returns_empty(self, svc):
        assert svc.search("   ") == ""


class TestBingDegradation:
    """Bing 通道的降级触发条件。"""

    def test_no_key_returns_none_without_degrading(self, svc):
        """未配置 key（如密钥文件缺失）只跳过 Bing，不算"降级"。"""
        svc._bing_key = ""
        assert svc._search_bing("query") is None
        assert svc._degraded_to_duckduckgo is False

    def test_quota_exhausted_degrades(self, svc, monkeypatch):
        svc._bing_key = "k" * 32
        monkeypatch.setattr(svc, "_check_bing_quota", lambda: False)
        assert svc._search_bing("query") is None
        assert svc._degraded_to_duckduckgo is True

    def test_auth_failure_degrades_permanently(self, svc, monkeypatch):
        """401/403 表示 key 失效 → 永久降级，不再重试。"""
        svc._bing_key = "k" * 32
        monkeypatch.setattr(svc, "_check_bing_quota", lambda: True)

        class _Resp:
            status_code = 401

        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
        assert svc._search_bing("query") is None
        assert svc._degraded_to_duckduckgo is True

    def test_timeout_skips_without_permanent_degrade(self, svc, monkeypatch):
        """超时是临时故障，只跳过本次，不应永久降级。"""
        svc._bing_key = "k" * 32
        monkeypatch.setattr(svc, "_check_bing_quota", lambda: True)

        def _raise(*args, **kwargs):
            raise requests.Timeout("timeout")

        monkeypatch.setattr(requests, "get", _raise)
        assert svc._search_bing("query") is None
        assert svc._degraded_to_duckduckgo is False

    def test_other_http_error_skips_without_degrading(self, svc, monkeypatch):
        svc._bing_key = "k" * 32
        monkeypatch.setattr(svc, "_check_bing_quota", lambda: True)

        class _Resp:
            status_code = 500

        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
        assert svc._search_bing("query") is None
        assert svc._degraded_to_duckduckgo is False

    def test_success_returns_formatted_results(self, svc, monkeypatch):
        svc._bing_key = "k" * 32
        monkeypatch.setattr(svc, "_check_bing_quota", lambda: True)
        monkeypatch.setattr(svc, "_filter_safe", lambda results: results)
        monkeypatch.setattr(svc, "_quality_check", lambda results: True)
        monkeypatch.setattr(svc, "_format_results", lambda results: "formatted")

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"webPages": {"value": [{"name": "n", "url": "u", "snippet": "s"}]}}

        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
        assert svc._search_bing("query") == "formatted"

    def test_low_quality_results_rejected(self, svc, monkeypatch):
        """结果质量不足时不采用（但也不永久降级）。"""
        svc._bing_key = "k" * 32
        monkeypatch.setattr(svc, "_check_bing_quota", lambda: True)
        monkeypatch.setattr(svc, "_filter_safe", lambda results: results)
        monkeypatch.setattr(svc, "_quality_check", lambda results: False)

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"webPages": {"value": [{"name": "n"}]}}

        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
        assert svc._search_bing("query") is None
        assert svc._degraded_to_duckduckgo is False


class TestInitialState:
    """初始状态与配置读取。"""

    def test_defaults_from_config(self, svc):
        assert svc._bing_timeout > 0
        assert svc._bing_monthly_limit > 0
        assert svc._degraded_to_duckduckgo is False

    def test_search_raw_returns_empty_on_failure(self, svc, monkeypatch):
        monkeypatch.setattr(svc, "search", lambda q, n=5: "搜索服务暂不可用，请稍后重试 😿")
        assert svc.search_raw("query") == []

    def test_search_raw_wraps_text_result(self, svc, monkeypatch):
        monkeypatch.setattr(svc, "search", lambda q, n=5: "some result text")
        raw = svc.search_raw("query")
        assert raw and raw[0]["snippet"].startswith("some result")
