"""
用户画像管理模块。

管理 user_profile 和 user_traits 的读写、冲突检测和自动更新。
是介于抽取器和数据库之间的中间层。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from core.service_registry import registry
from utils.crypto import encrypt, decrypt
from utils.logger import get_logger

logger = get_logger(__name__)


class ProfileManager:
    """用户画像管理器。

    职责：
    - 用户固定属性的 CRUD (user_profile)
    - 习得特质的 CRUD (user_traits)
    - 置信度计算与更新
    - 新旧特质冲突检测
    - 提供画像摘要供 prompt_builder 使用
    """

    def __init__(self):
        pass

    def _get_db(self):
        return registry.get("database")

    # ------------------------------------------------------------------
    # 用户固定属性
    # ------------------------------------------------------------------

    def set_profile(self, key: str, value: str, confidence: float = 1.0) -> bool:
        """设置用户固定属性。

        Args:
            key: 属性名（如 nickname, dietary_restrictions）
            value: 属性值
            confidence: 置信度（默认 1.0 表示用户显式输入）

        Returns:
            是否成功
        """
        try:
            db = self._get_db()
            if db is None:
                return False
            encrypted = encrypt(value)
            db.execute(
                "INSERT OR REPLACE INTO user_profile (key, value, confidence, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (key, encrypted, confidence, datetime.now().isoformat()),
            )
            db.commit()
            logger.info(f"用户属性已设置: {key}")
            return True
        except Exception as e:
            logger.error(f"设置属性失败: {e}")
            return False

    def get_profile(self, key: str, default: str = "") -> str:
        """获取用户固定属性。

        Args:
            key: 属性名
            default: 默认值

        Returns:
            解密后的属性值
        """
        try:
            db = self._get_db()
            if db is None:
                return default
            cursor = db.execute("SELECT value FROM user_profile WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return decrypt(row[0])
            return default
        except Exception:
            return default

    def get_all_profiles(self) -> Dict[str, str]:
        """获取所有用户属性（解密后）。"""
        try:
            db = self._get_db()
            if db is None:
                return {}
            cursor = db.execute("SELECT key, value FROM user_profile")
            return {row[0]: decrypt(row[1]) for row in cursor.fetchall()}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # 习得特质
    # ------------------------------------------------------------------

    def upsert_trait(
        self,
        trait_name: str,
        value: str,
        evidence: str = "",
        confidence: float = 0.6,
        source: str = "auto",
    ) -> bool:
        """插入或更新习得特质。

        如果特质已存在：增加 occurrences，提升置信度
        如果不存在：创建新特质

        Args:
            trait_name: 特质名
            value: 特质值
            evidence: 证据摘要
            confidence: 初始置信度
            source: auto / manual

        Returns:
            是否成功
        """
        try:
            db = self._get_db()
            if db is None:
                return False

            # 检查是否已存在
            cursor = db.execute(
                "SELECT trait_id, occurrences, confidence FROM user_traits "
                "WHERE trait_name = ?", (trait_name,)
            )
            existing = cursor.fetchone()

            if existing:
                # 已存在：更新
                trait_id, old_occurrences, old_confidence = existing
                new_occurrences = old_occurrences + 1
                new_confidence = min(old_confidence + 0.1, 0.9)

                db.execute(
                    "UPDATE user_traits SET "
                    "occurrences = ?, confidence = ?, "
                    "evidence = evidence || '; ' || ?, "
                    "last_active = ? "
                    "WHERE trait_id = ?",
                    (new_occurrences, new_confidence, evidence[:200],
                     datetime.now().isoformat(), trait_id),
                )
                logger.debug(f"特质已更新: {trait_name} (置信度 {old_confidence:.2f}→{new_confidence:.2f})")
            else:
                # 新建
                db.execute(
                    "INSERT INTO user_traits "
                    "(trait_name, value, evidence, occurrences, confidence, source, last_active) "
                    "VALUES (?, ?, ?, 1, ?, ?, ?)",
                    (trait_name, value, evidence[:200], confidence, source,
                     datetime.now().isoformat()),
                )
                logger.info(f"新特质已创建: {trait_name} (置信度 {confidence:.2f})")

            db.commit()
            return True

        except Exception as e:
            logger.error(f"保存特质失败: {e}")
            return False

    def batch_upsert_traits(self, candidates: List[Dict[str, Any]]) -> int:
        """批量存入候选特质。

        Args:
            candidates: 候选特质列表

        Returns:
            成功存入的数量
        """
        count = 0
        for c in candidates:
            # 过滤低置信度
            if c.get("confidence", 0) < 0.3:
                continue

            # 冲突检测
            if self._has_conflict(c.get("trait_name", ""), c.get("value", "")):
                self._resolve_conflict(c)

            if self.upsert_trait(
                trait_name=c.get("trait_name", ""),
                value=c.get("value", ""),
                evidence=c.get("evidence", ""),
                confidence=c.get("confidence", 0.5),
                source=c.get("source", "auto"),
            ):
                count += 1

        return count

    def get_trait(self, trait_name: str) -> Optional[Dict[str, Any]]:
        """获取单个特质。"""
        try:
            db = self._get_db()
            if db is None:
                return None
            cursor = db.execute(
                "SELECT * FROM user_traits WHERE trait_name = ?", (trait_name,)
            )
            row = cursor.fetchone()
            if row:
                cols = [d[0] for d in cursor.description]
                return dict(zip(cols, row))
            return None
        except Exception:
            return None

    def get_active_traits(self, min_confidence: float = 0.6, days: int = 60) -> List[Dict[str, Any]]:
        """获取活跃特质列表。

        Args:
            min_confidence: 最低置信度
            days: 最近活跃天数

        Returns:
            特质列表
        """
        try:
            db = self._get_db()
            if db is None:
                return []
            cursor = db.execute(
                "SELECT trait_name, value, confidence, occurrences, last_active "
                "FROM user_traits WHERE confidence >= ? "
                "AND last_active >= date('now', ?) "
                "ORDER BY confidence DESC",
                (min_confidence, f"-{days} days"),
            )
            return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
        except Exception:
            return []

    def get_all_traits(self) -> List[Dict[str, Any]]:
        """获取所有特质。"""
        try:
            db = self._get_db()
            if db is None:
                return []
            cursor = db.execute(
                "SELECT * FROM user_traits ORDER BY confidence DESC"
            )
            return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
        except Exception:
            return []

    def update_confidence(self, trait_name: str, delta: float) -> None:
        """调整特质置信度。

        Args:
            trait_name: 特质名
            delta: 置信度变化量（正值提升，负值降低）
        """
        try:
            db = self._get_db()
            if db is None:
                return
            db.execute(
                "UPDATE user_traits SET confidence = MAX(0, MIN(1, confidence + ?)), "
                "last_active = ? WHERE trait_name = ?",
                (delta, datetime.now().isoformat(), trait_name),
            )
            db.commit()
        except Exception as e:
            logger.warning(f"置信度更新失败: {e}")

    def delete_trait(self, trait_name: str) -> bool:
        """删除特质。"""
        try:
            db = self._get_db()
            if db is None:
                return False
            db.execute("DELETE FROM user_traits WHERE trait_name = ?", (trait_name,))
            db.commit()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 冲突检测
    # ------------------------------------------------------------------

    def _has_conflict(self, trait_name: str, value: str) -> bool:
        """检测新特质是否与现有高置信度特质冲突。"""
        try:
            db = self._get_db()
            if db is None:
                return False

            # 简化版：检查名称前缀相似的已有特质
            prefix = trait_name.split("_")[0] if "_" in trait_name else trait_name[:3]
            cursor = db.execute(
                "SELECT trait_name, value, confidence FROM user_traits "
                "WHERE trait_name LIKE ? AND confidence > 0.7",
                (f"{prefix}%",)
            )
            for row in cursor.fetchall():
                existing_name, existing_value, confidence = row
                # 同前缀但值不同的视为潜在冲突
                if existing_value != value:
                    return True
            return False
        except Exception:
            return False

    def _resolve_conflict(self, candidate: Dict[str, Any]) -> None:
        """解决新旧特质冲突：降低旧特质置信度。"""
        trait_name = candidate.get("trait_name", "")
        prefix = trait_name.split("_")[0] if "_" in trait_name else trait_name[:3]

        try:
            db = self._get_db()
            if db is None:
                return
            db.execute(
                "UPDATE user_traits SET confidence = confidence - 0.3 "
                "WHERE trait_name LIKE ? AND confidence > 0.6 AND value != ?",
                (f"{prefix}%", candidate.get("value", "")),
            )
            db.commit()
            logger.info(f"冲突解决: {prefix} 旧特质置信度 -0.3")
        except Exception as e:
            logger.warning(f"冲突解决失败: {e}")

    # ------------------------------------------------------------------
    # 画像摘要
    # ------------------------------------------------------------------

    def get_profile_summary(self) -> str:
        """获取画像摘要文本（供 prompt_builder 使用）。"""
        parts = []

        # 固定属性
        profiles = self.get_all_profiles()
        if profiles.get("nickname"):
            parts.append(f"昵称: {profiles['nickname']}")
        if profiles.get("dietary_restrictions"):
            parts.append(f"饮食限制: {profiles['dietary_restrictions']}")
        if profiles.get("favorite_foods"):
            parts.append(f"喜欢的食物: {profiles['favorite_foods']}")

        # 高置信度特质
        traits = self.get_active_traits(min_confidence=0.7, days=30)
        if traits:
            trait_text = "\n".join(
                f"- {t['trait_name']}: {t['value']}" for t in traits[:10]
            )
            parts.append(f"已习得偏好:\n{trait_text}")

        return "\n".join(parts) if parts else ""

    def clear_all(self) -> bool:
        """一键清除所有画像和特质（"忘记我"功能）。"""
        try:
            db = self._get_db()
            if db is None:
                return False
            db.execute("DELETE FROM user_profile")
            db.execute("DELETE FROM user_traits")
            db.commit()
            logger.info("所有画像和特质已清除")
            return True
        except Exception:
            return False