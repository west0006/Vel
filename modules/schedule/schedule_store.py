"""
日程存储模块。

提供日程的 CRUD 操作、冲突检测、重复日程实例管理。
所有操作通过 SQLite 数据库完成，写操作使用基本锁保护。
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.service_registry import registry
from modules.schedule.schedule_parser import ScheduleItem
from utils.logger import get_logger

logger = get_logger(__name__)


class ScheduleStore:
    """日程存储管理器。

    负责日程的持久化和查询，支持单次日程和重复日程实例。
    """

    def __init__(self):
        self._db: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def _get_db(self) -> sqlite3.Connection:
        """获取数据库连接。"""
        if self._db is None:
            self._db = registry.get("database")
        return self._db

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    def add_schedule(self, item: ScheduleItem) -> Optional[str]:
        """添加一条日程到 schedule 表。

        Args:
            item: ScheduleItem 对象

        Returns:
            新日程的 UUID，失败返回 None
        """
        schedule_id = str(uuid.uuid4())

        with self._lock:
            try:
                db = self._get_db()
                db.execute(
                    """INSERT INTO schedule
                    (id, title, description, start_time, end_time,
                     is_all_day, recurrence_rule, reminder_offset_min,
                     priority, status, source, location)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                    (
                        schedule_id,
                        item.title,
                        item.description,
                        item.start_time.isoformat(),
                        item.end_time.isoformat() if item.end_time else None,
                        1 if item.is_all_day else 0,
                        item.recurrence_rule or None,
                        item.reminder_offset_min,
                        item.priority,
                        item.source,
                        item.location,
                    ),
                )
                db.commit()
                logger.info(f"日程已创建: {item.title} ({schedule_id[:8]}...) @ {item.start_time}")
                return schedule_id

            except Exception as e:
                logger.exception(f"日程创建失败: {e}")
                return None

    def add_batch(self, items: List[ScheduleItem]) -> List[str]:
        """批量添加日程。

        Args:
            items: ScheduleItem 列表

        Returns:
            成功创建的日程 ID 列表
        """
        ids = []
        for item in items:
            sid = self.add_schedule(item)
            if sid:
                ids.append(sid)
        return ids

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """获取单条日程详情。"""
        try:
            db = self._get_db()
            db.row_factory = sqlite3.Row
            cursor = db.execute("SELECT * FROM schedule WHERE id = ?", (schedule_id,))
            row = cursor.fetchone()
            db.row_factory = None
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"获取日程失败: {e}")
            return None

    def get_schedules_by_date(self, date: datetime) -> List[Dict[str, Any]]:
        """获取指定日期的所有日程。

        Args:
            date: 目标日期

        Returns:
            日程字典列表
        """
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        return self.get_schedules_in_range(day_start, day_end)

    def get_schedules_in_range(
        self, start: datetime, end: datetime, include_completed: bool = False
    ) -> List[Dict[str, Any]]:
        """获取时间范围内的日程。
        """
        try:
            db = self._get_db()
            db.row_factory = sqlite3.Row

            status_filter = "AND status != 'cancelled'"
            if not include_completed:
                status_filter += " AND status != 'completed'"

            cursor = db.execute(
                f"""SELECT * FROM schedule
                    WHERE start_time < ? AND end_time > ?
                    {status_filter}
                    ORDER BY start_time ASC""",
                (end.isoformat(), start.isoformat()),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            db.row_factory = None
            return rows
        except Exception as e:
            logger.error(f"查询日程范围失败: {e}")
            return []

    def get_all_active(self) -> List[Dict[str, Any]]:
        """获取所有活跃日程。"""
        try:
            db = self._get_db()
            db.row_factory = sqlite3.Row
            cursor = db.execute(
                "SELECT * FROM schedule WHERE status = 'active' ORDER BY start_time ASC"
            )
            rows = [dict(r) for r in cursor.fetchall()]
            db.row_factory = None
            return rows
        except Exception as e:
            logger.error(f"获取活跃日程失败: {e}")
            return []

    def get_today_schedules(self) -> List[Dict[str, Any]]:
        """获取今日日程。"""
        return self.get_schedules_by_date(datetime.now())

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------

    def update_status(self, schedule_id: str, status: str) -> bool:
        """更新日程状态。

        Args:
            schedule_id: 日程 ID
            status: active / completed / cancelled / missed

        Returns:
            是否更新成功
        """
        valid = ("active", "completed", "cancelled", "missed")
        if status not in valid:
            logger.error(f"无效的日程状态: {status}")
            return False

        with self._lock:
            try:
                db = self._get_db()
                db.execute(
                    "UPDATE schedule SET status = ?, updated_at = ? WHERE id = ?",
                    (status, datetime.now().isoformat(), schedule_id),
                )
                db.commit()
                logger.info(f"日程状态更新: {schedule_id[:8]}... → {status}")
                return True
            except Exception as e:
                logger.error(f"更新日程状态失败: {e}")
                return False

    def update_schedule(self, schedule_id: str, updates: Dict[str, Any]) -> bool:
        """更新日程字段。

        Args:
            schedule_id: 日程 ID
            updates: 要更新的字段字典

        Returns:
            是否更新成功
        """
        allowed_fields = {
            "title", "description", "start_time", "end_time",
            "reminder_offset_min", "priority", "location",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return False

        filtered["updated_at"] = datetime.now().isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        values = list(filtered.values()) + [schedule_id]

        with self._lock:
            try:
                db = self._get_db()
                db.execute(f"UPDATE schedule SET {set_clause} WHERE id = ?", values)
                db.commit()
                logger.info(f"日程已更新: {schedule_id[:8]}...")
                return True
            except Exception as e:
                logger.error(f"更新日程失败: {e}")
                return False

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    def delete_schedule(self, schedule_id: str) -> bool:
        """删除日程（及其所有实例）。"""
        with self._lock:
            try:
                db = self._get_db()
                db.execute("DELETE FROM schedule_instance WHERE schedule_id = ?", (schedule_id,))
                db.execute("DELETE FROM schedule WHERE id = ?", (schedule_id,))
                db.commit()
                logger.info(f"日程已删除: {schedule_id[:8]}...")
                return True
            except Exception as e:
                logger.error(f"删除日程失败: {e}")
                return False

    # ------------------------------------------------------------------
    # 实例管理（重复日程）
    # ------------------------------------------------------------------

    def generate_instances(
        self, schedule_id: str, recurrence_rule: str, window_months: int = 3
    ) -> List[str]:
        """为重复日程生成未来实例。

        Args:
            schedule_id: 主日程 ID
            recurrence_rule: RFC 5545 规则
            window_months: 生成未来 N 个月的实例

        Returns:
            创建的实例 ID 列表
        """
        from modules.schedule.recurrence import RecurrenceEngine

        # 获取主日程
        parent = self.get_schedule(schedule_id)
        if not parent:
            return []

        # 解析重复规则生成日期列表
        engine = RecurrenceEngine()
        dates = engine.generate_dates(
            parent["start_time"],
            parent.get("end_time") or parent["start_time"],
            recurrence_rule,
            window_months=window_months,
        )

        # 批量创建实例
        instance_ids = []
        with self._lock:
            try:
                db = self._get_db()
                for d in dates:
                    iid = str(uuid.uuid4())
                    db.execute(
                        """INSERT INTO schedule_instance
                        (instance_id, schedule_id, original_start, actual_start, status)
                        VALUES (?, ?, ?, ?, 'active')""",
                        (iid, schedule_id, d.isoformat(), d.isoformat()),
                    )
                    instance_ids.append(iid)
                db.commit()
                logger.info(f"已生成 {len(dates)} 个重复日程实例 ({schedule_id[:8]}...)")
            except Exception as e:
                logger.error(f"生成实例失败: {e}")

        return instance_ids

    def update_instance(self, instance_id: str, actual_start: datetime, note: str = "") -> bool:
        """修改单个实例（断开与系列的链接）。"""
        with self._lock:
            try:
                db = self._get_db()
                db.execute(
                    "UPDATE schedule_instance SET actual_start = ?, note = ? WHERE instance_id = ?",
                    (actual_start.isoformat(), note, instance_id),
                )
                db.commit()
                return True
            except Exception as e:
                logger.error(f"更新实例失败: {e}")
                return False

    def get_instances_in_range(
        self, start: datetime, end: datetime
    ) -> List[Dict[str, Any]]:
        """获取时间范围内的日程实例。"""
        try:
            db = self._get_db()
            db.row_factory = sqlite3.Row
            cursor = db.execute(
                """SELECT si.*, s.title, s.description, s.priority
                   FROM schedule_instance si
                   JOIN schedule s ON si.schedule_id = s.id
                   WHERE si.actual_start < ? AND si.actual_start >= ?
                   AND si.status = 'active'
                   ORDER BY si.actual_start ASC""",
                (end.isoformat(), start.isoformat()),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            db.row_factory = None
            return rows
        except Exception as e:
            logger.error(f"查询实例失败: {e}")
            return []

    def get_missed_reminders(self) -> List[Dict[str, Any]]:
        """获取已错过但未处理的提醒（崩溃恢复用）。"""
        try:
            db = self._get_db()
            db.row_factory = sqlite3.Row
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            cursor = db.execute(
                """SELECT * FROM schedule
                   WHERE status = 'active'
                   AND start_time >= ? AND start_time < ?
                   ORDER BY start_time ASC""",
                (yesterday.isoformat(), now.isoformat()),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            db.row_factory = None
            return rows
        except Exception as e:
            logger.error(f"查询错过提醒失败: {e}")
            return []