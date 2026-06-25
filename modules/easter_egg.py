"""
隐藏彩蛋模块。

从 config/easter_eggs.yaml 加载触发词，对话中匹配时返回预设回复和动画。
"""

import os
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "easter_eggs.yaml")


class EasterEggEngine:
    """彩蛋匹配引擎。"""

    def __init__(self):
        self._eggs: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            import yaml
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self._eggs = data.get("eggs", [])
            logger.info(f"已加载 {len(self._eggs)} 个彩蛋")
        except Exception as e:
            logger.warning(f"彩蛋加载失败: {e}")
            self._eggs = []

    def match(self, text: str) -> Optional[Dict[str, Any]]:
        """检测文本是否命中彩蛋。

        Args:
            text: 用户输入文本

        Returns:
            命中返回 {"emotion": str, "reply": str}，否则 None
        """
        text_stripped = text.strip().lower()
        for egg in self._eggs:
            trigger = egg.get("trigger", "").lower()
            etype = egg.get("type", "contains")
            if etype == "exact" and text_stripped == trigger:
                return {"emotion": egg.get("emotion", "happy"), "reply": egg["reply"]}
            elif etype == "contains" and trigger in text_stripped:
                return {"emotion": egg.get("emotion", "happy"), "reply": egg["reply"]}
        return None