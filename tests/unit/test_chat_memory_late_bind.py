"""R1：ChatManager 对 memory_service 的晚绑定。

背景：``main.py`` 用后台线程加载 MemoryService，而 ``ChatManager.initialize()``
紧接着执行；模型加载需要数秒，初始化时通常拿不到服务。这里锁定“首次使用时
重试并缓存”的行为，避免记忆召回/摘要写入在本进程内永久失效。
"""

import pytest

from core.service_registry import registry
from modules.chat.chat_manager import ChatManager


class _FakeMemory:
    def __init__(self):
        self.queries = []
        self.added = []

    def search(self, query, top_k=3, min_score=0.4):
        self.queries.append(query)
        return [{"summary": "用户喜欢猫"}]

    def add_memory(self, summary, category="fact", importance=5):
        self.added.append(
            {"summary": summary, "category": category, "importance": importance}
        )


@pytest.fixture
def services(monkeypatch):
    """可控的服务表；registry.get 按当前表内容返回。"""
    table = {}
    monkeypatch.setattr(
        registry, "get", lambda name, default=None: table.get(name, default)
    )
    return table


class TestLateBinding:
    def test_initialize_without_memory_is_safe(self, services):
        manager = ChatManager()
        manager.initialize()

        assert manager._memory_service is None
        assert manager._get_memory_service() is None

    def test_picks_up_service_registered_after_initialize(self, services):
        manager = ChatManager()
        manager.initialize()
        assert manager._memory_service is None

        fake = _FakeMemory()
        services["memory_service"] = fake

        assert manager._get_memory_service() is fake
        # 已缓存：再次调用返回同一实例
        assert manager._get_memory_service() is fake

    def test_retrieve_memories_uses_late_service(self, services):
        manager = ChatManager()
        manager.initialize()
        fake = _FakeMemory()
        services["memory_service"] = fake

        assert manager._retrieve_memories("你好") == ["用户喜欢猫"]
        assert fake.queries == ["你好"]

    def test_trigger_summary_uses_late_service(self, services):
        manager = ChatManager()
        manager.initialize()
        manager._history_cache = [
            {"role": "user", "content": "我喜欢猫"},
            {"role": "assistant", "content": "喵~"},
        ]
        fake = _FakeMemory()
        services["memory_service"] = fake

        manager._trigger_summary()

        assert fake.added
        assert fake.added[0]["category"] == "event"
