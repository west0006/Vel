"""
自动更新服务模块。

⚠️ **当前为占位骨架，未实现**（2026-10-08 用户决策：暂不实现）。

设计规格见 `doc/reference/设计-项目详细设计-Vel v1.1.md`：

- §4.8 自动更新模块（GitHub Releases API）；
- §9.5 自动更新安全性与回滚 —— **启动器模式**（`Updater.exe`）+ SHA256 校验 +
  原子替换 + 连续 3 次启动失败自动恢复上一版本。

本服务**不会被 `main.py` 注册**（未接线），因此日志不得声称"已注册"。
待真正开发时应同步：`update_info` 表已就绪（current_version / last_check_time /
latest_version / download_url / sha256 / update_status）。
"""

from typing import Optional

from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class UpdateService:
    """自动更新服务（占位骨架，见模块 docstring）。"""

    #: 数据库与配置都读不到版本号时的兜底值
    FALLBACK_VERSION = "0.1.0-alpha"

    def __init__(self):
        # 本服务当前未接线（main.py 不注册），日志如实描述实例化状态，
        # 避免此前"更新服务已注册"的误导性输出。
        logger.info("更新服务已实例化（占位骨架，未接线）")

    # ------------------------------------------------------------------
    # 版本号
    # ------------------------------------------------------------------

    def get_current_version(self) -> str:
        """返回当前版本号。

        优先级：``update_info`` 表 > ``config/settings.yaml`` 的 ``app.version`` >
        ``FALLBACK_VERSION`` 常量。

        此前该版本号硬编码在方法内、与 `settings.yaml` 的 ``app.version`` 形成
        **两个来源**，存在不一致隐患；现统一为上述优先级。
        """
        try:
            db = registry.get("database")
            if db:
                row = db.execute(
                    "SELECT current_version FROM update_info WHERE id=1"
                ).fetchone()
                if row and row[0]:
                    return row[0]
        except Exception:
            logger.exception("get_current_version 读取 update_info 失败")

        try:
            from core.config import config

            version = config.get_str("app.version", "")
            if version:
                return version
        except Exception:
            logger.exception("get_current_version 读取 app.version 失败")

        return self.FALLBACK_VERSION

    # ------------------------------------------------------------------
    # 以下接口均为占位（阶段7实现）
    # ------------------------------------------------------------------

    def check_for_updates(self) -> Optional[str]:
        """检查是否有新版本。

        TODO（阶段7）：调用 GitHub Releases API，结果写入 ``update_info``
        （``latest_version`` / ``download_url`` / ``sha256`` / ``last_check_time``）。

        Returns:
            新版本号；无更新或未实现时返回 ``None``。
        """
        logger.debug("更新检查被调用（尚未实现，阶段7）")
        return None

    def download_update(self, version: str, url: str) -> bool:
        """下载指定版本的更新包。

        TODO（阶段7）：下载到临时目录、校验 SHA256、置
        ``update_info.update_status = 'ready'``。
        """
        logger.info(f"更新下载被调用（尚未实现，阶段7）: v{version}")
        return False

    def apply_update(self) -> bool:
        """应用已下载的更新。

        TODO（阶段7）：按设计文档 §9.5 的启动器模式执行 ——
        启动独立 ``Updater.exe`` → 主程序退出 → Updater 备份并替换文件 → 重启主程序。
        """
        logger.info("更新应用被调用（尚未实现，阶段7）")
        return False
