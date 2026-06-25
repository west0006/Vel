"""
重复规则解析模块。

解析 RFC 5545 (iCalendar) 格式的重复规则，并生成未来日程实例。
支持常见的重复模式：每天/每周/每月/每年。
"""

from datetime import datetime, timedelta
from typing import List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class RecurrenceEngine:
    """重复日程引擎。

    解析 RFC 5545 FREQ=BASE;INTERVAL=N;BYDAY=MO,TU;... 格式规则，
    生成指定窗口内的日程实例日期列表。
    """

    # 星期缩写映射
    DAY_MAP = {
        "MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6,
        "MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6,
    }

    def parse_rule(self, rule: str) -> dict:
        """解析 RFC 5545 规则字符串为字典。

        Args:
            rule: 如 "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,WE,FR"

        Returns:
            {"freq": "WEEKLY", "interval": 1, "byday": ["MO","WE","FR"], ...}
        """
        parts = {}
        for segment in rule.split(";"):
            if "=" in segment:
                key, value = segment.split("=", 1)
                key = key.strip().lower()
                value = value.strip()

                if key == "interval":
                    parts[key] = int(value)
                elif key in ("byday", "bymonthday", "bymonth"):
                    parts[key] = [v.strip() for v in value.split(",")]
                else:
                    parts[key] = value

        if "interval" not in parts:
            parts["interval"] = 1

        return parts

    def to_rule_string(self, freq: str, interval: int = 1,
                       byday: Optional[List[str]] = None,
                       bymonthday: Optional[List[int]] = None) -> str:
        """将参数转换为 RFC 5545 规则字符串。

        Args:
            freq: DAILY / WEEKLY / MONTHLY / YEARLY
            interval: 间隔
            byday: 星期几（如 ["MO","WE","FR"]）
            bymonthday: 月内第几天（如 [1, 15]）

        Returns:
            RFC 5545 格式字符串
        """
        parts = [f"FREQ={freq.upper()}", f"INTERVAL={interval}"]
        if byday:
            parts.append(f"BYDAY={','.join(byday)}")
        if bymonthday:
            parts.append(f"BYMONTHDAY={','.join(str(d) for d in bymonthday)}")
        return ";".join(parts)

    # ------------------------------------------------------------------
    # 日期生成
    # ------------------------------------------------------------------

    def generate_dates(
        self,
        start: datetime,
        end: datetime,
        rule: str,
        window_months: int = 3,
    ) -> List[datetime]:
        """根据重复规则生成未来日期列表。

        Args:
            start: 首次开始时间
            end: 首次结束时间
            rule: RFC 5545 规则
            window_months: 生成未来 N 个月的实例

        Returns:
            datetime 列表
        """
        params = self.parse_rule(rule)
        freq = params.get("freq", "").upper()
        interval = params.get("interval", 1)
        interval = max(1, min(interval, 365))
        byday = params.get("byday", [])
        bymonthday = params.get("bymonthday", [])

        if freq == "DAILY":
            return self._generate_daily(start, interval, window_months)
        elif freq == "WEEKLY":
            days = [self.DAY_MAP.get(d.upper(), -1) for d in byday]
            days = [d for d in days if d >= 0] or [start.weekday()]
            return self._generate_weekly(start, interval, days, window_months)
        elif freq == "MONTHLY":
            days = [int(d) for d in bymonthday] if bymonthday else [start.day]
            return self._generate_monthly(start, interval, days, window_months)
        elif freq == "YEARLY":
            return self._generate_yearly(start, interval, window_months)
        else:
            logger.warning(f"不支持的重复频率: {freq}")
            return []

    def _generate_daily(
        self, start: datetime, interval: int, window_months: int
    ) -> List[datetime]:
        """每日重复。"""
        limit = start + timedelta(days=30 * window_months)
        current = start + timedelta(days=interval)  # 跳过第一天（已存在）
        dates = []
        while current < limit:
            dates.append(current)
            current += timedelta(days=interval)
        return dates

    def _generate_weekly(
        self, start: datetime, interval: int, days: List[int], window_months: int
    ) -> List[datetime]:
        """每周重复（指定星期几）。"""
        limit = start + timedelta(days=30 * window_months)
        current = start + timedelta(days=interval * 7)
        dates = []

        while current < limit:
            # 在目标周内找到所有匹配的星期几
            week_start = current - timedelta(days=current.weekday())
            for day_num in days:
                target = week_start + timedelta(days=day_num)
                if target > start and target < limit:
                    dates.append(target.replace(
                        hour=start.hour, minute=start.minute,
                        second=start.second, microsecond=start.microsecond,
                    ))
            current += timedelta(days=interval * 7)

        return sorted(dates)

    def _generate_monthly(
        self, start: datetime, interval: int, days: List[int], window_months: int
    ) -> List[datetime]:
        interval = max(1, interval)
        """每月重复。"""
        import calendar
        limit = start + timedelta(days=30 * window_months)
        current_month = start.month + interval
        current_year = start.year

        if current_month > 12:
            current_year += current_month // 12
            current_month = current_month % 12 or 12

        dates = []
        while True:
            month_days = calendar.monthrange(current_year, current_month)[1]
            for d in days:
                if 1 <= d <= month_days:
                    target = datetime(
                        current_year, current_month, d,
                        start.hour, start.minute,
                        start.second, start.microsecond,
                    )
                    if target < limit:
                        dates.append(target)

            if datetime(current_year, current_month, 1) > limit:
                break

            current_month += interval
            while current_month > 12:
                current_year += 1
                current_month -= 12

        return sorted(dates)

    def _generate_yearly(
        self, start: datetime, interval: int, window_months: int
    ) -> List[datetime]:
        """每年重复。"""
        limit = start + timedelta(days=30 * window_months)
        current_year = start.year + interval
        dates = []

        while True:
            target = start.replace(year=current_year)
            if target > limit:
                break
            dates.append(target)
            current_year += interval

        return dates

    # ------------------------------------------------------------------
    # 自然语言 → 规则（简化版）
    # ------------------------------------------------------------------

    def parse_natural_recurrence(self, text: str) -> Optional[str]:
        """从自然语言中提取重复规则（简化版）。

        Args:
            text: 自然语言文本

        Returns:
            RFC 5545 规则字符串，无法识别返回 None
        """
        import re

        text_lower = text.lower()

        # 每天
        if re.search(r'每[天日]', text_lower):
            return self.to_rule_string("DAILY", interval=1)

        # 每隔 N 天
        match = re.search(r'每隔?\s*(\d+)\s*天', text_lower)
        if match:
            return self.to_rule_string("DAILY", interval=int(match.group(1)))

        # 每周
        if "每周" in text_lower or "每个星期" in text_lower:
            # 提取星期
            week_map = {
                "一": "MO", "二": "TU", "三": "WE",
                "四": "TH", "五": "FR", "六": "SA", "日": "SU", "天": "SU",
            }
            days = re.findall(r'周([一二三四五六日天])', text)
            if days:
                byday = [week_map[d] for d in days]
                return self.to_rule_string("WEEKLY", interval=1, byday=byday)
            return self.to_rule_string("WEEKLY", interval=1)

        # 每月
        if "每月" in text_lower or "每个月" in text_lower:
            match = re.search(r'(\d{1,2})[日号]', text)
            if match:
                return self.to_rule_string("MONTHLY", interval=1, bymonthday=[int(match.group(1))])
            return self.to_rule_string("MONTHLY", interval=1)

        # 每年
        if "每年" in text_lower:
            return self.to_rule_string("YEARLY", interval=1)

        return None