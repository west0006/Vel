"""
信息抽取管道模块。

通过三级流水线从对话中提取用户偏好、习惯和重要事件：
1. 规则匹配层：识别明确偏好陈述
2. 情感标记层：检测高强度情绪表达
3. LLM 摘要层：批量提炼候选特质

Alpha 版简化实现：规则 + LLM 两阶段抽取。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from core.service_registry import registry
from utils.crypto import encrypt
from utils.logger import get_logger

logger = get_logger(__name__)


class PersonalityExtractor:
    """个性化信息抽取管道。

    从对话中抽取用户偏好、习惯、事件，生成候选特质和情节记忆。
    """

    # 明确偏好陈述模式
    PREFERENCE_PATTERNS = [
        ("喜欢", "prefer"),
        ("爱", "prefer"),
        ("讨厌", "dislike"),
        ("不喜欢", "dislike"),
        ("不吃", "restriction"),
        ("过敏", "restriction"),
        ("习惯", "habit"),
        ("经常", "habit"),
        ("每次", "habit"),
        ("我是", "identity"),
        ("我在", "status"),
        ("我的", "attribute"),
    ]

    # 情感强度阈值
    EMOTION_INTENSITY_THRESHOLD = 0.7

    # 积累多少轮对话后触发 LLM 摘要
    SUMMARY_BATCH_SIZE = 5

    def __init__(self):
        self._dialogue_buffer: List[Dict[str, str]] = []
        self._batch_count = 0

    # ------------------------------------------------------------------
    # 第1层：规则匹配
    # ------------------------------------------------------------------

    def extract_by_rules(self, text: str) -> List[Dict[str, Any]]:
        """从单条消息中通过规则提取偏好候选。

        Args:
            text: 用户消息文本

        Returns:
            候选特质列表 [{trait_name, value, evidence, source, confidence}, ...]
        """
        candidates = []

        for keyword, category in self.PREFERENCE_PATTERNS:
            if keyword not in text:
                continue

            # 尝试提取偏好对象
            idx = text.index(keyword)
            # 取关键词前后的词
            before = text[max(0, idx - 10):idx].strip()
            after = text[idx + len(keyword):idx + len(keyword) + 30].strip()

            value = after.split("，")[0].split("。")[0].split("！")[0].strip()
            if not value:
                continue

            trait_name = f"{category}_{value[:10]}"
            confidence = 0.85 if category in ("prefer", "dislike", "restriction") else 0.7

            candidates.append({
                "trait_name": trait_name,
                "value": value,
                "evidence": text[:100],
                "source": "auto",
                "confidence": confidence,
                "category": category,
            })

        return candidates

    # ------------------------------------------------------------------
    # 第2层：情感标记（在 mood_logger 中完成，此处仅记录）
    # ------------------------------------------------------------------

    def check_emotion_for_memory(self, text: str, intensity: float) -> bool:
        """判断高强度情绪消息是否应标记为潜在记忆。

        Args:
            text: 用户消息
            intensity: 情绪强度 0~1

        Returns:
            是否应标记
        """
        return intensity > self.EMOTION_INTENSITY_THRESHOLD

    # ------------------------------------------------------------------
    # 第3层：LLM 摘要
    # ------------------------------------------------------------------

    def feed_dialogue(self, user_msg: str, assistant_msg: str) -> None:
        """喂入一轮对话到缓冲区，达到阈值时触发 LLM 摘要。

        Args:
            user_msg: 用户消息
            assistant_msg: 助手回复
        """
        self._dialogue_buffer.append({"role": "user", "content": user_msg})
        self._dialogue_buffer.append({"role": "assistant", "content": assistant_msg})
        self._batch_count += 1

        if self._batch_count >= self.SUMMARY_BATCH_SIZE:
            self._trigger_llm_summary()

    def _trigger_llm_summary(self) -> Optional[List[Dict[str, Any]]]:
        """调用 LLM 对缓冲区对话进行摘要和特质抽取。"""
        if len(self._dialogue_buffer) < 10:
            return None

        llm = registry.get("llm_service")
        if llm is None:
            return None

        # 构建提示词
        dialogue_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else 'Vel'}: {m['content'][:200]}"
            for m in self._dialogue_buffer[-20:]  # 取最近 20 条
        )

        prompt = (
            "从以下对话中深度分析用户，提取新发现的信息。\n"
            "输出 JSON 对象，格式：\n"
            "{\n"
            "  \"traits\": [\n"
            "    {\"trait_name\": \"名称\", \"value\": \"值\",\n"
            "     \"category\": \"preference/habit/personality/goal/event\",\n"
            "     \"evidence\": \"原文引用(≤20字)\"}\n"
            "  ],\n"
            "  \"summary\": \"10字以内概括这段对话中用户的情绪或状态\"\n"
            "}\n\n"
            "category 说明：\n"
            "  preference = 喜恶(\"喜欢辣\"/\"不喜欢早起\")\n"
            "  habit = 习惯(\"每天跑步\"/\"熬夜\")\n"
            "  personality = 性格(\"细心\"/\"拖延\")\n"
            "  goal = 目标(\"备考\"/\"减肥\")\n"
            "  event = 事件(\"下周出差\")\n\n"
            "注意：只提取对话中明确体现的新信息，不推测。没有新发现时 traits 为空数组。\n\n"
            f"对话:\n{dialogue_text}\n\n"
            "只输出 JSON 对象，不要其他内容："
        )

        try:
            if hasattr(llm, '_call_ollama'):
                reply = llm._call_ollama([
                    {"role": "system", "content": "你是信息抽取助手，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ])
            else:
                reply = llm.generate(prompt)

            # 提取 JSON
            start = reply.find('{')
            end = reply.rfind('}')
            if start >= 0 and end > start:
                reply = reply[start:end + 1]

            data = json.loads(reply)
            items = data.get("traits", [])
            user_summary = data.get("summary", "")
            if user_summary:
                items.append({
                    "trait_name": "latest_mood_summary",
                    "value": user_summary,
                    "category": "personality",
                    "evidence": user_summary,
                    "confidence": 0.5,
                    "source": "auto",
                })
            logger.info(f"LLM 摘要抽取: {len(items)} 条候选特质")

            # 清空缓冲区
            self._dialogue_buffer = self._dialogue_buffer[-10:]  # 保留最近10条
            self._batch_count = 0

            return items

        except json.JSONDecodeError as e:
            logger.warning(f"LLM 摘要 JSON 错误: {e}")
        except Exception as e:
            logger.error(f"LLM 摘要失败: {e}")

        # 出错时清一半
        self._dialogue_buffer = self._dialogue_buffer[-20:]
        self._batch_count = 10
        return None

    def force_summarize(self) -> Optional[List[Dict[str, Any]]]:
        """强制触发摘要（如退出时保存）。"""
        return self._trigger_llm_summary()