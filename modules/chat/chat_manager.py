"""
对话管理器模块。

管理用户与桌宠之间的多轮对话，包括上下文窗口维护、记忆召回、
个性化提示注入、情感分析触发等功能。
"""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.event_bus import bus, EVENT_MOOD_DETECTED
from core.service_registry import registry
from modules.chat.prompt_builder import PromptBuilder
from services.llm_service import LLMService
from utils.logger import get_logger

logger = get_logger(__name__)


class ChatManager:
    """对话管理器。

    协调 LLM 服务、记忆服务和提示词构建器，提供完整的对话体验。
    维护10轮滑动窗口上下文，自动召回相关记忆并注入提示词。
    """

    def __init__(self, context_window: int = 10, summary_interval: int = 5):
        self._context_window = context_window
        self._summary_interval = summary_interval

        self._llm: Optional[LLMService] = None
        self._prompt_builder = PromptBuilder()
        self._memory_service = None
        self._extractor = None
        self._profile_manager = None
        self._mood_logger = None

        self._turn_count = 0
        self._on_reply_ready: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """初始化对话管理器，从注册器获取全部依赖。"""
        self._llm = registry.get("llm_service")
        self._memory_service = registry.get("memory_service")
        self._extractor = registry.get("personality_extractor")
        self._profile_manager = registry.get("profile_manager")
        self._mood_logger = registry.get("mood_logger")

        if self._extractor is None:
            logger.info("个性化抽取器未注册，将跳过特质抽取")
        if self._profile_manager is None:
            logger.info("画像管理器未注册，将跳过画像入库")

        logger.info("对话管理器初始化完成")

    def set_on_reply_ready(self, callback: Callable[[str], None]) -> None:
        self._on_reply_ready = callback

    def set_user_name(self, name: str) -> None:
        self._prompt_builder.set_user_name(name)
        if self._llm:
            self._llm.set_user_name(name)

    # ------------------------------------------------------------------
    # 核心对话流程
    # ------------------------------------------------------------------

    def process_message(self, user_input: str) -> str:
        logger.info(f"对话输入: {user_input[:80]}...")

        # 1. Agent 路由：意图分类 → 分流处理
        try:
            router = registry.get("agent_service")
            if router:
                routed = router.handle(user_input)
                if routed:
                    self._save_to_archive("user", user_input)
                    self._save_to_archive("assistant", routed)
                    return routed
        except Exception as e:
            logger.warning(f"Agent路由异常: {e}")

        # 2. 保存用户消息
        self._save_to_archive("user", user_input)

        # 3. 检索相关记忆
        memory_texts = []
        if self._memory_service:
            try:
                memories = self._memory_service.search(user_input, top_k=3, min_score=0.4)
                memory_texts = [m["summary"] for m in memories]
            except Exception as e:
                logger.warning(f"记忆检索失败: {e}")

        # 4. 构建个性化系统提示
        if self._prompt_builder and self._llm:
            system_msg = self._prompt_builder.build_system_message()
            self._llm.set_system_prompt(system_msg["content"])

        # 5. 搜索意图检测
        search_context = ""
        search_svc = registry.get("search_service")
        if search_svc and search_svc.needs_search(user_input):
            try:
                search_result = search_svc.search(user_input)
                if search_result and "暂不可用" not in search_result:
                    search_context = search_svc.format_for_chat(user_input, search_result)
            except Exception as e:
                logger.warning(f"搜索失败: {e}")

        # 6. 执行 LLM 调用
        try:
            if self._llm:
                combined = memory_texts[:]
                if search_context:
                    combined.insert(0, search_context)
                reply = self._llm.generate(user_input, memories=combined)
            else:
                reply = "喵~我还没准备好，请稍后再找我聊天哦"
        except Exception as e:
            logger.exception(f"对话处理异常: {e}")
            reply = "喵...好像出了点问题，让我重新想想~"

        # 7. 保存回复
        self._save_to_archive("assistant", reply)

        # 8. 规则抽取特质并入库
        if self._extractor and self._profile_manager:
            try:
                candidates = self._extractor.extract_by_rules(user_input)
                if candidates:
                    self._profile_manager.batch_upsert_traits(candidates)
            except Exception as e:
                logger.warning(f"特质抽取/入库失败: {e}")

        # 9. 喂入 LLM 摘要缓冲区
        if self._extractor:
            try:
                self._extractor.feed_dialogue(user_input, reply)
            except Exception as e:
                logger.warning(f"摘要缓冲失败: {e}")

        # 10. 轮次管理
        self._turn_count += 1
        if self._turn_count % self._summary_interval == 0:
            self._trigger_summary()

        # 11. 情绪分析
        self._analyze_mood(user_input)

        logger.info(f"对话回复: {reply[:80]}...")
        return reply

    # ------------------------------------------------------------------
    # 存档管理
    # ------------------------------------------------------------------

    def _save_to_archive(self, role: str, content: str) -> None:
        try:
            db = registry.get("database")
            if db is None:
                return
            db.execute(
                "INSERT INTO conversation_archive (role, content, tokens_count) VALUES (?, ?, ?)",
                (role, content, len(content) // 2),
            )
            db.commit()
        except Exception as e:
            logger.warning(f"存档保存失败: {e}")

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            db = registry.get("database")
            if db is None:
                return []
            cursor = db.execute(
                "SELECT msg_id, role, content, timestamp FROM conversation_archive "
                "ORDER BY msg_id DESC LIMIT ?", (limit,)
            )
            keys = [d[0] for d in cursor.description]
            return [dict(zip(keys, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.warning(f"获取历史失败: {e}")
            return []

    # ------------------------------------------------------------------
    # 情绪分析（P2-8 修复：使用 mood_logger 统一词库）
    # ------------------------------------------------------------------

    def _analyze_mood(self, text: str) -> None:
        """分析用户情绪，使用 mood_logger 统一词库。"""
        try:
            if self._mood_logger:
                # 使用 mood_logger 的统一词库和打分逻辑
                label, intensity = self._mood_logger.analyze(text)
            else:
                # 回退：内联简化词库
                label, intensity = self._fallback_mood_analyze(text)

            if label == "neutral" and intensity < 0.4:
                return

            # 存储到数据库
            try:
                db = registry.get("database")
                if db:
                    db.execute(
                        "INSERT INTO mood_snapshot (mood_label, intensity, context_summary) "
                        "VALUES (?, ?, ?)",
                        (label, intensity, text[:100]),
                    )
                    db.commit()
            except Exception as e:
                logger.warning(f"情绪记录失败: {e}")

            bus.publish(EVENT_MOOD_DETECTED, {"label": label, "intensity": intensity})

            if label == "negative" and intensity > 0.6:
                logger.info(f"检测到负面情绪 (强度={intensity:.2f})")

        except Exception as e:
            logger.warning(f"情绪分析失败: {e}")

    @staticmethod
    def _fallback_mood_analyze(text: str) -> tuple:
        """回退情绪分析（mood_logger 不可用时）。"""
        positive = ["开心", "高兴", "喜欢", "棒", "好", "谢谢", "赞", "爱",
                     "快乐", "nice", "great", "good", "哈哈", "嘻嘻"]
        negative = ["烦", "累", "不开心", "生气", "讨厌", "难过", "失望",
                    "烦躁", "焦虑", "压力", "烦死了", "郁闷", "伤心"]
        tl = text.lower()
        pc = sum(1 for w in positive if w in tl)
        nc = sum(1 for w in negative if w in tl)
        if pc > nc:
            return ("positive", min(0.5 + pc * 0.1, 1.0))
        elif nc > pc:
            return ("negative", min(0.5 + nc * 0.1, 1.0))
        return ("neutral", 0.3)

    # ------------------------------------------------------------------
    # 记忆摘要
    # ------------------------------------------------------------------

    def _trigger_summary(self) -> None:
        history = self.get_history(limit=10)
        if not history:
            return
        summary = self._prompt_builder.summarize_for_storage([
            {"role": h["role"], "content": h["content"]} for h in history
        ])
        if self._memory_service:
            self._memory_service.add_memory(summary=summary, category="event", importance=5)

    # ------------------------------------------------------------------
    # 对话管理
    # ------------------------------------------------------------------

    def clear_context(self) -> None:
        if self._llm:
            self._llm.clear_history()
        self._turn_count = 0
        logger.info("对话上下文已清空")

    def get_turn_count(self) -> int:
        return self._turn_count