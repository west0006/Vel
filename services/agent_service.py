"""
独立 Agent 服务。用轻量模型做意图路由，每个功能解耦为独立 handler。
"""

import requests
from typing import Any, Callable, Dict, List, Optional

from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)

CLASSIFY_PROMPT = """分析用户输入，只回复一个词表示意图：

chat | schedule | memo | diary | search | location | egg | help | habit

示例：
"你好" → chat
"明天下午3点开会" → schedule
"记一下买牛奶" → memo
"今天日记" → diary
"天气怎么样" → search
"我在哪" → location
"喵喵喵" → egg
"你能做什么" → help
"我要养成每天阅读的习惯" "今天阅读打卡" → habit

用户输入: {input}
意图:"""


class AgentService:
    """独立 Agent 服务。

    用轻量模型做快速意图分类（2秒内），路由到各 handler。
    所有 handler 注册到 _handlers 字典，新增功能只需一行。
    """

    def __init__(self, router_model: str = "qwen2.5:3b", router_host: str = "127.0.0.1:11434"):
        self._router_model = router_model
        self._router_url = f"http://{router_host}/api/chat"
        self._handlers: Dict[str, Callable] = {}
        self._register_default_handlers()
        self._warm_up()

    def _warm_up(self) -> None:
        """预热轻量模型，首次调用时加载到显存。"""
        try:
            import threading
            def _warm():
                requests.post(self._router_url, json={
                    "model": self._router_model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "options": {"num_predict": 2},
                    "stream": False,
                }, timeout=30)
                logger.info(f"Agent模型 {self._router_model} 预热完成")

            threading.Thread(target=_warm, daemon=True).start()
        except Exception:
            pass

    def _register_default_handlers(self) -> None:
        self.register("schedule", self._handle_schedule)
        self.register("memo", self._handle_memo)
        self.register("diary", self._handle_diary)
        self.register("location", self._handle_location)
        self.register("help", self._handle_help)
        self.register("habit", self._handle_habit)
        # chat / search / egg → 返回 None，走正常对话流程

    def register(self, intent: str, handler: Callable[[str], Optional[str]]) -> None:
        self._handlers[intent] = handler
        logger.info(f"Agent handler 已注册: {intent}")

    def classify(self, user_input: str) -> str:
        start = __import__('time').time()
        try:
            resp = requests.post(
                self._router_url,
                json={
                    "model": self._router_model,
                    "messages": [
                        {"role": "system", "content": "你只回复一个英文单词。不要解释。"},
                        {"role": "user", "content": CLASSIFY_PROMPT.format(input=user_input[:200])},
                    ],
                    "options": {"temperature": 0, "num_predict": 8},
                    "stream": False,
                },
                timeout=20,
            )
            elapsed = __import__('time').time() - start
            text = resp.json().get("message", {}).get("content", "").strip().lower()
            logger.debug(f"Agent分类: [{elapsed:.1f}s] raw={text[:30]}")

            valid = set(self._handlers.keys()) | {"chat", "search", "egg"}
            for w in text.split():
                if w in valid:
                    logger.info(f"Agent意图: {w}")
                    return w
            logger.debug(f"Agent分类无效: {text}")
            return "chat"
        except Exception as e:
            elapsed = __import__('time').time() - start
            logger.warning(f"Agent分类失败 [{elapsed:.1f}s]: {e}")
            return "chat"

    def handle(self, user_input: str) -> Optional[str]:
        intent = self.classify(user_input)

        # egg 直接走彩蛋模块
        if intent == "egg":
            try:
                ee = registry.get("easter_egg_engine")
                if ee:
                    egg = ee.match(user_input)
                    if egg:
                        return egg["reply"]
            except Exception:
                pass
            return None

        handler = self._handlers.get(intent)
        if handler is None:
            return None
        try:
            return handler(user_input)
        except Exception as e:
            logger.warning(f"Agent handler [{intent}] 异常: {e}")
            return None

    # ────────────────── handlers ──────────────────

    def _handle_schedule(self, text: str) -> Optional[str]:
        try:
            from modules.schedule.schedule_parser import ScheduleParser
            from modules.schedule.schedule_store import ScheduleStore
            parser = ScheduleParser()
            store = registry.get("schedule_store") or ScheduleStore()
            items = parser.parse_single(text)
            if items:
                item = items[0]
                sid = store.add_schedule(item)
                if sid:
                    rs = registry.get("reminder_scheduler")
                    if rs:
                        rs.register_reminder(sid, item.start_time, item.title,
                                             item.description, item.reminder_offset_min, item.priority)
                return f"已创建日程：{item.title} @ {item.start_time.strftime('%m/%d %H:%M')}"
        except Exception:
            pass
        return None

    def _handle_memo(self, text: str) -> Optional[str]:
        mm = registry.get("memo_manager")
        if mm is None:
            return None
        result = mm.parse_and_create(text)
        if result:
            remind = result.get("remind_at")
            content = result.get("content", "")
            if remind:
                return f"已记录备忘录：{remind.strftime('%m/%d %H:%M')} {content}"
            return f"已记录：{content}"
        return None

    def _handle_diary(self, text: str) -> Optional[str]:
        diary = registry.get("diary_generator")
        if diary is None:
            return None
        from datetime import date, timedelta
        target = date.today()
        if "昨天" in text: target -= timedelta(days=1)
        elif "前天" in text: target -= timedelta(days=2)
        summary = diary.get_diary(target) or diary.generate(target)
        return summary if summary else None

    def _handle_location(self, text: str) -> Optional[str]:
        loc = registry.get("location_service")
        if loc is None:
            return None
        data = loc.get_location(force_refresh=True)
        if not data:
            return "暂时获取不到位置信息喵~"

        city = data.get("city", "")
        province = data.get("province", "")
        if isinstance(city, list): city = city[0] if city else ""
        if isinstance(province, list): province = province[0] if province else ""
        city = str(city).strip() if city else ""
        province = str(province).strip() if province else ""

        if not city and not province:
            return "喵~ 暂时无法定位你的位置，可以试试手动输入城市名 📍"
        addr = f"{province}{city}" if province != city else city
        return f"你现在大概在 {addr} 附近喵~ 📍"

    def _handle_habit(self, text: str) -> Optional[str]:
        hm = registry.get("habit_manager")
        if hm is None:
            return None
        if "打卡" in text or "签到" in text:
            habits = hm.list_all()
            if not habits:
                return "你还没有创建习惯喵~ 试试说「我要养成每天读书的习惯」"
            best = None
            for h in habits:
                if h["name"] in text:
                    best = h;
                    break
            if best is None:
                best = habits[0]
            result = hm.check_in(best["id"])
            if result:
                if result.get("already"):
                    return f"今天已经打过「{result['name']}」的卡啦~ 明天继续加油！"
                fire = "🔥" * min(result["streak"], 5)
                return f"「{result['name']}」打卡成功！{fire} 连续 {result['streak']} 天"
        # 创建习惯：每天/每日/每一天
        import re
        m = re.search(r'每[天日].+?的?(.+?)(?:习惯|，|。|$)', text)
        if m:
            name = m.group(1).strip()[:20]
            tm = "21:00"
            tm_match = re.search(r'(\d{1,2})[点时](\d{1,2})?分?', text)
            if tm_match:
                h = tm_match.group(1).zfill(2)
                m2 = tm_match.group(2) or "00"
                tm = f"{h}:{m2}"
            hid = hm.create(name, tm)
            if hid:
                return f"习惯已创建：「{name}」⏰ 每天 {tm} 提醒你~"
        return None

    def _handle_help(self, text: str) -> Optional[str]:
        return (
            "我可以帮你这些事喵~\n"
            "创建日程：「明天下午3点开会」\n"
            "记备忘录：「记一下买牛奶」\n"
            "写日记：「今天日记」\n"
            "搜索：「今天天气」\n"
            "查位置：「我在哪」\n"
            "聊天：随便说什么都行～"
        )