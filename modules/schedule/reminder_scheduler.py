"""
提醒调度模块。

基于 APScheduler 实现日程提醒的调度、触发和通知。
支持双阶段提醒（预警 + 到期强提醒）、崩溃恢复和提醒偏移学习。
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from apscheduler.schedulers.qt import QtScheduler
from apscheduler.triggers.date import DateTrigger

from core.event_bus import bus, EVENT_SCHEDULE_ALERT
from core.service_registry import registry
from modules.schedule.schedule_store import ScheduleStore
from utils.logger import get_logger

logger = get_logger(__name__)


class ReminderScheduler:
    """提醒调度器。

    使用 APScheduler 管理所有提醒任务，支持：
    - 提前提醒（预警）
    - 到期提醒（强提醒）
    - 启动时从数据库恢复
    - 运行时快照（崩溃恢复）
    - 提醒偏移学习
    """

    def __init__(self, snapshot_path: str = ""):
        self._scheduler: Optional[QtScheduler] = None
        self._store: Optional[ScheduleStore] = None
        self._snapshot_path = snapshot_path or os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~/.config")),
            "SmartDesktopPet", "data", "runtime_snapshot.json",
        )
        self._on_trigger: Optional[Callable] = None

        # 提醒偏移学习记录
        self._offset_learning: Dict[str, Dict[str, Any]] = {}

        # 小睡计数
        self._snooze_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize(self, on_trigger: Callable[[Dict], None]) -> None:
        """初始化调度器。

        Args:
            on_trigger: 提醒触发时的回调函数
        """
        self._scheduler = QtScheduler()
        self._store = registry.get("schedule_store") or ScheduleStore()
        self._on_trigger = on_trigger
        self._scheduler.start()
        logger.info("提醒调度器已启动")
        self._setup_weekly_cleanup()

        # ------------------------------------------------------------------
    # 注册提醒
    # ------------------------------------------------------------------

    def register_reminder(self, schedule_id: str, start_time: datetime,
                          title: str, description: str = "",
                          reminder_offset_min: int = 15,
                          priority: int = 1,
                          location: str = "") -> None:
        """注册一条日程的提醒任务（预警 + 强提醒）。

        Args:
            schedule_id: 日程 ID
            start_time: 开始时间
            title: 日程标题
            description: 日程描述
            reminder_offset_min: 提前提醒分钟数
            priority: 优先级
            location: 地点
        """
        if self._scheduler is None:
            return

        # 计算预警时间
        advance_time = start_time - timedelta(minutes=reminder_offset_min)

        now = datetime.now()

        # 如果预警时间已过但日程未到，跳过预警
        if advance_time > now:
            self._add_job(
                schedule_id=schedule_id,
                run_time=advance_time,
                title=title,
                description=description,
                stage="advance",
                priority=priority,
                location=location,
                start_time_str=start_time.isoformat(),
            )

        # 到期提醒（如果还在未来）
        if start_time > now:
            self._add_job(
                schedule_id=schedule_id,
                run_time=start_time,
                title=title,
                description=description,
                stage="due",
                priority=priority,
                location=location,
            )

        logger.info(
            f"提醒已注册: {title} "
            f"(预警={advance_time.strftime('%H:%M')}, 到期={start_time.strftime('%H:%M')})"
        )

    def _add_job(self, schedule_id: str, run_time: datetime,
                 title: str, description: str, stage: str,
                 priority: int, location: str = "",
                 start_time_str: str = "") -> None:
        """添加单个 APScheduler 任务。"""
        job_id = f"{schedule_id}_{stage}"

        self._scheduler.add_job(
            func=self._on_reminder_trigger,
            trigger=DateTrigger(run_date=run_time),
            args=[{
                "schedule_id": schedule_id,
                "title": title,
                "description": description,
                "stage": stage,       # advance / due
                "priority": priority,
                "location": location,
            }],
            id=job_id,
            replace_existing=True,
        )

    def _on_reminder_trigger(self, data: Dict[str, Any]) -> None:
        """提醒触发时的内部处理。"""
        schedule_id = data.get("schedule_id", "")
        title = data.get("title", "")
        stage = data.get("stage", "due")

        logger.info(f"提醒触发: {title} (阶段={stage})")

        # 更新日程状态（到期提醒触发时标记）
        if stage == "due":
            # 不立即标记完成，等用户操作
            pass

        # 发布提醒事件
        bus.publish(EVENT_SCHEDULE_ALERT, {
            "schedule_id": schedule_id,
            "title": title,
            "description": data.get("description", ""),
            "stage": stage,
            "priority": data.get("priority", 1),
            "location": data.get("location", ""),
            "timestamp": datetime.now().isoformat(),
        })

        # 调用外部回调
        if self._on_trigger:
            self._on_trigger(data)

    # ------------------------------------------------------------------
    # 小睡功能
    # ------------------------------------------------------------------

    def snooze(self, schedule_id: str, minutes: int = 5) -> bool:
        """将提醒小睡指定分钟。

        Args:
            schedule_id: 日程 ID
            minutes: 推迟分钟数

        Returns:
            是否成功设置小睡
        """
        # 检查小睡次数
        max_snoozes = 3
        count = self._snooze_counts.get(schedule_id, 0)
        if count >= max_snoozes:
            logger.warning(f"日程 {schedule_id[:8]}... 已小睡 {count} 次，超出上限")
            # 标记为已错过
            self._store.update_status(schedule_id, "missed")
            return False

        self._snooze_counts[schedule_id] = count + 1

        # 移除旧的 due 任务
        job_id = f"{schedule_id}_due"
        if self._scheduler and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        # 获取日程信息
        schedule = self._store.get_schedule(schedule_id)
        if not schedule:
            return False

        # 添加新任务
        run_time = datetime.now() + timedelta(minutes=minutes)
        self._add_job(
            schedule_id=schedule_id,
            run_time=run_time,
            title=schedule["title"],
            description=schedule.get("description", ""),
            stage="due",
            priority=schedule.get("priority", 1),
        )

        logger.info(f"提醒已小睡: {schedule_id[:8]}... → {run_time.strftime('%H:%M')} (第{count+1}次)")
        return True

    def mark_completed(self, schedule_id: str) -> None:
        """标记日程已完成，移除所有提醒任务。"""
        self._remove_jobs(schedule_id)
        self._snooze_counts.pop(schedule_id, None)
        self._store.update_status(schedule_id, "completed")

    def mark_missed(self, schedule_id: str) -> None:
        """标记日程已错过。"""
        self._remove_jobs(schedule_id)
        self._snooze_counts.pop(schedule_id, None)
        self._store.update_status(schedule_id, "missed")

    def _remove_jobs(self, schedule_id: str) -> None:
        """移除指定日程的所有 APScheduler 任务。"""
        if self._scheduler is None:
            return
        for stage in ("advance", "due"):
            job_id = f"{schedule_id}_{stage}"
            if self._scheduler.get_job(job_id):
                self._scheduler.remove_job(job_id)

    # ------------------------------------------------------------------
    # 提醒偏移学习
    # ------------------------------------------------------------------

    def record_feedback(self, schedule_id: str, action: str) -> None:
        """记录用户对提醒的反馈，用于学习偏移量。

        Args:
            schedule_id: 日程 ID
            action: "snooze" / "complete" / "ignore"
        """
        schedule = self._store.get_schedule(schedule_id)
        if not schedule:
            return

        title = schedule.get("title", "")
        # 简单分类：从标题提取类型（会议、约会等）
        category = "default"
        for kw, cat in [("会议", "meeting"), ("团建", "gathering"),
                        ("医疗", "medical"), ("约会", "date"),
                        ("上课", "class"), ("面试", "interview")]:
            if kw in title:
                category = cat
                break

        # 更新学习记录
        if category not in self._offset_learning:
            self._offset_learning[category] = {
                "snooze_count": 0,
                "total_count": 0,
                "current_offset": schedule.get("reminder_offset_min", 15),
            }

        learning = self._offset_learning[category]
        learning["total_count"] += 1
        if action == "snooze":
            learning["snooze_count"] += 1

        # 连续3次延迟 → 偏移量+5分钟
        if learning["snooze_count"] >= 3:
            new_offset = min(learning["current_offset"] + 5, 60)
            learning["current_offset"] = new_offset
            learning["snooze_count"] = 0
            logger.info(f"提醒偏移学习: {category} 偏移量 → {new_offset} 分钟")

            # 存储到数据库
            try:
                db = registry.get("database")
                if db:
                    key = f"reminder_offset_{category}"
                    db.execute(
                        "INSERT OR REPLACE INTO user_traits (trait_name, value, confidence, source) "
                        "VALUES (?, ?, ?, 'auto')",
                        (key, str(new_offset), 0.6),
                    )
                    db.commit()
            except Exception as e:
                logger.warning(f"偏移量存储失败: {e}")

    def get_learned_offset(self, category: str = "default") -> int:
        """获取学习到的提醒偏移量。"""
        if category in self._offset_learning:
            return self._offset_learning[category]["current_offset"]
        return 15

    # ------------------------------------------------------------------
    # 恢复与快照
    # ------------------------------------------------------------------

    def rebuild_from_database(self) -> int:
        """从数据库重建所有活跃提醒。

        Returns:
            重建的提醒数量
        """
        schedules = self._store.get_all_active()
        now = datetime.now()
        count = 0

        for s in schedules:
            start_time = datetime.fromisoformat(s["start_time"])
            if start_time < now - timedelta(hours=24):
                continue  # 超过24小时的过期日程跳过

            self.register_reminder(
                schedule_id=s["id"],
                start_time=start_time,
                title=s["title"],
                description=s.get("description", ""),
                reminder_offset_min=s.get("reminder_offset_min", 15),
                priority=s.get("priority", 1),
                location=s.get("location", ""),
            )
            count += 1

        logger.info(f"从数据库重建 {count} 条提醒")
        return count

    def save_snapshot(self) -> None:
        """保存运行时快照（崩溃恢复用）。"""
        if self._scheduler is None:
            return

        jobs_data = []
        for job in self._scheduler.get_jobs():
            jobs_data.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })

        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "jobs": jobs_data,
            "snooze_counts": self._snooze_counts,
            "offset_learning": {k: {sk: sv for sk, sv in v.items()}
                              for k, v in self._offset_learning.items()},
        }

        try:
            os.makedirs(os.path.dirname(self._snapshot_path), exist_ok=True)
            tmp = self._snapshot_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._snapshot_path)
            logger.debug("运行时快照已保存")
        except Exception as e:
            logger.warning(f"快照保存失败: {e}")

    def load_snapshot(self) -> bool:
        """加载运行时快照，恢复调度器状态。"""
        if not os.path.exists(self._snapshot_path):
            return False

        try:
            with open(self._snapshot_path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)

            self._snooze_counts = snapshot.get("snooze_counts", {})
            self._offset_learning = snapshot.get("offset_learning", {})

            logger.info("运行时快照已加载")
            return True
        except Exception as e:
            logger.warning(f"快照加载失败: {e}")
            return False

    def _setup_weekly_cleanup(self) -> None:
        """每周日凌晨清理 7 天前已完成的重复实例。"""
        try:
            from apscheduler.triggers.cron import CronTrigger
            self._scheduler.add_job(
                func=self._cleanup_old_instances,
                trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
                id="schedule_instance_cleanup",
                replace_existing=True,
            )
            logger.info("重复实例清理任务已注册（每周日 03:00）")
        except Exception as e:
            logger.warning(f"实例清理任务注册失败: {e}")

    def _cleanup_old_instances(self) -> None:
        """清理 7 天前已完成/错过的重复实例。"""
        try:
            if self._store is None:
                return
            db = registry.get("database")
            if db is None:
                return
            cursor = db.execute(
                "DELETE FROM schedule_instance "
                "WHERE status IN ('completed','missed') "
                "AND actual_start < date('now', '-7 days')"
            )
            deleted = cursor.rowcount
            db.commit()
            if deleted > 0:
                logger.info(f"已清理 {deleted} 条过期重复实例")
        except Exception as e:
            logger.warning(f"实例清理失败: {e}")

    def shutdown(self) -> None:
        """关闭调度器。"""
        if self._scheduler:
            self.save_snapshot()
            self._scheduler.shutdown(wait=False)
            logger.info("提醒调度器已关闭")