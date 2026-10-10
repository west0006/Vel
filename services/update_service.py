"""
自动更新服务模块。

预留接口，计划在阶段6实现。
架构：Updater.exe 启动器式更新，非原子替换。
"""

from typing import Optional
from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class UpdateService:
    """自动更新服务（阶段6实现）。"""

    def __init__(self):
        logger.info("更新服务已注册（暂未启用，阶段6实现）")

    def check_for_updates(self) -> Optional[str]:
        """检查是否有新版本。"""
        # TODO: 阶段6实现 GitHub Release 检查
        logger.debug("更新检查被调用（未实现）")
        return None

    def download_update(self, version: str, url: str) -> bool:
        """下载指定版本的更新包。"""
        logger.info(f"更新下载被调用（未实现）: v{version}")
        return False

    def apply_update(self) -> bool:
        """应用已下载的更新。"""
        logger.info("更新应用被调用（未实现）")
        return False

    def get_current_version(self) -> str:
        try:
            db = registry.get("database")
            if db:
                row = db.execute(
                    "SELECT current_version FROM update_info WHERE id=1"
                ).fetchone()
                if row:
                    return row[0]
        except Exception:
            logger.exception("get_current_version 执行失败")
        return "0.1.0-alpha"
