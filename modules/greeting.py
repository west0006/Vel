"""
智能问候模块。

每日首次唤醒时生成个性化问候。
"""

from datetime import date, datetime
from typing import Optional

from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class GreetingService:
    """每日问候服务。"""

    def check_and_greet(self) -> Optional[str]:
        """检查是否应该问候，是则返回问候语。"""
        today = date.today().isoformat()

        # 检查今日是否已问候
        try:
            db = registry.get("database")
            if db:
                row = db.execute(
                    "SELECT value FROM app_settings WHERE key='last_greeting_date'"
                ).fetchone()
                if row and row[0] == today:
                    return None  # 今日已问候
        except Exception:
            logger.exception("check_and_greet 执行失败")

        # 收集上下文
        context = self._collect_context()
        greeting = self._generate(context)

        # 记录日期
        try:
            db = registry.get("database")
            if db:
                db.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('last_greeting_date', ?)",
                    (today,),
                )
                db.commit()
        except Exception:
            logger.exception("check_and_greet 执行失败")

        logger.info(f"问候已生成: {greeting[:40]}...")
        return greeting

    def _collect_context(self) -> dict:
        ctx = {"period": self._get_period(), "weather": "", "mood": "", "nickname": "用户"}

        # 昵称
        try:
            pm = registry.get("profile_manager")
            if pm:
                nick = pm.get_profile("nickname", "")
                if nick: ctx["nickname"] = nick
        except Exception:
            logger.exception("_collect_context 执行失败")

        # 天气（wttr.in 免费无Key，<2s）
        try:
            import requests
            resp = requests.get("https://wttr.in/?format=%C+%t", timeout=3,
                                headers={"User-Agent": "curl/7.0"})
            if resp.status_code == 200 and resp.text.strip():
                ctx["weather"] = resp.text.strip()  # 如 "☀️ +22°C"
        except Exception:
            logger.exception("_collect_context 执行失败")

        # 情绪
        try:
            db = registry.get("database")
            if db:
                row = db.execute(
                    "SELECT mood_label FROM mood_snapshot ORDER BY timestamp DESC LIMIT 1"
                ).fetchone()
                if row:
                    ctx["mood"] = {"positive": "开心", "neutral": "平静", "negative": "有点累"}.get(row[0], "")
        except Exception:
            logger.exception("_collect_context 执行失败")

        return ctx

    def _get_period(self) -> str:
        h = datetime.now().hour
        if 5 <= h < 9: return "早上"
        if 9 <= h < 12: return "上午"
        if 12 <= h < 14: return "中午"
        if 14 <= h < 18: return "下午"
        if 18 <= h < 22: return "晚上"
        return "晚上"

    def _generate(self, ctx: dict) -> str:
        """调用 LLM 生成短问候。"""
        llm = registry.get("llm_service")
        if llm is None:
            return f"{ctx['period']}好呀~ {ctx['nickname']}，新的一天也要元气满满喵！☀️"

        prompt = (
            f"生成一句{ctx['period']}问候语，不超过50字，语气温柔猫咪口吻。"
            f"昵称: {ctx['nickname']}"
        )
        if ctx.get("weather"):
            prompt += f" 天气: {ctx['weather']}"
        if ctx.get("mood"):
            prompt += f" 昨日心情: {ctx['mood']}"

        # 用轻量模型生成（非阻塞，超时短）
        try:
            import requests
            resp = requests.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": "qwen2.5:3b",
                    "messages": [
                        {"role": "system", "content": "你是猫咪助手，回复50字以内。"},
                        {"role": "user", "content": prompt},
                    ],
                    "options": {"temperature": 0.7, "num_predict": 60},
                    "stream": False,
                },
                timeout=10,
            )
            text = resp.json().get("message", {}).get("content", "").strip()
            return text if text else f"{ctx['period']}好呀，{ctx['nickname']}~ 今天也要加油喵！☀️"
        except Exception:
            return f"{ctx['period']}好呀，{ctx['nickname']}~ 今天也要加油喵！☀️"
