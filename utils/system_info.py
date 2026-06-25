"""
系统信息检测工具模块。

提供 GPU、内存、操作系统等硬件信息查询功能。
"""

import platform
from typing import Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


class SystemInfo:
    """系统信息检测。"""

    @staticmethod
    def get_os_info() -> str:
        """获取操作系统信息。"""
        return f"{platform.system()} {platform.release()} ({platform.version()})"

    @staticmethod
    def is_windows() -> bool:
        """判断当前是否为 Windows 系统。"""
        return platform.system() == "Windows"

    @staticmethod
    def is_python_3_11() -> bool:
        """检查 Python 版本是否为 3.11.x。"""
        v = platform.python_version_tuple()
        return v[0] == "3" and v[1] == "11"

    @staticmethod
    def get_python_version() -> str:
        """获取 Python 版本字符串。"""
        return platform.python_version()

    @staticmethod
    def get_total_ram_gb() -> Optional[float]:
        """获取总内存（GB），失败返回 None。"""
        try:
            import psutil
            return round(psutil.virtual_memory().total / (1024 ** 3), 1)
        except ImportError:
            return None

    @staticmethod
    def get_available_ram_gb() -> Optional[float]:
        """获取可用内存（GB），失败返回 None。"""
        try:
            import psutil
            return round(psutil.virtual_memory().available / (1024 ** 3), 1)
        except ImportError:
            return None

    @staticmethod
    def get_gpu_info() -> Optional[str]:
        """获取 GPU 信息，失败返回 None。"""
        try:
            import pynvml
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            if count == 0:
                return None
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            total_gb = mem_info.total / (1024 ** 3)
            pynvml.nvmlShutdown()
            return f"{name.decode()} ({total_gb:.1f} GB)"
        except ImportError:
            logger.debug("pynvml 未安装，无法获取 GPU 信息")
            return None
        except Exception:
            logger.debug("获取 GPU 信息失败")
            return None

    @staticmethod
    def get_summary() -> dict:
        """获取系统信息摘要。"""
        return {
            "os": SystemInfo.get_os_info(),
            "python": SystemInfo.get_python_version(),
            "ram_gb": SystemInfo.get_total_ram_gb(),
            "gpu": SystemInfo.get_gpu_info(),
            "is_windows": SystemInfo.is_windows(),
        }

    @staticmethod
    def print_summary() -> None:
        """打印系统信息摘要到日志。"""
        info = SystemInfo.get_summary()
        logger.info("===== 系统信息 =====")
        logger.info(f"操作系统: {info['os']}")
        logger.info(f"Python版本: {info['python']}")
        logger.info(f"内存: {info['ram_gb']} GB")
        logger.info(f"GPU: {info['gpu'] or '未检测到'}")
        logger.info("====================")