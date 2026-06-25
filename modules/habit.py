"""
习惯孵化模块。

创建习惯 → APScheduler每日提醒 → 打卡 → streak累计。
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from core.event_bus import bus
from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class HabitManager:
    """习惯管理器。"""

    def create(self, name: str, target_time: str = "21:00") -> Optional[str]:
        """创建习惯。

        Args:
            name: 习惯名称
            target_time: 提醒时间 (HH:MM)
        """
        hid = str(uuid.uuid4())[:8]
        try:
            db = registry.get("database")
            if db is None:
                return None
            db.execute(
                "INSERT INTO habit (id, name, target_time, streak, enabled) VALUES (?,?,?,0,1)",
                (hid, name, target_time),
            )
            db.commit()
            self._schedule_reminder(hid, name, target_time)
            logger.info(f"习惯已创建: {name} @ {target_time}")
            return hid
        except Exception as e:
            logger.error(f"习惯创建失败: {e}")
            return None

    def _schedule_reminder(self, hid: str, name: str, target_time: str) -> None:
        try:
            from apscheduler.triggers.cron import CronTrigger
            parts = target_time.split(":")
            h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            scheduler = registry.get("reminder_scheduler")
            if scheduler and scheduler._scheduler:
                scheduler._scheduler.add_job(
                    func=lambda: bus.publish("HABIT_REMINDER", {
                        "habit_id": hid, "name": name, "timestamp": datetime.now().isoformat(),
                    }),
                    trigger=CronTrigger(hour=h, minute=m),
                    id=f"habit_{hid}", replace_existing=True,
                )
        except Exception as e:
            logger.warning(f"习惯提醒注册失败: {e}")

    def check_in(self, hid: str) -> Optional[Dict[str, Any]]:
        """打卡。返回新 streak 信息。"""
        try:
            db = registry.get("database")
            if db is None:
                return None
            row = db.execute("SELECT name, streak, longest_streak, total_completions, last_check_date FROM habit WHERE id=? AND enabled=1", (hid,)).fetchone()
            if not row:
                return None
            name, streak, longest, total, last_date_str = row
            today = date.today()

            # 检查今日是否已打卡
            if last_date_str and last_date_str == today.isoformat():
                return {"name": name, "streak": streak, "total": total, "already": True}

            # 判断连续
            if last_date_str:
                last_date = date.fromisoformat(last_date_str)
                if (today - last_date).days == 1:
                    streak += 1
                elif (today - last_date).days == 0:
                    pass  # 同一天不处理
                else:
                    streak = 1  # 中断
            else:
                streak = 1

            longest = max(streak, longest or 0)
            total = (total or 0) + 1

            db.execute(
                "UPDATE habit SET streak=?, longest_streak=?, total_completions=?, last_check_date=? WHERE id=?",
                (streak, longest, total, today.isoformat(), hid),
            )
            db.commit()

            bus.publish("HABIT_COMPLETED", {"habit_id": hid, "name": name, "streak": streak})
            logger.info(f"习惯打卡: {name} streak={streak}")
            return {"name": name, "streak": streak, "longest": longest, "total": total, "already": False}
        except Exception as e:
            logger.error(f"习惯打卡失败: {e}")
            return None

    def skip(self, hid: str) -> None:
        """今天请假。"""
        try:
            db = registry.get("database")
            if db is None:
                return
            db.execute("UPDATE habit SET streak=0, last_check_date=? WHERE id=?", (date.today().isoformat(), hid))
            db.commit()
            bus.publish("HABIT_BROKEN", {"habit_id": hid})
            logger.info(f"习惯请假: {hid}")
        except Exception as e:
            logger.warning(f"习惯请假失败: {e}")

    def list_all(self) -> List[Dict[str, Any]]:
        try:
            db = registry.get("database")
            if db is None:
                return []
            cursor = db.execute("SELECT id,name,target_time,streak,longest_streak,total_completions,last_check_date,enabled FROM habit ORDER BY created_at DESC")
            return [
                {"id": r[0], "name": r[1], "target_time": r[2], "streak": r[3],
                 "longest": r[4], "total": r[5], "last_check": r[6], "enabled": bool(r[7])}
                for r in cursor.fetchall()
            ]
        except Exception:
            return []

    def get_habit(self, hid: str) -> Optional[Dict[str, Any]]:
        try:
            db = registry.get("database")
            if db is None:
                return None
            r = db.execute("SELECT * FROM habit WHERE id=?", (hid,)).fetchone()
            return {"id": r[0], "name": r[1], "target_time": r[2], "streak": r[3]} if r else None
        except Exception:
            return None