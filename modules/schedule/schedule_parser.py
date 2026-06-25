"""
日程解析模块。

支持三种输入方式：
- 单句文字：dateparser + 正则提取 → LLM 兜底
- 长文本：分句 → 逐句 LLM 判断是否含日程
- OCR 文字：同长文本处理

输出结构化 ScheduleItem 列表。
"""

import re
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ScheduleItem:
    """结构化日程项。"""
    title: str
    start_time: datetime
    end_time: Optional[datetime] = None
    description: str = ""
    location: str = ""
    priority: int = 1           # 0低/1中/2高
    is_all_day: bool = False
    recurrence_rule: str = ""   # RFC 5545
    reminder_offset_min: int = 15
    source: str = "manual"      # manual / ocr / import
    raw_text: str = ""          # 原始输入文本

    def __post_init__(self):
        if self.end_time is None:
            self.end_time = self.start_time + timedelta(hours=1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "description": self.description,
            "location": self.location,
            "priority": self.priority,
            "is_all_day": self.is_all_day,
            "recurrence_rule": self.recurrence_rule,
            "reminder_offset_min": self.reminder_offset_min,
            "source": self.source,
        }


class ScheduleParser:
    """日程解析器。

    解析自然语言输入为结构化日程列表。
    使用 dateparser + 正则提取作为主解析器，LLM 兜底。
    """

    def __init__(self):
        self._llm_service = None

    def _get_llm(self) -> Any:
        """懒加载 LLM 服务。"""
        if self._llm_service is None:
            self._llm_service = registry.get("llm_service")
        return self._llm_service

    # ------------------------------------------------------------------
    # 单句解析
    # ------------------------------------------------------------------

    def parse_single(self, text: str) -> List[ScheduleItem]:
        """解析单句文字为日程列表。

        Args:
            text: 单句自然语言输入

        Returns:
            ScheduleItem 列表（通常1条）
        """
        logger.info(f"解析单句日程: {text[:80]}...")

        # 第一步：尝试 dateparser + 正则提取
        item = self._quick_parse(text)
        if item and self._is_valid(item):
            logger.info(f"快速解析成功: {item.title} @ {item.start_time}")
            return [item]

        # 第二步：LLM 兜底
        logger.info("快速解析失败，使用 LLM 兜底")
        return self._llm_parse(text)

    def _quick_parse(self, text: str) -> Optional[ScheduleItem]:
        """使用 dateparser + 正则进行快速解析。

        Args:
            text: 输入文本

        Returns:
            解析成功返回 ScheduleItem，否则 None
        """
        import dateparser

        title = text
        start_time = None

        # 尝试提取时间短语
        # 匹配常见中文时间模式
        time_patterns = [
            # "明天下午3点"
            r'(明天|后天|今天|下周[一二三四五六日天]|下下?周[一二三四五六日天]|'
            r'\d{1,2}月\d{1,2}[日号]|'
            r'周[一二三四五六日天]|'
            r'下?个?月\d{1,2}[日号]?)\s*'
            r'(早上|上午|中午|下午|傍晚|晚上|凌晨)?\s*'
            r'(\d{1,2})[点:：](\d{1,2})?[分]?',
            # "11点开会", "下午3点"（含可选时段前缀）
            r'(早上|上午|中午|下午|傍晚|晚上|凌晨)?\s*(\d{1,2})[点:：](\d{1,2})?[分]?',
        ]

        time_phrase = None
        for pattern in time_patterns:
            match = re.search(pattern, text)
            if match:
                time_phrase = match.group(0)
                # 第二组：补全丢失的时段前缀（如"下午"）
                if match.lastindex and match.group(1):
                    time_phrase = match.group(1) + time_phrase.lstrip(match.group(1))
                break

        if time_phrase:
            # 使用 dateparser 解析
            try:
                settings = {
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': datetime.now(),
                }
                parsed = dateparser.parse(time_phrase, settings=settings)
                if parsed:
                    start_time = parsed
                    # 从文本中移除时间短语得到标题
                    title = text.replace(time_phrase, "").strip()
                    # 清理标题
                    title = re.sub(r'^[提醒我]?[要记得记]?[，,。.]?\s*', '', title)
            except Exception as e:
                logger.debug(f"dateparser 解析失败: {e}")

        if start_time is None:
            return None

        if not title:
            title = f"日程 ({start_time.strftime('%H:%M')})"

        # 提取优先级关键词
        priority = 1
        if any(w in text for w in ["重要", "紧急", "必须", "一定要"]):
            priority = 2

        return ScheduleItem(
            title=title,
            start_time=start_time,
            priority=priority,
            raw_text=text,
        )

    def _is_valid(self, item: ScheduleItem) -> bool:
        """校验解析结果是否合理。"""
        if not item.title or len(item.title) < 2:
            return False
        if item.start_time < datetime.now() - timedelta(minutes=30):
            return False  # 30分钟前的日程
        return True

    # ------------------------------------------------------------------
    # 长文本解析
    # ------------------------------------------------------------------

    def parse_long_text(self, text: str) -> List[ScheduleItem]:
        """解析长文本（多句），每句独立判断是否含日程。

        Args:
            text: 长文本（如邮件、通知）

        Returns:
            ScheduleItem 列表
        """
        if len(text) <= 80:
            return self.parse_single(text)

        # 分句
        sentences = self._split_sentences(text)

        # 逐句尝试快速解析
        results = []
        for sent in sentences:
            if len(sent) < 5:
                continue
            # 快速预判：是否包含时间相关词
            if not self._likely_schedule(sent):
                continue
            items = self.parse_single(sent)
            results.extend(items)

        if not results:
            # 全部快速解析失败，使用 LLM 批量提取
            logger.info("快速解析全部失败，使用 LLM 批量提取")
            results = self._llm_parse(text)

        return results

    def parse_from_ocr(self, text: str) -> List[ScheduleItem]:
        """解析 OCR 提取的文字（同长文本处理）。"""
        return self.parse_long_text(text)

    def _split_sentences(self, text: str) -> List[str]:
        """将文本按句子分割。"""
        # 按常见分隔符分割
        sentences = re.split(r'[。！？\n;；，,](?![0-9])', text)
        return [s.strip() for s in sentences if s.strip()]

    def _likely_schedule(self, text: str) -> bool:
        """预判文本是否可能包含日程信息。"""
        time_keywords = [
            "今天", "明天", "后天", "下周", "下个月",
            "点", "分", "时", "月", "日", "号",
            "上午", "下午", "晚上", "中午",
            "提醒", "会议", "开会", "截止", "预约",
            "ddl", "deadline", "日程",
        ]
        return any(kw in text for kw in time_keywords)

    # ------------------------------------------------------------------
    # LLM 兜底解析
    # ------------------------------------------------------------------

    def _llm_parse(self, text: str) -> List[ScheduleItem]:
        """使用 LLM 解析日程文本。

        Args:
            text: 待解析文本

        Returns:
            ScheduleItem 列表
        """
        llm = self._get_llm()
        if llm is None:
            logger.warning("LLM 服务不可用，无法解析日程")
            return []

        prompt = (
            "你是一个日程解析助手。请从以下文本中提取所有日程，输出 JSON 数组。\n"
            "每个日程包含: title(标题), start_time(开始时间, ISO格式), "
            "end_time(结束时间, 可为null), description(描述), "
            "location(地点), priority(0低/1中/2高, 默认1), "
            "is_all_day(false), reminder_offset_min(提前提醒分钟, 默认15)。\n"
            "当前时间: {now}\n"
            "文本: {text}\n"
            "请只输出 JSON 数组，不要其他内容。如果没有日程，输出 []。"
        ).format(
            now=datetime.now().isoformat(),
            text=text,
        )

        try:
            # 使用 LLM 的 generate 方法（不走对话历史）
            if hasattr(llm, '_call_ollama'):
                reply = llm._call_ollama([
                    {"role": "system", "content": "你是一个精确的日程解析助手，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ])
            else:
                reply = llm.generate(prompt)

            # 提取 JSON
            reply = reply.strip()
            # 尝试找到 JSON 数组
            start = reply.find('[')
            end = reply.rfind(']')
            if start >= 0 and end > start:
                reply = reply[start:end + 1]

            items = json.loads(reply)

            result = []
            for item in items:
                si = ScheduleItem(
                    title=item.get("title", ""),
                    start_time=datetime.fromisoformat(item["start_time"]),
                    end_time=datetime.fromisoformat(item["end_time"]) if item.get("end_time") else None,
                    description=item.get("description", ""),
                    location=item.get("location", ""),
                    priority=item.get("priority", 1),
                    is_all_day=item.get("is_all_day", False),
                    reminder_offset_min=item.get("reminder_offset_min", 15),
                    source="manual",
                    raw_text=text,
                )
                if self._is_valid(si):
                    result.append(si)

            return result

        except json.JSONDecodeError as e:
            logger.error(f"LLM 日程解析 JSON 错误: {e}, raw={reply[:200]}")
            return []
        except Exception as e:
            logger.exception(f"LLM 日程解析失败: {e}")
            return []

    # ------------------------------------------------------------------
    # 冲突检测
    # ------------------------------------------------------------------

    def check_conflict(
        self, items: List[ScheduleItem], existing: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """检测新日程与已有日程的冲突。

        Args:
            items: 新日程列表
            existing: 已有日程列表 [{title, start_time, end_time}, ...]

        Returns:
            冲突列表 [{new_item, existing_item, overlap_type}, ...]
        """
        conflicts = []
        for new_item in items:
            new_start = new_item.start_time
            new_end = new_item.end_time or new_start + timedelta(hours=1)

            for ex_item in existing:
                ex_start = ex_item.get("start_time")
                ex_end = ex_item.get("end_time")
                if isinstance(ex_start, str):
                    ex_start = datetime.fromisoformat(ex_start)
                if isinstance(ex_end, str):
                    ex_end = datetime.fromisoformat(ex_end)
                if ex_end is None:
                    ex_end = ex_start + timedelta(hours=1)

                # 检查时间重叠
                if new_start < ex_end and new_end > ex_start:
                    overlap_type = "partial"
                    if new_start <= ex_start and new_end >= ex_end:
                        overlap_type = "contains"
                    elif ex_start <= new_start and ex_end >= new_end:
                        overlap_type = "contained_by"

                    conflicts.append({
                        "new_item": new_item.to_dict(),
                        "existing_item": {
                            "title": ex_item.get("title", ""),
                            "start_time": ex_start.isoformat(),
                            "end_time": ex_end.isoformat(),
                        },
                        "overlap_type": overlap_type,
                    })

        return conflicts