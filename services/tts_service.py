"""
语音合成服务模块。

预留接口，Alpha 版暂不启用。
Beta 阶段将集成 Edge-TTS 或 Coqui TTS 本地推理。
"""

from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class TTSService:
    """语音合成服务（Beta 阶段实现）。"""

    def __init__(self):
        logger.info("TTS 服务已注册（暂未启用，Beta 阶段实现）")

    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        """将文字合成为语音。"""
        # TODO: Beta 阶段实现本地 TTS 推断
        logger.debug(f"TTS 合成被调用（未实现）: {text[:30]}...")
        return None

    def is_available(self) -> bool:
        return False