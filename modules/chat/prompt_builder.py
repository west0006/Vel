"""
提示词构建模块。

负责将用户画像、记忆、对话历史和系统提示拼接为发送给 LLM 的完整消息。
支持个性化注入，Alpha 版使用规则+数据库键值对简化实现。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class PromptBuilder:
    """提示词构建器。

    从 ServiceRegistry 获取用户画像和记忆服务，构建个性化的 LLM 提示词。
    """

    # 默认系统提示模板
    DEFAULT_SYSTEM_PROMPT = (
        "你是一个名叫 Vel 的桌面宠物，性格像一只温柔调皮的猫咪。"
        "你是用户{user_name}的桌面伙伴。请用亲切活泼的口吻交流，"
        "适当使用\"~\"语气词和\"喵\"字。回复简短自然（不超过150字）。"
    )

    def __init__(self):
        self._system_prompt = self.DEFAULT_SYSTEM_PROMPT
        self._user_name = "用户"

    def set_user_name(self, name: str) -> None:
        """设置用户名。"""
        self._user_name = name

    def set_system_prompt(self, prompt: str) -> None:
        """自定义系统提示。"""
        self._system_prompt = prompt

    # ------------------------------------------------------------------
    # 信息收集
    # ------------------------------------------------------------------

    def _get_profile_summary(self) -> str:
        """从 user_profile 获取用户画像摘要。"""
        try:
            db = registry.get("database")
            if db is None:
                return ""
            cursor = db.execute("SELECT key, value FROM user_profile")
            rows = cursor.fetchall()
            if not rows:
                return ""
            parts = []
            for key, value in rows:
                # 敏感字段解密
                from utils.crypto import decrypt
                decoded = decrypt(value)
                parts.append(f"{key}: {decoded}")
            return "\n".join(parts)
        except Exception as e:
            logger.debug(f"获取用户画像失败: {e}")
            return ""

    def _get_active_traits(self) -> Dict[str, List[str]]:
        """获取活跃的用户特质，按 category 分组。"""
        try:
            db = registry.get("database")
            if db is None:
                return {}
            cursor = db.execute(
                "SELECT trait_name, value, "
                "CASE "
                "  WHEN trait_name LIKE 'prefer_%' OR trait_name LIKE 'dislike_%' OR trait_name LIKE 'restriction_%' THEN 'preference' "
                "  WHEN trait_name LIKE 'habit_%' THEN 'habit' "
                "  WHEN trait_name LIKE 'goal_%' OR trait_name LIKE 'identity_%' THEN 'goal' "
                "  ELSE 'personality' "
                "END as category "
                "FROM user_traits "
                "WHERE confidence >= 0.6 AND last_active >= date('now', '-60 days') "
                "ORDER BY confidence DESC LIMIT 20"
            )
            grouped: Dict[str, List[str]] = {}
            for row in cursor.fetchall():
                cat = row[2]
                if cat not in grouped:
                    grouped[cat] = []
                grouped[cat].append(row[1])
            return grouped
        except Exception as e:
            logger.debug(f"获取用户特质失败: {e}")
            return {}

    def _get_time_context(self) -> str:
        """获取时间上下文。"""
        from datetime import datetime
        now = datetime.now()
        hour = now.hour
        if 5 <= hour < 9:
            period = "早晨"
        elif 9 <= hour < 12:
            period = "上午"
        elif 12 <= hour < 14:
            period = "中午"
        elif 14 <= hour < 18:
            period = "下午"
        elif 18 <= hour < 22:
            period = "晚上"
        else:
            period = "深夜"

        return f"现在是{period} ({now.strftime('%H:%M')})"

    # ------------------------------------------------------------------
    # 提示词构建
    # ------------------------------------------------------------------

    def build_system_message(self, extra_context: Optional[str] = None) -> Dict[str, str]:
        parts = [self._system_prompt.replace("{user_name}", self._user_name)]

        profile = self._get_profile_summary()
        if profile:
            parts.append(f"\n【用户画像】\n{profile}")

        traits = self._get_active_traits()
        if traits:
            labels = {
                "personality": "性格", "preference": "偏好",
                "habit": "习惯", "goal": "最近在",
            }
            lines = [f"【你了解的 {self._user_name}】"]
            for cat, cat_label in labels.items():
                if cat in traits:
                    lines.append(f"{cat_label}：" + "、".join(traits[cat]))
            parts.append("\n".join(lines))

        if extra_context:
            parts.append(f"\n【附加上下文】{extra_context}")

        # ── 时间参考 ──
        parts.append("【时间参考】" + datetime.now().strftime("%Y年%m月%d日 %H:%M:%S") +
                         "，回答\"现在几点\"等时间问题时请严格使用这个时间。")

        # ── 工具协议 ──
        parts.append("""【重要：工具调用格式】

        需要操作时，你必须只用一行标签回复，标签内外不要有任何额外文字。格式如下：

        <tool_call>{"tool":"工具名","params":{...}}</tool_call>

        可用工具：
        - create_reminder：创建日程提醒
          参数：{"tool":"create_reminder","params":{"title":"事件","time":"自然语言时间"}}
        - create_memo：创建备忘录
          参数：{"tool":"create_memo","params":{"content":"内容","time":"提醒时间(可选)"}}
        - query_schedule：查询当日日程
          参数：{"tool":"query_schedule","params":{"date":"日期(可选)"}}
        - get_diary：查看日记
          参数：{"tool":"get_diary","params":{"date":"日期(可选)"}}
        - search_web：联网搜索（结果会回传供你总结）
          参数：{"tool":"search_web","params":{"query":"搜索关键词"}}

        规则：
        - 普通聊天直接回复，不需要工具
        - 需要操作时使用上述格式，严格按要求
        - search_web 的结果会回传给你，请基于它生成最终回复
        - 回复简短自然，不超过150字，猫咪口吻""")

        return {"role": "system", "content": "\n".join(parts)}

    def build_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        """将检索到的记忆转换为提示上下文。"""
        if not memories:
            return ""
        lines = ["以下是你对用户的记忆（请自然地融入回复）:"]
        for mem in memories[:5]:
            lines.append(f"- ({mem.get('category', '记忆')}) {mem.get('summary', '')}")
        return "\n".join(lines)

    def summarize_for_storage(self, history: List[Dict[str, str]]) -> str:
        """为长期记忆生成对话摘要（由 LLM 完成或规则截取）。"""
        # 简化版：取最后几条对话的关键内容
        important_lines = []
        for msg in history[-6:]:
            role = "用户" if msg["role"] == "user" else "Vel"
            content = msg["content"]
            if len(content) > 100:
                content = content[:100] + "..."
            important_lines.append(f"{role}: {content}")
        return "\n".join(important_lines)