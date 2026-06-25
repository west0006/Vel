"""
OCR 文字识别服务模块。

预留接口，Alpha 版暂不启用。
Beta 阶段将集成 PaddleOCR (GPU) + Tesseract 备用。
"""

from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class OCRService:
    """OCR 文字识别服务（Beta 阶段实现）。"""

    def __init__(self):
        logger.info("OCR 服务已注册（暂未启用，Beta 阶段实现）")

    def recognize(self, image_data: bytes) -> Optional[str]:
        """识别图片中的文字。"""
        # TODO: Beta 阶段实现 PaddleOCR GPU 推理
        logger.debug("OCR 识别被调用（未实现）")
        return None

    def is_available(self) -> bool:
        return False