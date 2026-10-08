"""
记忆服务模块。

嵌入编码：优先 Ollama nomic-embed-text，回退 sentence-transformers。
向量存储：FAISS Flat 索引。
"""

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from core.event_bus import bus, EVENT_MEMORY_CREATED
from core.service_registry import registry
from utils.crypto import encrypt, decrypt
from utils.logger import get_logger

logger = get_logger(__name__)


class OllamaEmbedder:
    """通过 Ollama API 进行文本向量编码。"""

    def __init__(self, model: str = "nomic-embed-text:latest",
                 host: str = "127.0.0.1", port: int = 11434,
                 dimension: int = 768):
        self._model = model
        self._host = host
        self._port = port
        self._url = f"http://{host}:{port}/api/embeddings"
        self._dimension = dimension
        self._available = None

    def _check(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import requests
            # 先确认模型存在
            r = requests.get(f"http://{self._host}:{self._port}/api/tags", timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            if self._model not in models:
                logger.warning(f"模型 {self._model} 不在 Ollama 中")
                self._available = False
                return False

            # 预热加载（首次推理较慢，给 60s）
            r = requests.post(
                self._url,
                json={"model": self._model, "prompt": "test"},
                timeout=60
            )
            self._available = (r.status_code == 200)
            if self._available:
                data = r.json()
                actual_dim = len(data.get("embedding", []))
                if actual_dim > 0:
                    self._dimension = actual_dim
                    logger.info(f"Ollama 嵌入就绪: {self._model} (dim={self._dimension})")
            return self._available
        except Exception as e:
            logger.warning(f"Ollama 嵌入检测失败: {e}")
            self._available = False
            return False

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: List[str]) -> np.ndarray:
        import requests
        result = np.zeros((len(texts), self._dimension), dtype=np.float32)
        for i, text in enumerate(texts):
            try:
                r = requests.post(self._url, json={"model": self._model, "prompt": text}, timeout=10)
                r.raise_for_status()
                emb = r.json()["embedding"]
                result[i] = np.array(emb, dtype=np.float32)
            except Exception as e:
                logger.warning(f"嵌入失败: {e}")
        return result


class SentenceTransformerEmbedder:
    """回退：sentence-transformers。"""

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self._model_name = model_name
        self._model = None
        self._dimension = 384

    def _load(self):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self._model_name)

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: List[str]) -> np.ndarray:
        if self._model is None:
            self._load()
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return np.array(embeddings, dtype=np.float32)


class MemoryService:
    def __init__(self, db_path="data/pet.db", faiss_path="data/faiss.index",
                 ollama_host="127.0.0.1", ollama_port=11434,
                 embedding_model="nomic-embed-text:latest"):
        self._db_path = db_path
        self._faiss_path = faiss_path
        self._model_name = embedding_model
        self._dimension = 768

        self._encoder = None
        self._index = None
        self._id_map: Dict[str, int] = {}
        self._reverse_id_map: Dict[int, str] = {}
        self._deleted_ids: set = set()  # 待压缩的 dead IDs
        self._lock = threading.Lock()

    def _get_db(self):
        """获取数据库连接，优先复用注册的连接。"""
        db = registry.get("database")
        if db is not None:
            return db
        return sqlite3.connect(self._db_path)

    def initialize(self) -> bool:
        try:
            self._load_encoder()
            self._dimension = self._encoder.dimension
            self._load_or_create_index()
            logger.info(f"记忆服务初始化完成 (dim={self._dimension})")
            return True
        except Exception as e:
            logger.error(f"记忆服务初始化失败: {e}")
            return False

    def _load_encoder(self) -> None:
        # 优先 Ollama
        ollama = OllamaEmbedder(model=self._model_name)
        if ollama._check():
            self._encoder = ollama
            return
        # 回退 sentence-transformers
        logger.warning("Ollama 嵌入不可用，回退到 sentence-transformers")
        self._encoder = SentenceTransformerEmbedder()
        self._encoder._load()

    def _load_or_create_index(self) -> None:
        import faiss
        if os.path.exists(self._faiss_path):
            self._index = faiss.read_index(self._faiss_path)
            if self._index.d != self._dimension:
                logger.warning(f"索引维度不匹配 ({self._index.d} vs {self._dimension})，重建")
                self._index = faiss.IndexFlatIP(self._dimension)
            else:
                logger.info(f"FAISS 索引已加载 ({self._index.ntotal} 条)")
                self._rebuild_id_map()
                return
        self._index = faiss.IndexFlatIP(self._dimension)
        logger.info(f"新 FAISS 索引已创建 (dim={self._dimension})")

    def _rebuild_id_map(self) -> None:
        try:
            conn = self._get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT memory_id, embedding_id FROM episodic_memory WHERE embedding_id IS NOT NULL")
            for memory_id, embedding_id in cursor.fetchall():
                if embedding_id:
                    faiss_id = int(embedding_id)
                    self._id_map[memory_id] = faiss_id
                    self._reverse_id_map[faiss_id] = memory_id

        except Exception as e:
            logger.warning(f"重建 id_map 失败: {e}")

    def encode(self, texts: List[str]) -> np.ndarray:
        return self._encoder.encode(texts)

    def add_memory(self, summary, category="fact", importance=5, context_msg_ids=None):
        memory_id = str(uuid.uuid4())
        with self._lock:
            try:
                embedding = self.encode([summary])[0]
                if self._index is None:
                    logger.warning("FAISS 索引未初始化")
                    return None
                faiss_id = self._index.ntotal
                self._index.add(np.array([embedding]))
                self._id_map[memory_id] = faiss_id
                self._reverse_id_map[faiss_id] = memory_id
                self._save_index()

                conn = self._get_db()
                conn.execute(
                    "INSERT INTO episodic_memory (memory_id,summary,category,importance,embedding_id,context_msg_ids) "
                    "VALUES (?,?,?,?,?,?)",
                    (memory_id, encrypt(summary), category, importance, str(faiss_id),
                     json.dumps(context_msg_ids or [], ensure_ascii=False)),
                )
                conn.commit()

                logger.info(f"记忆已存储: {category} - {summary[:50]}...")
                bus.publish(EVENT_MEMORY_CREATED, {"memory_id": memory_id, "category": category, "importance": importance})
                return memory_id
            except Exception as e:
                logger.exception(f"记忆存储失败: {e}")
                return None

    def search(self, query, top_k=5, min_score=0.5):
        if self._index is None or self._index.ntotal == 0:
            return []
        with self._lock:
            try:
                query_vec = self.encode([query])[0]
                scores, indices = self._index.search(np.array([query_vec]), min(top_k, self._index.ntotal))
                results = []
                conn = self._get_db()
                conn.row_factory = sqlite3.Row
                for score, faiss_idx in zip(scores[0], indices[0]):
                    if faiss_idx < 0 or score < min_score:
                        continue
                    memory_id = self._reverse_id_map.get(int(faiss_idx))
                    if not memory_id:
                        continue
                    cursor = conn.execute(
                        "SELECT memory_id,summary,category,importance,created_at FROM episodic_memory WHERE memory_id=?",
                        (memory_id,),
                    )
                    row = cursor.fetchone()
                    if row:
                        results.append({
                            "memory_id": row["memory_id"], "summary": decrypt(row["summary"]),
                            "category": row["category"], "importance": row["importance"],
                            "score": float(score), "created_at": row["created_at"],
                        })
                        conn.execute("UPDATE episodic_memory SET last_recalled=? WHERE memory_id=?",
                                     (datetime.now().isoformat(), memory_id))
                conn.commit()

                return results
            except Exception as e:
                logger.exception(f"记忆检索失败: {e}")
                return []

    def delete_memory(self, memory_id):
        with self._lock:
            try:
                faiss_id = self._id_map.pop(memory_id, None)
                if faiss_id is not None:
                    self._reverse_id_map.pop(faiss_id, None)
                    self._deleted_ids.add(faiss_id)
                conn = self._get_db()
                conn.execute("DELETE FROM episodic_memory WHERE memory_id=?", (memory_id,))
                conn.commit()

                # 死向量超过 30% 时触发压缩
                total = self._index.ntotal if self._index else 0
                if total > 0 and len(self._deleted_ids) > total * 0.3:
                    self._compact_index()

                return True
            except Exception as e:
                logger.error(f"删除记忆失败: {e}")
                return False

    def get_memory_count(self):
        try:
            conn = self._get_db()
            cursor = conn.execute("SELECT COUNT(*) FROM episodic_memory")
            count = cursor.fetchone()[0]

            return count
        except Exception:
            return 0

    def _save_index(self):
        import faiss
        faiss.write_index(self._index, self._faiss_path)

    def _compact_index(self) -> None:
        """重建 FAISS 索引，移除死向量。"""
        import faiss
        if self._index is None or not self._deleted_ids:
            return
        logger.info(
            f"FAISS 索引压缩: {len(self._deleted_ids)} 个死向量 / "
            f"{self._index.ntotal} 总量"
        )
        try:
            # 重建新索引
            new_index = faiss.IndexFlatIP(self._dimension)
            new_id_map: Dict[str, int] = {}
            new_rev: Dict[int, str] = {}

            conn = self._get_db()
            cursor = conn.execute(
                "SELECT memory_id, embedding_id FROM episodic_memory "
                "WHERE embedding_id IS NOT NULL ORDER BY CAST(embedding_id AS INTEGER)"
            )
            embeddings = []
            for memory_id, emb_id in cursor.fetchall():
                faiss_id = int(emb_id)
                if faiss_id not in self._deleted_ids:
                    # 从旧索引取出向量
                    vec = self._index.reconstruct(faiss_id)
                    embeddings.append(vec)
                    new_id = new_index.ntotal + len(embeddings) - 1
                    new_id_map[memory_id] = new_id
                    new_rev[new_id] = memory_id

            if embeddings:
                new_index.add(np.array(embeddings))
                # 更新 embedding_id
                for memory_id, new_id in new_id_map.items():
                    conn.execute(
                        "UPDATE episodic_memory SET embedding_id = ? WHERE memory_id = ?",
                        (str(new_id), memory_id),
                    )
                conn.commit()

            self._index = new_index
            self._id_map = new_id_map
            self._reverse_id_map = new_rev
            self._deleted_ids.clear()
            self._save_index()

            logger.info(f"FAISS 索引压缩完成: {new_index.ntotal} 条有效向量")
        except Exception as e:
            logger.error(f"索引压缩失败: {e}")

    def _save_index(self):
        import faiss
        faiss.write_index(self._index, self._faiss_path)

    def cleanup_old_memories(self, threshold_days=90):
        try:
            conn = self._get_db()
            cursor = conn.execute(
                "SELECT memory_id FROM episodic_memory WHERE last_recalled IS NOT NULL AND "
                "julianday('now') - julianday(last_recalled) > ?", (threshold_days,)
            )
            expired = [row[0] for row in cursor.fetchall()]
            for mid in expired:
                self.delete_memory(mid)

            logger.info(f"已清理 {len(expired)} 条过期记忆")
            return len(expired)
        except Exception as e:
            logger.error(f"清理记忆失败: {e}")
            return 0