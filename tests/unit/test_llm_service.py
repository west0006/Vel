"""LLMService 单元测试。

重点覆盖**降级链**（失败计数 → 降级 → 恢复探测）与预设回复轮换 ——
这类逻辑出错会"静默降级"，用户只看到桌宠变傻却无任何报错。

另含 2026-10-08 修复的缺陷回归：降级后必须能自动恢复（此前永不恢复）。
"""

import pytest

from services.llm_service import LLMService


def _failing_service(**kwargs):
    """构造一个底层调用必失败的服务实例。"""
    svc = LLMService(**kwargs)

    def _boom(messages):
        raise RuntimeError("ollama down")

    svc._call_ollama = _boom          # type: ignore[assignment]
    return svc


def _healthy_service(reply="hello"):
    """构造一个底层调用必成功的服务实例。"""
    svc = LLMService()
    svc._call_ollama = lambda messages: reply   # type: ignore[assignment]
    return svc


class TestFallbackReplies:
    """预设回复轮换。"""

    def test_rotates_cyclically(self):
        svc = LLMService(fallback_replies=["A", "B", "C"])
        assert [svc._get_fallback_reply() for _ in range(4)] == ["A", "B", "C", "A"]

    def test_default_replies_available(self):
        svc = LLMService()
        assert svc._get_fallback_reply()


class TestFailureDegradation:
    """连续失败 → 降级。"""

    def test_single_failure_does_not_degrade(self):
        svc = _failing_service()
        reply = svc.generate("hi")
        assert svc._is_degraded is False
        assert svc._consecutive_failures == 1
        assert reply in svc._fallback_replies

    def test_degrades_after_threshold(self):
        svc = _failing_service()
        for _ in range(svc._max_failures_before_degrade):
            svc.generate("hi")
        assert svc._is_degraded is True
        assert svc._consecutive_failures == svc._max_failures_before_degrade

    def test_degraded_uses_fallback_without_calling_backend(self):
        """降级期间（未到探测点）不应再调用底层。"""
        svc = _failing_service()
        called = []
        svc._call_ollama = lambda m: called.append(1) or "x"   # type: ignore[assignment]
        svc._is_degraded = True
        reply = svc.generate("hi")
        assert called == []
        assert reply in svc._fallback_replies

    def test_history_records_both_sides(self):
        """降级回复也要入历史，否则上下文断裂。"""
        svc = _failing_service()
        svc.generate("你好")
        history = svc.get_history()
        assert [h["role"] for h in history] == ["user", "assistant"]


class TestRecoveryProbe:
    """2026-10-08 缺陷修复：降级后必须能自动恢复。"""

    def test_probe_interval_reaches_backend(self):
        """降级后第 _degrade_probe_interval 次应重新尝试真实调用。"""
        svc = _healthy_service(reply="recovered")
        svc._is_degraded = True
        attempts = []
        svc._call_ollama = lambda m: attempts.append(1) or "recovered"   # type: ignore[assignment]

        for _ in range(svc._degrade_probe_interval - 1):
            svc.generate("hi")
        assert attempts == [], "未到探测点不应调用底层"

        reply = svc.generate("hi")          # 第 N 次 → 触发探测
        assert attempts == [1]
        assert reply == "recovered"

    def test_recovers_and_exits_degrade_mode(self):
        """探测成功 → 退出降级模式并开始正常回复。"""
        svc = _healthy_service(reply="ok")
        svc._is_degraded = True
        svc._degrade_probe_counter = svc._degrade_probe_interval - 1
        svc.generate("hi")
        assert svc._is_degraded is False
        assert svc._consecutive_failures == 0

    def test_probe_failure_keeps_degraded_and_resets_counter(self):
        """探测失败 → 继续降级，计数器归零（下个周期再试）。"""
        svc = _failing_service()
        svc._is_degraded = True
        svc._degrade_probe_counter = svc._degrade_probe_interval - 1
        reply = svc.generate("hi")
        assert svc._is_degraded is True
        assert svc._degrade_probe_counter == 0
        assert reply in svc._fallback_replies


class TestHealthyPath:
    """正常路径。"""

    def test_success_resets_failure_counter(self):
        svc = _healthy_service(reply="ok")
        svc._consecutive_failures = 2
        reply = svc.generate("hi")
        assert reply == "ok"
        assert svc._consecutive_failures == 0
        assert svc._is_degraded is False

    def test_no_degrade_marker_when_healthy(self):
        svc = _healthy_service()
        svc.generate("hi")
        assert svc._degrade_probe_counter == 0


class TestConfiguration:
    """构造参数与配置读取。"""

    def test_custom_model_and_limits(self):
        svc = LLMService(model="m", host="h", port=1234, timeout=9, max_tokens=99)
        assert svc.base_url == "http://h:1234"
        assert svc.model == "m"
        assert svc.timeout == 9
        assert svc.max_tokens == 99

    def test_context_window_trimming(self):
        """上下文窗口按轮数算，一轮 = user + assistant，故保留上限为 2×窗口。"""
        svc = LLMService(context_window=2)
        for index in range(6):
            svc.add_to_history("user", f"m{index}")
        assert len(svc.get_history()) <= 2 * 2
        # 保留的应是最新的
        assert svc.get_history()[-1]["content"] == "m5"

    def test_clear_history(self):
        svc = LLMService()
        svc.add_to_history("user", "x")
        svc.clear_history()
        assert svc.get_history() == []

    def test_system_prompt_injection(self):
        svc = LLMService()
        svc.set_user_name("小明")
        svc.set_system_prompt("你是测试角色")
        messages = svc._build_messages()
        assert messages[0]["role"] == "system"
        assert "测试角色" in messages[0]["content"]
