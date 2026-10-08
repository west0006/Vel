"""
对话管理器模块。统一 LLM 中枢 + 工具调用。
"""

import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.event_bus import bus, EVENT_MOOD_DETECTED
from core.service_registry import registry
from modules.chat.prompt_builder import PromptBuilder
from services.llm_service import LLMService
from utils.logger import get_logger

logger = get_logger(__name__)

TOOL_TAG_RE = re.compile(r'<tool_call>\s*(\{.+?\})\s*</tool_call>', re.DOTALL)
FALLBACK_JSON_RE = re.compile(r'\{\s*"tool"\s*:\s*"(create_reminder|create_memo|query_schedule|get_diary|search_web)"', re.DOTALL)
MAX_TOOL_CALLS = 2


class ChatManager:
    """对话管理器。统一 LLM 中枢。"""

    def __init__(self, summary_interval: int = 5):
        self._llm: Optional[LLMService] = None
        self._prompt_builder = PromptBuilder()
        self._memory_service = None
        self._extractor = None
        self._profile_manager = None
        self._mood_logger = None

        self._turn_count = 0
        self._summary_interval = summary_interval
        self._history_cache: List[Dict[str, Any]] = []  # 内存 LRU，最多 100 条


    # ────────────── 初始化 ──────────────

    def initialize(self) -> None:
        self._llm = registry.get("llm_service")
        self._memory_service = registry.get("memory_service")
        self._extractor = registry.get("personality_extractor")
        self._profile_manager = registry.get("profile_manager")
        self._mood_logger = registry.get("mood_logger")
        logger.info("对话管理器初始化完成")

    def set_user_name(self, name: str) -> None:
        self._prompt_builder.set_user_name(name)
        if self._llm:
            self._llm.set_user_name(name)

    # ────────────── 核心管线 ──────────────

    def process_message(self, user_input: str) -> str:
        logger.info(f"对话输入: {user_input[:80]}...")

        # 1. 彩蛋预检
        ee = registry.get("easter_egg_engine")
        if ee:
            egg = ee.match(user_input)
            if egg:
                self._save_to_archive("user", user_input)
                self._save_to_archive("assistant", egg["reply"])
                return egg["reply"]

        # 2. 存档用户消息
        self._save_to_archive("user", user_input)

        # 3. 记忆召回
        memory_texts = self._retrieve_memories(user_input)

        # 4. 构建系统提示词
        if self._prompt_builder and self._llm:
            system_msg = self._prompt_builder.build_system_message()
            self._llm.set_system_prompt(system_msg["content"])

        # 5. 回退：无 LLM
        if not self._llm:
            reply = "喵~我还没准备好，请稍后再找我聊天哦"
            self._save_to_archive("assistant", reply)
            return reply

        # 6. LLM 中枢（最多 2 轮工具调用）
        try:
            reply, skip_archive = self._llm_loop(user_input, memory_texts)
            if not skip_archive:
                self._save_to_archive("assistant", reply)
        except Exception as e:
            logger.exception(f"对话处理异常: {e}")
            reply = "喵...好像出了点问题，让我重新想想~"
            self._save_to_archive("assistant", reply)

        # 7. 后处理
        self._post_process(user_input, reply)
        logger.info(f"对话回复: {reply[:80]}...")
        return reply

    # ────────────── LLM 中枢 ──────────────

    _stream_cb: Optional[Callable[[str], None]] = None

    def set_stream_callback(self, cb: Callable[[str], None]) -> None:
        self._stream_cb = cb

    def _llm_loop(self, user_input: str, memory_texts: List[str]) -> Tuple[str, bool]:
        """LLM 循环：流式生成 → 检测 tool_call → 执行。

        Returns: (最终回复, skip_archive)。
        """
        combined = list(memory_texts)
        first_input = user_input
        tool_count = 0

        while tool_count <= MAX_TOOL_CALLS:
            reply = self._stream_generate(first_input, combined)
            first_input = ""

            # 检测 tool_call
            m = TOOL_TAG_RE.search(reply)
            payload_str = None

            if m:
                payload_str = m.group(1)
            else:
                fm = FALLBACK_JSON_RE.search(reply)
                if fm:
                    start = fm.start()
                    depth, end = 0, start
                    for i in range(start, len(reply)):
                        if reply[i] == '{': depth += 1
                        elif reply[i] == '}':
                            depth -= 1
                            if depth == 0: end = i + 1; break
                    payload_str = reply[start:end]

            if not payload_str:
                return reply, False

            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                logger.warning(f"tool_call JSON 解析失败: {payload_str[:100]}")
                return reply, False

            tool_name = payload.get("tool", "")
            tool_params = payload.get("params", {})
            executor = registry.get("tool_executor")
            if executor is None:
                return reply, False

            tool_result, is_terminal = executor.execute(tool_name, tool_params)
            logger.info(f"工具调用: {tool_name} → {'终结' if is_terminal else '中间'}")

            if is_terminal:
                return tool_result, False

            combined.insert(0, f"[工具结果：{tool_name}]\n{tool_result}")
            tool_count += 1

        return reply, False

    def _stream_generate(self, user_input: str, memories: List[str]) -> str:
        """流式生成，边输出边收集全文。"""
        parts = []
        try:
            for chunk in self._llm.generate_stream(user_input, memories=memories):
                parts.append(chunk)
                if self._stream_cb:
                    self._stream_cb(chunk)
        except Exception as e:
            logger.warning(f"流式生成异常: {e}")
            # 降级：非流式
            return self._llm.generate(user_input, memories=memories)
        return "".join(parts)

    # ────────────── 记忆 ──────────────

    def _retrieve_memories(self, user_input: str) -> List[str]:
        if not self._memory_service:
            return []
        try:
            memories = self._memory_service.search(user_input, top_k=3, min_score=0.4)
            texts = [m["summary"] for m in memories]
            if texts:
                bus.publish("CONTEXT_HINT", {"text": f"想起了 {len(texts)} 段相关记忆~"})
            return texts
        except Exception as e:
            logger.warning(f"记忆检索失败: {e}")
            return []

    # ────────────── 后处理 ──────────────

    def _post_process(self, user_input: str, reply: str) -> None:
        # 特质抽取
        if self._extractor and self._profile_manager:
            try:
                candidates = self._extractor.extract_by_rules(user_input)
                if candidates:
                    self._profile_manager.batch_upsert_traits(candidates)
            except Exception as e:
                logger.warning(f"特质抽取失败: {e}")

        # 摘要缓冲
        if self._extractor:
            try:
                self._extractor.feed_dialogue(user_input, reply)
            except Exception as e:
                logger.warning(f"摘要缓冲失败: {e}")

        # 情绪分析
        self._analyze_mood(user_input)

        # 轮次管理
        self._turn_count += 1
        if self._turn_count % self._summary_interval == 0:
            self._trigger_summary()

    # ────────────── 存档 & 历史 ──────────────

    def _save_to_archive(self, role: str, content: str) -> None:
        try:
            db = registry.get("database")
            if db is None:
                return
            db.execute(
                "INSERT INTO conversation_archive (role, content, tokens_count) "
                "VALUES (?, ?, ?)",
                (role, content, len(content) // 2),
            )
            db.commit()

            # 同步写入内存缓存
            self._history_cache.append({
                "role": role, "content": content,
                "timestamp": datetime.now().isoformat(),
            })
            if len(self._history_cache) > 100:
                self._history_cache = self._history_cache[-100:]
        except Exception as e:
            logger.warning(f"存档失败: {e}")

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self._history_cache:
            return self._history_cache[-limit:]
        try:
            db = registry.get("database")
            if db is None:
                return []
            cursor = db.execute(
                "SELECT msg_id, role, content, timestamp FROM conversation_archive "
                "ORDER BY msg_id DESC LIMIT ?", (limit,)
            )
            return [dict(zip([d[0] for d in cursor.description], row))
                    for row in cursor.fetchall()]
        except Exception as e:
            logger.warning(f"获取历史失败: {e}")
            return []

    # ────────────── 情绪 ──────────────

    def _analyze_mood(self, text: str) -> None:
        try:
            if self._mood_logger:
                label, intensity = self._mood_logger.analyze(text)
            else:
                label, intensity = self._fallback_mood_analyze(text)

            if label == "neutral" and intensity < 0.4:
                return

            db = registry.get("database")
            if db:
                db.execute(
                    "INSERT INTO mood_snapshot (mood_label, intensity, context_summary) "
                    "VALUES (?, ?, ?)",
                    (label, intensity, text[:100]),
                )
                db.commit()

            bus.publish(EVENT_MOOD_DETECTED, {"label": label, "intensity": intensity})
        except Exception as e:
            logger.warning(f"情绪分析失败: {e}")

    @staticmethod
    def _fallback_mood_analyze(text: str) -> tuple:
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

    # ────────────── 摘要 ──────────────

    def _trigger_summary(self) -> None:
        history = self.get_history(limit=10)
        if not history:
            return
        messages = [{"role": h["role"], "content": h["content"]} for h in history]

        # 优先 LLM 提取关键记忆，失败回退模板截断
        summary = self._prompt_builder.summarize_for_storage(messages)
        if self._llm and not getattr(self._llm, '_is_degraded', True):
            try:
                dialogue_text = "\n".join(
                    f"{'用户' if m['role']=='user' else 'Vel'}: {m['content'][:100]}"
                    for m in messages[-6:]
                )
                llm_summary = self._llm._call_ollama([
                    {"role": "system", "content": "用一句简短的话总结这段对话的核心内容。"},
                    {"role": "user", "content": dialogue_text},
                ])
                if llm_summary and len(llm_summary) > 5:
                    summary = llm_summary.strip()
            except Exception:
                pass

        if self._memory_service:
            self._memory_service.add_memory(
                summary=summary, category="event", importance=5,
            )

    # ────────────── 对话管理 ──────────────

    def clear_context(self) -> None:
        if self._llm:
            self._llm.clear_history()
        self._turn_count = 0
        logger.info("对话上下文已清空")

    def get_turn_count(self) -> int:
        return self._turn_count