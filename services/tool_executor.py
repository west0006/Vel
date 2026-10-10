"""
工具执行器。终结型工具结果即回复，中间型抛回 LLM 总结。
"""

from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class ToolExecutor:
    """工具执行器。execute(tool_name, params) -> (result, is_terminal)。"""

    MAX_SEARCH_RESULT_CHARS = 800

    def execute(self, tool_name: str, params: Dict[str, Any]) -> Tuple[str, bool]:
        """执行工具。返回 (结果文本, 是否终结型)。"""
        method = getattr(self, f"_tool_{tool_name}", None)
        if method is None:
            return f"未知工具: {tool_name}", True
        try:
            return method(params)
        except Exception as e:
            logger.exception(f"工具执行失败 [{tool_name}]: {e}")
            return f"工具执行出错，请换个说法试试喵~", True

    # ──────── 终结型 ────────

    def _tool_create_reminder(self, params: dict) -> Tuple[str, bool]:
        title = params.get("title", "日程")
        time_str = params.get("time", "")
        text = f"{time_str} {title}"

        from modules.schedule.schedule_parser import ScheduleParser
        from modules.schedule.schedule_store import ScheduleStore

        parser = ScheduleParser()
        store = registry.get("schedule_store") or ScheduleStore()
        items = parser.parse_single(text)
        if not items:
            return "没能理解时间，试试「明天下午3点开会」这样的说法喵~", True

        item = items[0]
        parser.add_pending(item)  # 加入冲突缓存
        sid = store.add_schedule(item)
        if sid:
            rs = registry.get("reminder_scheduler")
            if rs:
                rs.register_reminder(
                    sid, item.start_time, item.title,
                    item.description, item.reminder_offset_min, item.priority,
                )
            return f"已创建日程：{item.title} @ {item.start_time.strftime('%m/%d %H:%M')}", True
        return "日程创建失败，稍后重试喵~", True

    def _tool_create_memo(self, params: dict) -> Tuple[str, bool]:
        content = params.get("content", "")
        time_str = params.get("time", "")
        text = f"记一下：{content}"
        if time_str:
            text = f"记一下：{time_str} {content}"

        mm = registry.get("memo_manager")
        if mm is None:
            return "备忘录功能暂不可用喵~", True

        result = mm.parse_and_create(text)
        if result:
            remind = result.get("remind_at")
            c = result.get("content", content)
            if remind:
                return f"已记录：{remind.strftime('%m/%d %H:%M')} {c}", True
            return f"已记录：{c}", True
        return "备忘录创建失败，试试「记一下买牛奶」喵~", True

    def _tool_query_schedule(self, params: dict) -> Tuple[str, bool]:
        store = registry.get("schedule_store")
        if store is None:
            return "日程功能暂不可用喵~", True

        date_str = params.get("date", "")
        if date_str:
            try:
                from dateparser import parse
                target = parse(date_str)
                if target:
                    items = store.get_schedules_by_date(target)
                else:
                    items = store.get_today_schedules()
            except Exception:
                items = store.get_today_schedules()
        else:
            items = store.get_today_schedules()

        if not items:
            return "今天没有日程喵~", True

        lines = []
        for s in items[:5]:
            st = s.get("start_time", "")
            if st and len(st) > 10:
                st = st[11:16]
            status = "✅" if s.get("status") == "completed" else "📌"
            lines.append(f"{status} {st} {s.get('title','')}")
        return "📅 今日日程：\n" + "\n".join(lines), True

    def _tool_get_diary(self, params: dict) -> Tuple[str, bool]:
        diary = registry.get("diary_generator")
        if diary is None:
            return "日记功能暂不可用喵~", True

        date_str = params.get("date", "")
        target_date = date.today()
        if date_str:
            try:
                from dateparser import parse
                parsed = parse(date_str)
                if parsed:
                    target_date = parsed.date()
            except Exception:
                logger.exception("_tool_get_diary 执行失败")

        summary = diary.get_diary(target_date) or diary.generate(target_date)
        return summary or f"{target_date} 还没有日记喵~", True

    # ──────── 中间型 ────────

    def _tool_search_web(self, params: dict) -> Tuple[str, bool]:
        query = params.get("query", "")
        if not query:
            return "请提供搜索关键词喵~", True

        svc = registry.get("search_service")
        if svc is None:
            return "搜索功能暂不可用喵~", True

        result = svc.search(query, max_results=3)
        if not result or "暂不可用" in result:
            return "搜索暂时不可用，请稍后重试喵~", True

        return result[:self.MAX_SEARCH_RESULT_CHARS], False
