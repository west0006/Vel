"""
Ollama LLM 服务封装模块。

负责与本地 Ollama 进程通信，提供对话生成、上下文管理及降级回复功能。
Alpha 版本使用 Qwen2.5-7B-Instruct 量化模型。
"""

import json
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.event_bus import bus, EVENT_SYSTEM_STATUS
from utils.logger import get_logger

logger = get_logger(__name__)


class LLMService:
    """Ollama LLM 服务封装。

    通过 Ollama HTTP API (默认 localhost:11434) 与本地模型通信。
    支持上下文窗口管理，失败时降级为预设回复。
    """

    def __init__(
        self,
        model: str = "gemma4:latest",
        host: str = "127.0.0.1",
        port: int = 11434,
        timeout: int = 30,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        context_window: int = 10,
        fallback_replies: Optional[List[str]] = None,
    ):
        self.model = model
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.context_window = context_window
        self._user_name = "用户"

        self._fallback_replies = fallback_replies or [
            "喵...我好像有点卡住了，稍等一下哦~",
            "啊哦，我的小脑袋转不动了，让我重启一下思维...",
            "现在有点迷糊，你要不要换个话题？",
        ]
        self._fallback_index = 0

        self._history: List[Dict[str, str]] = []
        self._system_prompt = (
            "你是一个名叫 Vel 的桌面宠物，性格像一只温柔调皮的猫咪。"
            "你是用户（{user_name}）的桌面伙伴，职责是陪伴、提醒和帮助用户。"
            "请用亲切、活泼的口吻与用户交流，适当使用\"~\"语气词和\"喵\"字。"
            "回复要简短自然（不超过150字），尽量口语化。"
        )

        self._consecutive_failures = 0
        self._max_failures_before_degrade = 3
        self._is_degraded = False
        # 降级后的恢复探测：每 _degrade_probe_interval 次生成尝试一次真实调用。
        # 修复缺陷：此前 `if self._is_degraded: return fallback` 直接返回，
        # 导致一旦降级就永不恢复（Ollama 重启 / 模型重载后无法自愈，除非重启程序）。
        self._degrade_probe_counter = 0
        self._degrade_probe_interval = 5

    # ------------------------------------------------------------------
    # 系统提示管理
    # ------------------------------------------------------------------

    def set_system_prompt(self, prompt: str) -> None:
        """设置系统提示词，覆盖默认值。"""
        self._system_prompt = prompt

    def set_user_name(self, name: str) -> None:
        """更新用户名称。"""
        self._user_name = name

    def _build_system_message(self, extra_memories: Optional[List[str]] = None) -> List[Dict[str, str]]:
        """构建系统消息列表。

        Args:
            extra_memories: 当前对话注入的临时记忆文本

        Returns:
            消息列表 [system_msg, (memory_msg), ...]
        """
        messages = []
        name = self._user_name or "用户"
        content = self._system_prompt.replace("{user_name}", name)
        messages.append({"role": "system", "content": content})

        if extra_memories:
            memory_text = "\n".join(f"- {m}" for m in extra_memories[:5])
            messages.append({
                "role": "system",
                "content": f"以下是你对用户的相关记忆，请自然地融入回复:\n{memory_text}",
            })

        return messages

    # ------------------------------------------------------------------
    # 对话历史管理
    # ------------------------------------------------------------------

    def add_to_history(self, role: str, content: str) -> None:
        """添加一条对话到历史记录。"""
        self._history.append({"role": role, "content": content})
        max_messages = self.context_window * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]

    def clear_history(self) -> None:
        """清空对话历史。"""
        self._history.clear()

    def get_history(self) -> List[Dict[str, str]]:
        """获取当前对话历史。"""
        return self._history.copy()

    # ------------------------------------------------------------------
    # LLM 调用
    # ------------------------------------------------------------------

    def _build_messages(self, memories: Optional[List[str]] = None) -> List[Dict[str, str]]:
        """构建发送给 Ollama 的完整消息列表。

        记忆作为额外的 system 消息注入，不影响持久化的 _history。
        """
        messages = self._build_system_message(memories)
        messages.extend(self._history)
        return messages

    def generate(self, user_input: str, memories: Optional[List[str]] = None) -> str:
        """生成对话回复。

        Args:
            user_input: 用户输入文本
            memories: 可选，召回的相关记忆文本列表

        Returns:
            模型回复文本
        """
        if self._is_degraded:
            self._degrade_probe_counter += 1
            if self._degrade_probe_counter < self._degrade_probe_interval:
                reply = self._get_fallback_reply()
                self.add_to_history("user", user_input)
                self.add_to_history("assistant", reply)
                return reply
            # 达到探测间隔：本次走真实调用，成功即自动退出降级模式
            self._degrade_probe_counter = 0
            logger.info("降级模式探测恢复：尝试真实调用")

        self.add_to_history("user", user_input)
        messages = self._build_messages(memories)

        try:
            reply = self._call_ollama(messages)
            self._consecutive_failures = 0
            if self._is_degraded:
                logger.info("LLM 已恢复，退出降级模式")
            self._is_degraded = False
            self._degrade_probe_counter = 0
            self.add_to_history("assistant", reply)
            return reply

        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"LLM 调用失败 (第{self._consecutive_failures}次): {e}")

            if self._consecutive_failures >= self._max_failures_before_degrade:
                self._enter_degrade_mode()

            reply = self._get_fallback_reply()
            self.add_to_history("assistant", reply)
            return reply

    def _call_ollama(self, messages: List[Dict[str, str]]) -> str:
        """调用 Ollama API 生成回复。

        注意：此方法不修改 self._history，由调用者管理。
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
            "stream": False,
        }

        start = time.time()
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        elapsed = time.time() - start

        data = resp.json()
        reply = data.get("message", {}).get("content", "").strip()
        logger.info(f"LLM 回复生成完毕 ({elapsed:.1f}s, {len(reply)} 字)")
        return reply

    def _enter_degrade_mode(self) -> None:
        """进入降级模式，使用预设回复。"""
        self._is_degraded = True
        logger.warning("LLM 连续失败超过阈值，进入降级模式")
        bus.publish(EVENT_SYSTEM_STATUS, {
            "type": "llm_degrade",
            "reason": "连续3次调用失败",
        })

    def _get_fallback_reply(self) -> str:
        """获取下一条预设降级回复（轮询）。"""
        reply = self._fallback_replies[self._fallback_index % len(self._fallback_replies)]
        self._fallback_index += 1
        return reply

    # ------------------------------------------------------------------
    # 模型管理
    # ------------------------------------------------------------------

    def check_connection(self) -> Tuple[bool, str]:
        """检查 Ollama 服务是否可用。

        Returns:
            (是否可用, 消息)
        """
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                for m in models:
                    m_name = m.get("name", "")
                    # 精确匹配或前缀:tag 匹配
                    if m_name == self.model or m_name.startswith(self.model.rsplit(":", 1)[0]):
                        return True, f"模型 {self.model} 已就绪"
                return True, f"Ollama 运行中，但模型 {self.model} 未找到"
            return False, f"Ollama 返回状态码 {resp.status_code}"
        except requests.ConnectionError:
            return False, f"无法连接到 Ollama ({self.base_url})"
        except Exception as e:
            return False, str(e)

    def recover_from_degrade(self) -> bool:
        """尝试从降级模式恢复。"""
        if not self._is_degraded:
            return True

        ok, msg = self.check_connection()
        if ok:
            self._consecutive_failures = 0
            self._is_degraded = False
            logger.info("LLM 已从降级模式恢复")
            bus.publish(EVENT_SYSTEM_STATUS, {"type": "llm_recovered"})
            return True
        logger.warning(f"LLM 恢复失败: {msg}")
        return False

    def generate_stream(self, user_input: str) -> Any:
        """流式生成回复（供未来使用）。"""
        self.add_to_history("user", user_input)
        messages = self._build_messages()

        payload = {
            "model": self.model,
            "messages": messages,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
            "stream": True,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=self.timeout,
            )
            full_reply = []
            for line in resp.iter_lines(decode_unicode=True):
                if line:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    full_reply.append(content)
                    yield content

            self.add_to_history("assistant", "".join(full_reply))
            self._consecutive_failures = 0

        except Exception as e:
            logger.error(f"流式生成失败: {e}")
            yield self._get_fallback_reply()