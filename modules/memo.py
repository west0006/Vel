"""
简易备忘录模块。

支持"记一下："语法解析创建，到期提醒，列表查询。
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from apscheduler.triggers.date import DateTrigger

from core.event_bus import bus, EVENT_SCHEDULE_ALERT
from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class MemoManager:
    """备忘录管理器。"""

    def __init__(self):
        pass

    def _db(self):
        return registry.get("database")

    def parse_and_create(self, text: str) -> Optional[Dict[str, Any]]:
        """从"记一下：..."文本解析并创建备忘录。

        Args:
            text: 如 "记一下：明天下午3点约见客户"

        Returns:
            创建的 memo 字典，失败返回 None
        """
        # 去掉前缀
        for prefix in ("记一下：", "记一下:", "备忘录：", "备忘录:"):
            if text.startswith(prefix):
                content = text[len(prefix):].strip()
                break
        else:
            return None

        remind_at = None
        reminder_text = content

        # 尝试解析时间
        import dateparser
        # 常见中文时间模式
        import re
        time_patterns = [
            r'(明天|后天|今天|下周[一二三四五六日天])\s*(早上|上午|中午|下午|傍晚|晚上|凌晨)?\s*(\d{1,2})[点:：](\d{1,2})?[分]?',
            r'(\d{1,2})月(\d{1,2})[日号]\s*(早上|上午|中午|下午|傍晚|晚上|凌晨)?\s*(\d{1,2})[点:：](\d{1,2})?[分]?',
        ]
        time_phrase = None
        for pat in time_patterns:
            m = re.search(pat, content)
            if m:
                time_phrase = m.group(0)
                break

        if time_phrase:
            try:
                parsed = dateparser.parse(time_phrase,
                    settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': datetime.now()})
                if parsed:
                    remind_at = parsed
                    reminder_text = content.replace(time_phrase, "").strip()
            except Exception:
                pass

        # 存入数据库
        memo_id = str(uuid.uuid4())
        try:
            db = self._db()
            if db is None:
                return None
            db.execute(
                "INSERT INTO memo (id, content, remind_at, status) VALUES (?, ?, ?, 'active')",
                (memo_id, reminder_text or content, remind_at.isoformat() if remind_at else None),
            )
            db.commit()

            # 注册提醒
            if remind_at and remind_at > datetime.now():
                self._schedule_reminder(memo_id, remind_at, reminder_text or content)

            logger.info(f"备忘录已创建: {reminder_text[:50]}")
            return {"id": memo_id, "content": reminder_text or content, "remind_at": remind_at}
        except Exception as e:
            logger.error(f"备忘录创建失败: {e}")
            return None

    def _schedule_reminder(self, memo_id: str, remind_at: datetime, content: str) -> None:
        """注册 APScheduler 提醒。"""
        try:
            scheduler = registry.get("reminder_scheduler")
            if scheduler is None or scheduler._scheduler is None:
                return
            job_id = f"memo_{memo_id}"
            scheduler._scheduler.add_job(
                func=lambda: bus.publish("MEMO_REMINDER", {
                    "memo_id": memo_id, "content": content, "timestamp": datetime.now().isoformat(),
                }),
                trigger=DateTrigger(run_date=remind_at),
                id=job_id, replace_existing=True,
            )
        except Exception as e:
            logger.warning(f"备忘录提醒注册失败: {e}")

    def get_active(self) -> List[Dict[str, Any]]:
        """获取所有活跃备忘录。"""
        try:
            db = self._db()
            if db is None: return []
            cursor = db.execute(
                "SELECT id, content, remind_at, created_at FROM memo WHERE status='active' ORDER BY remind_at ASC"
            )
            return [{"id": r[0], "content": r[1], "remind_at": r[2], "created_at": r[3]} for r in cursor.fetchall()]
        except Exception:
            return []

    def mark_done(self, memo_id: str) -> bool:
        try:
            db = self._db()
            if db is None: return False
            db.execute("UPDATE memo SET status='completed' WHERE id=?", (memo_id,)); db.commit()
            return True
        except Exception:
            return False

    def delete(self, memo_id: str) -> bool:
        try:
            db = self._db()
            if db is None: return False
            db.execute("DELETE FROM memo WHERE id=?", (memo_id,)); db.commit()
            return True
        except Exception:
            return False