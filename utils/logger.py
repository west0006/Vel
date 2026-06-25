"""
统一日志工具模块。

提供标准化的日志输出，支持文件和控制台两种处理器。
所有模块应通过此模块获取 logger 实例。
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class LoggerManager:
    """日志管理器，统一管理日志配置和 logger 实例获取。"""

    _initialized = False

    @classmethod
    def init(
        cls,
        log_dir: Optional[str] = None,
        level: int = logging.DEBUG,
        console_level: int = logging.INFO,
        max_bytes: int = 5 * 1024 * 1024,
        backup_count: int = 3,
    ) -> None:
        """初始化全局日志配置。

        Args:
            log_dir: 日志文件目录，为 None 则不写入文件
            level: 日志级别
            console_level: 控制台日志级别
            max_bytes: 单个日志文件最大字节数
            backup_count: 保留的备份文件数
        """
        if cls._initialized:
            return

        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # 清空已有处理器，避免重复添加
        root_logger.handlers.clear()

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        root_logger.addHandler(console_handler)

        # 文件处理器
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            file_path = log_path / "deskpet.log"
            file_handler = logging.handlers.RotatingFileHandler(
                str(file_path), maxBytes=max_bytes, backupCount=backup_count,
                encoding="utf-8"
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
            root_logger.addHandler(file_handler)

        cls._initialized = True

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """获取指定名称的 logger 实例。

        Args:
            name: 模块名称，通常使用 __name__

        Returns:
            配置好的 Logger 实例
        """
        return logging.getLogger(name)


# 快捷函数
get_logger = LoggerManager.get_logger
log_init = LoggerManager.init