"""
语音识别服务模块。

预留接口，Alpha 版暂不启用（UI 不露出）。
Beta 阶段将集成 faster-whisper GPU 推理。
"""

from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class STTService:
    """语音识别服务（Beta 阶段实现）。"""

    def __init__(self):
        logger.info("STT 服务已注册（暂未启用，Beta 阶段实现）")

    def transcribe(self, audio_path: str) -> Optional[str]:
        """将音频文件转为文字。"""
        # TODO: Beta 阶段实现 faster-whisper GPU 推理
        logger.debug(f"STT 转写被调用（未实现）: {audio_path}")
        return None

    def is_available(self) -> bool:
        return False