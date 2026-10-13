"""
智能问候模块。

每日首次唤醒时生成个性化问候。

**本模块的 UI 阻塞已消除**（2026-10-08）：
`check_and_greet()` 会被 UI 回调链直接调用（`main.py`：点击桌宠 → `_show_bubble_safe`
→ `check_and_greet`），而它此前含两个同步网络调用 —— 天气 `requests.get(timeout=3)`
与问候语模型推理 `requests.post(timeout=10)`，网络慢或模型冷启动时**会卡住界面数秒**，
违反 `AGENTS.md` §4.3「UI 线程单次阻塞不得超过 200ms」。现改为：

- **天气**：只读 `utils.remote_text` 的后台缓存（未命中则问候语不含天气）；
- **问候语**：缓存命中即用；未命中返回模板，并触发**后台线程**生成（下次/预热时可用）；
- `prewarm()` 供启动时后台预热（不阻塞启动）。
"""

import threading
from datetime import date, datetime
from typing import Dict, Optional

from core.service_registry import registry
from utils.logger import get_logger
from utils.remote_text import remote_text

logger = get_logger(__name__)

#: 天气数据源与缓存键（wttr.in 免费无需 Key）
WEATHER_URL = "https://wttr.in/?format=%C+%t"
WEATHER_CACHE_KEY = "wttr_weather"
#: 问候语生成所用的轻量模型与超时（仅在后台线程中使用）
GREETING_MODEL = "qwen2.5:3b"
GREETING_TIMEOUT = 10


class GreetingService:
    """每日问候服务。"""

    def __init__(self) -> None:
        self._greeting_cache: Dict[str, str] = {}
        self._generating: set = set()
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def check_and_greet(self) -> Optional[str]:
        """检查是否应该问候，是则返回问候语（**永不阻塞**）。

        Returns:
            问候语；今日已问候或无需问候时返回 ``None``。
        """
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
            logger.exception("check_and_greet 读取上次问候日期失败")

        context = self._collect_context()
        greeting = self._generate(context)

        # 记录问候日期
        try:
            db = registry.get("database")
            if db:
                db.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) "
                    "VALUES ('last_greeting_date', ?)",
                    (today,),
                )
                db.commit()
        except Exception:
            logger.exception("check_and_greet 记录问候日期失败")

        logger.info(f"问候已生成: {greeting[:40]}...")
        return greeting

    def prewarm(self) -> None:
        """启动时后台预生成当天问候语（不阻塞启动）。

        由 `main.py` 在服务注册后调用；无 LLM 服务时直接跳过。
        """
        if registry.get("llm_service") is None:
            return
        try:
            context = self._collect_context()
        except Exception:
            logger.exception("prewarm 收集上下文失败")
            return
        self._spawn_generation(self._cache_key(context), context)

    # ------------------------------------------------------------------
    # 上下文收集
    # ------------------------------------------------------------------

    def _collect_context(self) -> dict:
        ctx = {"period": self._get_period(), "weather": "", "mood": "", "nickname": "用户"}

        # 昵称
        try:
            pm = registry.get("profile_manager")
            if pm:
                nick = pm.get_profile("nickname", "")
                if nick:
                    ctx["nickname"] = nick
        except Exception:
            logger.exception("_collect_context 读取昵称失败")

        # 天气：只读后台缓存（未命中时返回 None 并触发后台刷新），此处永不阻塞
        cached_weather = remote_text.get(WEATHER_CACHE_KEY, WEATHER_URL)
        if cached_weather:
            ctx["weather"] = cached_weather  # 如 "☀️ +22°C"

        # 最近情绪
        try:
            db = registry.get("database")
            if db:
                row = db.execute(
                    "SELECT mood_label FROM mood_snapshot ORDER BY timestamp DESC LIMIT 1"
                ).fetchone()
                if row:
                    ctx["mood"] = {"positive": "开心", "neutral": "平静",
                                   "negative": "有点累"}.get(row[0], "")
        except Exception:
            logger.exception("_collect_context 读取情绪失败")

        return ctx

    @staticmethod
    def _get_period() -> str:
        hour = datetime.now().hour
        if 5 <= hour < 9:
            return "早上"
        if 9 <= hour < 12:
            return "上午"
        if 12 <= hour < 14:
            return "中午"
        if 14 <= hour < 18:
            return "下午"
        if 18 <= hour < 22:
            return "晚上"
        return "晚上"

    # ------------------------------------------------------------------
    # 问候语生成（缓存 + 后台）
    # ------------------------------------------------------------------

    def _generate(self, ctx: dict) -> str:
        """生成问候语（**永不阻塞 UI**）。

        命中缓存直接返回；未命中返回模板，并触发后台生成 —— 模型推理
        （timeout 最长 10s）绝不在 UI 线程执行。
        """
        template = self._template(ctx)
        if registry.get("llm_service") is None:
            return template

        key = self._cache_key(ctx)
        with self._cache_lock:
            cached = self._greeting_cache.get(key)
        if cached:
            return cached

        self._spawn_generation(key, ctx)
        return template

    @staticmethod
    def _template(ctx: dict) -> str:
        """模板问候（无模型 / 缓存未就绪时的降级）。"""
        return f"{ctx['period']}好呀，{ctx['nickname']}~ 今天也要加油喵！☀️"

    @staticmethod
    def _cache_key(ctx: dict) -> str:
        """问候语缓存键：当天 + 时段。"""
        return f"{date.today().isoformat()}:{ctx.get('period', '')}"

    def _build_prompt(self, ctx: dict) -> str:
        prompt = (
            f"生成一句{ctx['period']}问候语，不超过50字，语气温柔猫咪口吻。"
            f"昵称: {ctx['nickname']}"
        )
        if ctx.get("weather"):
            prompt += f" 天气: {ctx['weather']}"
        if ctx.get("mood"):
            prompt += f" 昨日心情: {ctx['mood']}"
        return prompt

    def _spawn_generation(self, key: str, ctx: dict) -> bool:
        """在后台线程生成问候语（同一 key 去重）。

        Returns:
            是否真正启动了生成线程。
        """
        with self._cache_lock:
            if key in self._generating:
                return False
            self._generating.add(key)
        threading.Thread(
            target=self._generate_in_background, args=(key, ctx),
            name="greeting-generate", daemon=True,
        ).start()
        return True

    def _generate_in_background(self, key: str, ctx: dict) -> None:
        """后台线程体：生成并写入缓存。"""
        try:
            text = self._llm_generate(ctx)
            if text:
                with self._cache_lock:
                    self._greeting_cache[key] = text
                logger.debug("问候语已后台生成: %s", key)
        except Exception:
            logger.exception("后台生成问候语失败")
        finally:
            with self._cache_lock:
                self._generating.discard(key)

    def _llm_generate(self, ctx: dict) -> Optional[str]:
        """调用本地 Ollama 生成问候语。

        ⚠️ **只允许在后台线程调用**（timeout 最长 10s）。
        """
        try:
            import requests

            resp = requests.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": GREETING_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是猫咪助手，回复50字以内。"},
                        {"role": "user", "content": self._build_prompt(ctx)},
                    ],
                    "options": {"temperature": 0.7, "num_predict": 60},
                    "stream": False,
                },
                timeout=GREETING_TIMEOUT,
            )
            text = resp.json().get("message", {}).get("content", "").strip()
            return text or None
        except Exception:
            logger.warning("问候语模型生成失败，将使用模板")
            return None
