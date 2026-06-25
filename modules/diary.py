"""
猫咪日记模块。

每日21:00自动生成 + 对话手动触发 + 历史查询。
"""

from datetime import datetime, date
from typing import Any, Dict, List, Optional

from core.event_bus import bus
from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class DiaryGenerator:
    """猫咪日记生成器。"""

    def generate(self, target_date: Optional[date] = None) -> Optional[str]:
        """生成指定日期的日记。

        Args:
            target_date: 目标日期，默认今天

        Returns:
            日记摘要文本，失败返回 None
        """
        target = target_date or date.today()
        context = self._collect(target)

        # 使用固定模板（不依赖LLM，避免LLM不可用时日记空白）
        summary = self._template_summary(context)
        if not summary:
            return None

        # 存入数据库
        try:
            db = registry.get("database")
            if db:
                db.execute(
                    "INSERT OR REPLACE INTO daily_diary (date, summary) VALUES (?, ?)",
                    (target.isoformat(), summary),
                )
                db.commit()
                logger.info(f"日记已生成: {target}")
                bus.publish("DIARY_GENERATED", {"date": target.isoformat(), "summary": summary})
                return summary
        except Exception as e:
            logger.error(f"日记存储失败: {e}")
        return None

    def get_diary(self, target_date: Optional[date] = None) -> Optional[str]:
        """获取指定日期的日记。"""
        target = target_date or date.today()
        try:
            db = registry.get("database")
            if db is None:
                return None
            cursor = db.execute(
                "SELECT summary FROM daily_diary WHERE date = ?", (target.isoformat(),)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def list_diaries(self, limit: int = 14) -> List[Dict[str, str]]:
        """列出最近日记。"""
        try:
            db = registry.get("database")
            if db is None:
                return []
            cursor = db.execute(
                "SELECT date, summary FROM daily_diary ORDER BY date DESC LIMIT ?", (limit,)
            )
            return [{"date": r[0], "summary": r[1]} for r in cursor.fetchall()]
        except Exception:
            return []

    def _collect(self, target: date) -> Dict[str, int]:
        """收集当日数据。"""
        data = {"completed_tasks": 0, "drink_ml": 0, "activities": 0, "meals": 0, "mood": ""}
        try:
            db = registry.get("database")
            if db is None:
                return data
            ds = target.isoformat()
            r = db.execute("SELECT COUNT(*) FROM schedule WHERE date(start_time)=? AND status='completed'", (ds,)).fetchone()
            data["completed_tasks"] = r[0] if r else 0
            r = db.execute("SELECT COALESCE(SUM(amount_ml),0) FROM drink_log WHERE date(timestamp)=?", (ds,)).fetchone()
            data["drink_ml"] = r[0] if r else 0
            r = db.execute("SELECT COUNT(*) FROM activity_log WHERE date(start_time)=?", (ds,)).fetchone()
            data["activities"] = r[0] if r else 0
            r = db.execute("SELECT COUNT(*) FROM meal_log WHERE date(timestamp)=?", (ds,)).fetchone()
            data["meals"] = r[0] if r else 0
            r = db.execute("SELECT mood_label FROM mood_snapshot WHERE date(timestamp)=? ORDER BY timestamp DESC LIMIT 1", (ds,)).fetchone()
            data["mood"] = r[0] if r else "平静"
        except Exception:
            pass
        return data

    def _template_summary(self, d: Dict[str, int], target: date) -> str:
        """模板生成日记（不依赖LLM）。

        Args:
            d: 当日统计数据
            target: 目标日期
        """
        parts = []
        mood_emoji = {"positive": "😊", "neutral": "😐", "negative": "😔"}.get(d.get("mood", ""), "😐")
        parts.append(f"今天的心情{mood_emoji}")
        if d["completed_tasks"]:
            parts.append(f"完成了{d['completed_tasks']}个日程")
        if d["drink_ml"]:
            parts.append(f"喝了{d['drink_ml']}ml水")
        if d["activities"]:
            parts.append(f"活动了{d['activities']}次")
        if d["meals"]:
            parts.append(f"记录了{d['meals']}餐")
        if len(parts) == 1:
            return f"今天是{target.strftime('%m月%d日')}，{parts[0]}。平常的一天，也是珍贵的一天喵~"
        return f"{'，'.join(parts)}。又是充实的一天，明天也要元气满满喵~"