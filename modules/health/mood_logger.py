"""
情绪日志模块。

Alpha 版使用基于关键词的情绪打分（开心/平静/低落三档词库），
支持趋势存储和曲线数据生成（供设置面板展示）。
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

from core.event_bus import bus, EVENT_MOOD_DETECTED
from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class MoodLogger:
    """情绪日志记录器。

    Alpha 版简化实现：关键词情感打分，三档分类。
    v0.2 将替换为 DistilBERT 微调模型。
    """

    # 正面情绪关键词
    POSITIVE_WORDS = {
        "开心": 0.9, "高兴": 0.9, "喜欢": 0.8, "棒": 0.7, "谢谢": 0.6,
        "赞": 0.7, "爱": 0.9, "快乐": 0.9, "nice": 0.6, "great": 0.7,
        "good": 0.6, "哈哈": 0.8, "嘻嘻": 0.7, "太好了": 0.9, "厉害": 0.7,
        "优秀": 0.8, "美味": 0.7, "好吃": 0.7, "幸福": 0.9, "满足": 0.8,
        "期待": 0.7, "感动": 0.8, "舒服": 0.7, "放松": 0.7, "顺利": 0.6,
    }

    # 负面情绪关键词
    NEGATIVE_WORDS = {
        "烦": 0.7, "累": 0.6, "怒": 0.8, "生气": 0.8, "讨厌": 0.8,
        "难过": 0.8, "失望": 0.7, "烦躁": 0.8, "焦虑": 0.8, "压力": 0.7,
        "烦死了": 0.9, "郁闷": 0.8, "伤心": 0.9, "崩溃": 0.9, "无聊": 0.5,
        "疲惫": 0.7, "困": 0.5, "头疼": 0.6, "糟糕": 0.7, "失败": 0.8,
        "不开心": 0.7, "后悔": 0.8, "害怕": 0.8, "担心": 0.6, "无奈": 0.6,
    }

    def __init__(self):
        self._consecutive_negative = 0
        self._daily_moods: List[Dict] = []

    # ------------------------------------------------------------------
    # 情绪分析
    # ------------------------------------------------------------------

    def analyze(self, text: str) -> Tuple[str, float]:
        """分析文本情绪（关键词打分）。

        Args:
            text: 用户输入文本

        Returns:
            (label, intensity) — label: "positive"/"neutral"/"negative", intensity: 0~1
        """
        text_lower = text.lower()

        # 扫描关键词
        pos_score = 0.0
        neg_score = 0.0
        pos_count = 0
        neg_count = 0

        for word, weight in self.POSITIVE_WORDS.items():
            if word in text_lower:
                pos_score += weight
                pos_count += 1

        for word, weight in self.NEGATIVE_WORDS.items():
            if word in text_lower:
                neg_score += weight
                neg_count += 1

        # 归一化
        if pos_count > 0:
            pos_score /= pos_count
        if neg_count > 0:
            neg_score /= neg_count

        # 判定
        if pos_score > neg_score and pos_count > 0:
            label = "positive"
            intensity = min(pos_score, 1.0)
        elif neg_score > pos_score and neg_count > 0:
            label = "negative"
            intensity = min(neg_score, 1.0)
        else:
            label = "neutral"
            intensity = max(pos_score, neg_score, 0.3)

        return label, intensity

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------

    def log_mood(self, text: str) -> Optional[Dict[str, Any]]:
        """分析并记录情绪。

        Args:
            text: 用户消息文本

        Returns:
            情绪记录字典，中性低强度时返回 None（不记录无意义数据）
        """
        label, intensity = self.analyze(text)

        # 中性和低强度不记录
        if label == "neutral" and intensity < 0.4:
            return None

        mood_record = {
            "timestamp": datetime.now().isoformat(),
            "mood_label": label,
            "intensity": intensity,
            "context_summary": text[:100],
        }

        # 存储到数据库
        self._save_to_db(mood_record)

        # 连续负面计数
        if label == "negative":
            self._consecutive_negative += 1
        else:
            self._consecutive_negative = 0

        # 记录到每日缓存
        self._daily_moods.append(mood_record)

        # 发布事件
        bus.publish(EVENT_MOOD_DETECTED, {
            "label": label,
            "intensity": intensity,
        })

        logger.debug(f"情绪记录: {label} (强度={intensity:.2f})")
        return mood_record

    def _save_to_db(self, record: Dict[str, Any]) -> None:
        """保存情绪记录到数据库。"""
        try:
            db = registry.get("database")
            if db is None:
                return
            db.execute(
                "INSERT INTO mood_snapshot (mood_label, intensity, context_summary) "
                "VALUES (?, ?, ?)",
                (record["mood_label"], record["intensity"], record["context_summary"]),
            )
            db.commit()
        except Exception as e:
            logger.warning(f"情绪记录存储失败: {e}")

    # ------------------------------------------------------------------
    # 趋势分析
    # ------------------------------------------------------------------

    def get_daily_trend(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近 N 天的情绪趋势数据。

        Args:
            days: 天数

        Returns:
            [{date, positive, neutral, negative, total, dominant}, ...]
        """
        try:
            db = registry.get("database")
            if db is None:
                return []

            cursor = db.execute(
                """SELECT date(timestamp) as d,
                   SUM(CASE WHEN mood_label='positive' THEN 1 ELSE 0 END) as pos,
                   SUM(CASE WHEN mood_label='neutral' THEN 1 ELSE 0 END) as neu,
                   SUM(CASE WHEN mood_label='negative' THEN 1 ELSE 0 END) as neg,
                   COUNT(*) as total
                   FROM mood_snapshot
                   WHERE timestamp >= date('now', ?)
                   GROUP BY d ORDER BY d ASC""",
                (f"-{days} days",),
            )

            results = []
            for row in cursor.fetchall():
                d, pos, neu, neg, total = row
                dominant = "positive"
                if neg >= pos and neg >= neu:
                    dominant = "negative"
                elif neu >= pos and neu >= neg:
                    dominant = "neutral"

                results.append({
                    "date": d,
                    "positive": pos or 0,
                    "neutral": neu or 0,
                    "negative": neg or 0,
                    "total": total or 0,
                    "dominant": dominant,
                })

            return results
        except Exception as e:
            logger.error(f"情绪趋势查询失败: {e}")
            return []

    def get_consecutive_negative(self) -> int:
        """获取连续负面情绪次数。"""
        return self._consecutive_negative

    def get_weekly_summary(self) -> Dict[str, Any]:
        """获取本周情绪摘要。"""
        trend = self.get_daily_trend(7)
        if not trend:
            return {"total": 0}

        total = sum(d["total"] for d in trend)
        pos = sum(d["positive"] for d in trend)
        neg = sum(d["negative"] for d in trend)
        neu = sum(d["neutral"] for d in trend)

        return {
            "total": total,
            "positive_pct": round(pos / max(total, 1) * 100, 1),
            "negative_pct": round(neg / max(total, 1) * 100, 1),
            "neutral_pct": round(neu / max(total, 1) * 100, 1),
            "dominant_mood": "positive" if pos >= neg else ("negative" if neg > pos else "neutral"),
            "trend": trend,
        }

    # ------------------------------------------------------------------
    # 关怀检测
    # ------------------------------------------------------------------

    def needs_comfort(self) -> bool:
        """判断是否需要在回复中加入关怀语句。"""
        if self._consecutive_negative >= 2:
            return True

        # 检查今天的情绪
        today = self.get_daily_trend(1)
        if today and today[0].get("negative", 0) >= 3:
            return True

        return False

    def get_comfort_text(self) -> str:
        """获取关怀语句。"""
        comfort_texts = [
            "听起来你好像有点不开心，有什么我可以帮忙的吗？",
            "别太勉强自己哦，休息一下也没关系的～",
            "我在呢，有什么想说的都可以告诉我",
            "今天是不是有点累了？要不要我给你推荐一个放松的小活动？",
        ]
        import random
        return random.choice(comfort_texts)


# 全局单例
mood_logger = MoodLogger()