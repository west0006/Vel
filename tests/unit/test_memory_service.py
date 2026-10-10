"""MemoryService 单元测试。

聚焦**数据一致性**与**死向量压缩阈值** —— 这两处出错不会报错，
但会导致检索返回错误记忆或索引无限膨胀。
"""

import sqlite3

import pytest

from services.memory_service import MemoryService

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodic_memory (
    memory_id       TEXT PRIMARY KEY,
    summary         TEXT,
    category        TEXT,
    importance      INTEGER,
    embedding_id    TEXT,
    context_msg_ids TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture
def svc(monkeypatch):
    """构造不加载 encoder / FAISS 的实例，并以内存库替代真实数据库。"""
    service = MemoryService(db_path=":memory:", faiss_path=":memory:")
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    conn.commit()
    monkeypatch.setattr(service, "_get_db", lambda: conn)
    service._test_conn = conn
    return service


class _FakeIndex:
    """最小 FAISS 索引替身（只需 ntotal / d）。"""

    def __init__(self, ntotal=0, d=384):
        self.ntotal = ntotal
        self.d = d


class TestIdMapRebuild:
    """id_map 与 reverse_id_map 的一致性。"""

    def test_rebuild_from_db(self, svc):
        svc._test_conn.execute(
            "INSERT INTO episodic_memory (memory_id, embedding_id) VALUES ('m1','0')")
        svc._test_conn.execute(
            "INSERT INTO episodic_memory (memory_id, embedding_id) VALUES ('m2','5')")
        svc._test_conn.commit()
        svc._rebuild_id_map()
        assert svc._id_map == {"m1": 0, "m2": 5}
        assert svc._reverse_id_map == {0: "m1", 5: "m2"}

    def test_rows_without_embedding_skipped(self, svc):
        svc._test_conn.execute(
            "INSERT INTO episodic_memory (memory_id, embedding_id) VALUES ('m1', NULL)")
        svc._test_conn.commit()
        svc._rebuild_id_map()
        assert svc._id_map == {}

    def test_bidirectional_consistency(self, svc):
        """正反映射必须一一对应 —— 不一致会导致检索命中错误记忆。"""
        for index in range(5):
            svc._test_conn.execute(
                "INSERT INTO episodic_memory (memory_id, embedding_id) VALUES (?,?)",
                (f"m{index}", str(index)))
        svc._test_conn.commit()
        svc._rebuild_id_map()
        assert len(svc._id_map) == len(svc._reverse_id_map) == 5
        for memory_id, faiss_id in svc._id_map.items():
            assert svc._reverse_id_map[faiss_id] == memory_id


class TestDeleteAndCompact:
    """删除记忆与死向量压缩。"""

    def _seed_index(self, svc, ntotal):
        """装入假索引并记录 _compact_index 的调用。"""
        svc._index = _FakeIndex(ntotal=ntotal)
        calls = []
        svc._compact_index = lambda: calls.append(1)   # type: ignore[assignment]
        return calls

    def test_delete_updates_maps_and_marks_dead(self, svc):
        svc._test_conn.execute(
            "INSERT INTO episodic_memory (memory_id, embedding_id) VALUES ('m1','0')")
        svc._test_conn.commit()
        svc._rebuild_id_map()
        self._seed_index(svc, ntotal=100)

        assert svc.delete_memory("m1") is True
        assert "m1" not in svc._id_map
        assert 0 not in svc._reverse_id_map
        assert 0 in svc._deleted_ids

    def test_compact_triggered_only_above_30_percent(self, svc):
        """死向量占比 > 30% 才触发压缩（阈值来自设计文档）。"""
        for index in range(4):
            svc._test_conn.execute(
                "INSERT INTO episodic_memory (memory_id, embedding_id) VALUES (?,?)",
                (f"m{index}", str(index)))
        svc._test_conn.commit()
        svc._rebuild_id_map()
        calls = self._seed_index(svc, ntotal=4)        # 阈值 = 1.2 条

        svc.delete_memory("m0")                        # 1/4 = 25% → 不压缩
        assert calls == []

        svc.delete_memory("m1")                        # 2/4 = 50% → 触发压缩
        assert calls == [1]

    def test_no_index_is_safe(self, svc):
        svc._index = None
        svc._test_conn.execute(
            "INSERT INTO episodic_memory (memory_id, embedding_id) VALUES ('m1','0')")
        svc._test_conn.commit()
        svc._rebuild_id_map()
        assert svc.delete_memory("m1") is True

    def test_delete_unknown_id_returns_true(self, svc):
        svc._index = _FakeIndex(ntotal=0)
        assert svc.delete_memory("__not_exist__") is True

    def test_compact_noop_without_dead_ids(self, svc):
        """无死向量时 _compact_index 应直接返回（不重建索引）。"""
        svc._index = _FakeIndex(ntotal=10)
        svc._deleted_ids.clear()
        svc._compact_index()                            # 不应抛异常


class TestCount:
    """记忆条数统计。"""

    def test_count(self, svc):
        for index in range(3):
            svc._test_conn.execute(
                "INSERT INTO episodic_memory (memory_id) VALUES (?)", (f"m{index}",))
        svc._test_conn.commit()
        assert svc.get_memory_count() == 3

    def test_count_on_error_returns_zero(self, svc, monkeypatch):
        def _boom():
            raise sqlite3.Error("db gone")

        monkeypatch.setattr(svc, "_get_db", _boom)
        assert svc.get_memory_count() == 0


class TestConstruction:
    """构造参数。"""

    def test_paths_recorded(self):
        service = MemoryService(db_path="a.db", faiss_path="b.index")
        assert service._db_path == "a.db"
        assert service._faiss_path == "b.index"

    def test_initial_state_clean(self):
        service = MemoryService()
        assert service._id_map == {}
        assert service._reverse_id_map == {}
        assert service._deleted_ids == set()
