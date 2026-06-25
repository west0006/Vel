"""
遗忘算法模块。

实现情节记忆的时间衰减和特质的自动清理机制。
定期执行清理任务，移除过期或低质量的记忆。
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class ForgettingEngine:
    """遗忘引擎。

    定期执行：
    - 情节记忆衰减（指数衰减模型）
    - 特质自动清理（低置信度 + 长期未激活）
    - 归档旧记忆（分数 < 阈值时移入归档表 / 删除）
    """

    def __init__(self):
        # 衰减参数
        self._half_life_days = 30
        self._importance_scale = {
            1: 7, 2: 14, 3: 21, 4: 30, 5: 30,
            6: 45, 7: 60, 8: 75, 9: 90, 10: 90,
        }

        # 清理阈值
        self._memory_score_threshold = 1.0
        self._trait_confidence_threshold = 0.3
        self._trait_inactive_days = 90
        self._trait_low_occurrence = 3

    # ------------------------------------------------------------------
    # 情节记忆衰减
    # ------------------------------------------------------------------

    def calculate_decay(self, importance: int, created_at: datetime,
                        last_recalled: Optional[datetime] = None) -> float:
        """计算记忆的当前衰减分数。

        使用指数衰减模型：score = importance * 2^(-Δt / T)
        其中 T 是根据重要性调整的半衰期。

        Args:
            importance: 初始重要性 1~10
            created_at: 创建时间
            last_recalled: 最后一次召回时间（重置衰减）

        Returns:
            当前衰减分数
        """
        half_life = self._importance_scale.get(importance, self._half_life_days)
        now = datetime.now()
        reference_time = last_recalled if last_recalled else created_at
        delta_days = (now - reference_time).total_seconds() / 86400
        decay_factor = 2 ** (-delta_days / half_life)
        return importance * decay_factor

    def apply_decay_to_all(self) -> int:
        """对所有未归档的记忆执行衰减计算，删除低于阈值的记忆。

        修复 P1-1：通过 MemoryService.delete_memory() 删除，
        确保 FAISS 索引和 id_map 同步清理。

        Returns:
            清理的记忆数量
        """
        try:
            db = registry.get("database")
            memory_svc = registry.get("memory_service")
            if db is None:
                return 0

            cursor = db.execute(
                "SELECT memory_id, importance, created_at, last_recalled "
                "FROM episodic_memory"
            )
            memories = cursor.fetchall()

            deleted_count = 0
            for row in memories:
                memory_id, importance, created_at_str, last_recalled_str = row
                importance = importance or 5

                created_at = datetime.fromisoformat(created_at_str)
                last_recalled = (
                    datetime.fromisoformat(last_recalled_str)
                    if last_recalled_str else None
                )

                score = self.calculate_decay(importance, created_at, last_recalled)

                if score < self._memory_score_threshold:
                    if memory_svc:
                        memory_svc.delete_memory(memory_id)
                    else:
                        db.execute(
                            "DELETE FROM episodic_memory WHERE memory_id = ?",
                            (memory_id,)
                        )
                    deleted_count += 1
                else:
                    db.execute(
                        "UPDATE episodic_memory SET decay_factor = ? WHERE memory_id = ?",
                        (score / importance, memory_id),
                    )

            db.commit()

            if deleted_count > 0:
                logger.info(f"记忆衰减清理: {deleted_count} 条已删除")

            return deleted_count

        except Exception as e:
            logger.error(f"记忆衰减计算失败: {e}")
            return 0

    # ------------------------------------------------------------------
    # 特质自动清理
    # ------------------------------------------------------------------

    def cleanup_traits(self) -> int:
        """清理过期或低质量特质。"""
        try:
            db = registry.get("database")
            if db is None:
                return 0

            cursor1 = db.execute(
                "DELETE FROM user_traits WHERE confidence < ?",
                (self._trait_confidence_threshold,)
            )
            count1 = cursor1.rowcount

            cursor2 = db.execute(
                "DELETE FROM user_traits WHERE "
                "last_active < date('now', ?) AND occurrences < ?",
                (f"-{self._trait_inactive_days} days", self._trait_low_occurrence)
            )
            count2 = cursor2.rowcount

            cursor3 = db.execute(
                "DELETE FROM user_traits WHERE "
                "confidence < 0.5 AND last_active < date('now', '-60 days')"
            )
            count3 = cursor3.rowcount

            db.commit()
            total = count1 + count2 + count3

            if total > 0:
                logger.info(
                    f"特质清理: {total} 条 "
                    f"(低置信度={count1}, 未活跃={count2}, 中等过期={count3})"
                )

            return total
        except Exception as e:
            logger.error(f"特质清理失败: {e}")
            return 0

    # ------------------------------------------------------------------
    # 定时维护
    # ------------------------------------------------------------------

    def run_weekly_maintenance(self) -> Dict[str, int]:
        """执行每周维护：衰减 + 清理。"""
        logger.info("执行每周记忆维护...")
        memories = self.apply_decay_to_all()
        traits = self.cleanup_traits()
        return {
            "memories_deleted": memories,
            "traits_deleted": traits,
        }

    def run_on_startup(self) -> None:
        """启动时轻量维护。"""
        self.cleanup_traits()

    # ------------------------------------------------------------------
    # 手动遗忘
    # ------------------------------------------------------------------

    def forget_recent_memories(self, hours: int = 24) -> int:
        """遗忘最近 N 小时的记忆（同步清理 FAISS）。"""
        try:
            db = registry.get("database")
            memory_svc = registry.get("memory_service")
            if db is None:
                return 0

            cursor = db.execute(
                "SELECT memory_id FROM episodic_memory "
                "WHERE created_at > datetime('now', ?)",
                (f"-{hours} hours",)
            )
            expired = [row[0] for row in cursor.fetchall()]

            for mid in expired:
                if memory_svc:
                    memory_svc.delete_memory(mid)
                else:
                    db.execute("DELETE FROM episodic_memory WHERE memory_id = ?", (mid,))

            db.commit()
            logger.info(f"已遗忘最近 {hours} 小时的 {len(expired)} 条记忆")
            return len(expired)
        except Exception:
            return 0