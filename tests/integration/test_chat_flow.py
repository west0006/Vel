"""对话端到端集成测试。

使用**真实**的 `ServiceRegistry`、`EventBus`、SQLite schema 与 `ChatManager` 管线，
只对 LLM 打桩（测试环境无 Ollama）。

覆盖主管线的关键分支：彩蛋优先 → 存档 → 记忆召回 → LLM 调用 → 后处理。
"""

import sqlite3
from pathlib import Path

import pytest

from modules.chat.chat_manager import ChatManager

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "schema.sql"


class _FakeLLM:
    """最小 LLMService 替身：固定回复 + 记录系统提示词。"""

    def __init__(self, reply: str = "喵~这是测试回复"):
        self.reply = reply
        self.system_prompt = ""
        self.user_name = "用户"
        self.calls = 0

    # ChatManager 会调用的接口
    def set_system_prompt(self, prompt: str) -> None:
        self.system_prompt = prompt

    def set_user_name(self, name: str) -> None:
        self.user_name = name

    # ChatManager 在清理上下文/读取历史时也会调用这些接口，替身需完整
    def clear_history(self) -> None:
        self.history = []

    def get_history(self) -> list:
        return list(self.history)

    def add_to_history(self, role: str, content: str) -> None:
        self.history.append((role, content))

    def generate(self, user_input: str, memories=None) -> str:
        self.calls += 1
        return self.reply

    def generate_stream(self, user_input: str, memories=None):
        self.calls += 1
        for char in self.reply:
            yield char


def _new_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    return conn


@pytest.fixture
def manager(clean_registry):
    """装配了数据库的 ChatManager（未注册 LLM）。"""
    clean_registry.register("database", _new_db())
    instance = ChatManager()
    instance.initialize()
    return instance


class TestFallbackWithoutLLM:
    """无 LLM 时的降级路径。"""

    def test_returns_fallback_message(self, manager):
        reply = manager.process_message("你好")
        assert "还没准备好" in reply

    def test_both_sides_archived(self, manager, clean_registry):
        manager.process_message("你好")
        db = clean_registry.get("database")
        roles = [row[0] for row in db.execute(
            "SELECT role FROM conversation_archive").fetchall()]
        assert "user" in roles and "assistant" in roles


class TestWithLLM:
    """注册 LLM 后的正常路径。"""

    def test_returns_llm_reply(self, manager, clean_registry):
        clean_registry.register("llm_service", _FakeLLM("喵~收到啦"))
        manager.initialize()
        assert manager.process_message("在吗") == "喵~收到啦"

    def test_system_prompt_injected(self, manager, clean_registry):
        fake = _FakeLLM("好的")
        clean_registry.register("llm_service", fake)
        manager.initialize()
        manager.process_message("你好")
        assert fake.system_prompt, "应向 LLM 注入系统提示词"

    def test_llm_reply_archived(self, manager, clean_registry):
        clean_registry.register("llm_service", _FakeLLM("存档测试"))
        manager.initialize()
        manager.process_message("你好")
        db = clean_registry.get("database")
        contents = [row[0] for row in db.execute(
            "SELECT content FROM conversation_archive").fetchall()]
        assert any("存档测试" in (c or "") for c in contents)

    def test_turn_count_increments(self, manager, clean_registry):
        clean_registry.register("llm_service", _FakeLLM("ok"))
        manager.initialize()
        before = manager.get_turn_count()
        manager.process_message("第一句")
        assert manager.get_turn_count() > before


class TestEasterEggPriority:
    """彩蛋必须短路 LLM 管线。"""

    def test_easter_egg_short_circuits(self, manager, clean_registry):
        class _Egg:
            def match(self, text):
                return {"reply": "🥚 彩蛋回复"} if "彩蛋" in text else None

        clean_registry.register("easter_egg_engine", _Egg())
        fake = _FakeLLM("不应被调用")
        clean_registry.register("llm_service", fake)
        manager.initialize()

        assert manager.process_message("触发彩蛋") == "🥚 彩蛋回复"
        assert fake.calls == 0, "彩蛋命中时不应调用 LLM"

    def test_no_match_falls_through_to_llm(self, manager, clean_registry):
        class _Egg:
            def match(self, text):
                return None

        clean_registry.register("easter_egg_engine", _Egg())
        clean_registry.register("llm_service", _FakeLLM("正常回复"))
        manager.initialize()
        assert manager.process_message("普通消息") == "正常回复"

    def test_easter_egg_pushes_stream_callback(self, manager, clean_registry):
        """彩蛋命中时**必须**经 ``_stream_cb`` 推送文字（V0017 回归）。

        背景：界面（`main.VelApplication`）**只**通过流式回调渲染回复，
        而彩蛋分支原本直接 ``return egg["reply"]``，从不调用回调 →
        用户输入「喵喵喵」后界面完全没有输出，只剩一个"流结束"信号。
        这条测试盯住"命中彩蛋后界面有东西可显示"。
        """
        class _Egg:
            def match(self, text):
                return {"reply": "🥚 喵～你终于说猫话了"} if "喵" in text else None

        clean_registry.register("easter_egg_engine", _Egg())
        manager.initialize()

        received: list = []
        manager.set_stream_callback(received.append)
        reply = manager.process_message("喵喵喵")

        assert reply == "🥚 喵～你终于说猫话了"
        assert received == ["🥚 喵～你终于说猫话了"], (
            "彩蛋回复必须推送到流式回调，否则界面无任何输出"
        )

    def test_easter_egg_without_callback_is_safe(self, manager, clean_registry):
        """未注册流式回调时（如单元测/无界面场景）不得抛异常。"""
        class _Egg:
            def match(self, text):
                return {"reply": "彩蛋"} if "蛋" in text else None

        clean_registry.register("easter_egg_engine", _Egg())
        manager.initialize()
        assert manager.process_message("彩蛋") == "彩蛋"


class TestResilience:
    """依赖缺失/异常时不得崩溃。"""

    def test_missing_optional_services_is_safe(self, manager):
        """未注册 memory/extractor/mood_logger/profile_manager 也应正常工作。"""
        assert manager.process_message("测试")      # 不抛异常

    def test_llm_exception_degrades_gracefully(self, manager, clean_registry):
        class _BrokenLLM(_FakeLLM):
            def generate_stream(self, user_input, memories=None):
                raise RuntimeError("llm down")
                yield  # pragma: no cover

        clean_registry.register("llm_service", _BrokenLLM())
        manager.initialize()
        reply = manager.process_message("你好")
        assert reply, "LLM 异常时应返回降级回复而非抛错"

    def test_clear_context_resets_turn_count_and_session(self, manager, clean_registry):
        clean_registry.register("llm_service", _FakeLLM("ok"))
        manager.initialize()
        manager.process_message("你好")
        assert manager.get_display_history(), "清除前应能看到本轮消息"

        manager.clear_context()

        assert manager.get_turn_count() == 0
        assert manager._history_cache == []
        assert manager.get_display_history() == []

    def test_clear_context_keeps_archive(self, manager, clean_registry):
        clean_registry.register("llm_service", _FakeLLM("ok"))
        manager.initialize()
        manager.process_message("旧消息")
        db = clean_registry.get("database")
        before = db.execute(
            "SELECT COUNT(*) FROM conversation_archive").fetchone()[0]
        assert before > 0

        manager.clear_context()

        after = db.execute(
            "SELECT COUNT(*) FROM conversation_archive").fetchone()[0]
        assert after == before, "只清本轮上下文，不应删除历史存档"

    def test_after_clear_only_new_messages_are_displayed(self, manager, clean_registry):
        clean_registry.register("llm_service", _FakeLLM("ok"))
        manager.initialize()
        manager.process_message("旧消息")
        manager.clear_context()

        manager._save_to_archive("user", "新消息")

        display = manager.get_display_history()
        assert [h["content"] for h in display] == ["新消息"]
