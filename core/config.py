"""
统一配置访问模块。

设计依据（AGENTS.md §4.6）：

    优先级：``app_settings`` 表（用户运行时修改）
          > ``config/settings.yaml``（出厂默认）
          > 代码内兜底默认值（调用方传入的 ``default``）

**键名规范**：统一使用 ``config/settings.yaml`` 的嵌套路径点号形式，
例如 ``llm.model``、``health.drink_interval_min``、``sleep.start``。

**历史包袱**：``app_settings`` 表中早期写入的键名与 yaml 不一致
（例如表中 ``drink_daily_target_ml`` 对应 yaml 的 ``health.drink_target_ml``、
``sleep_start`` 对应 ``sleep.start``），由 ``_DB_KEY_ALIASES`` 做兼容映射；
新增配置项请直接使用规范键名，不要再引入新别名。

本模块位于 ``core`` 层，只依赖 ``utils``（AGENTS.md §三 分层边界）。
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

#: 规范键 → ``app_settings`` 表中可能使用的历史键名（按优先级排列）
_DB_KEY_ALIASES: Dict[str, Tuple[str, ...]] = {
    # health 段的键在 app_settings 中历史以"无前缀"形式存在（见 schema.sql 的初始值），
    # 缺少这些映射会导致：schema/用户数据里的值读不到（静默回退 yaml 默认）、
    # config.set() 写入后旧键不更新（使用者读到的仍是旧值）。
    "health.drink_interval_min": ("drink_interval_min",),
    "health.drink_target_ml": ("drink_daily_target_ml", "drink_target_ml"),
    "health.sedentary_threshold_min": ("sedentary_threshold_min",),
    "health.active_hours_start": ("active_hours_start",),
    "health.active_hours_end": ("active_hours_end",),
    "sleep.start": ("sleep_start",),
    "sleep.end": ("sleep_end",),
    "search.gaode_daily_limit": ("gaode_daily_limit",),
    "search.bing_monthly_limit": ("bing_monthly_limit",),
}

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "y", "t"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "n", "f"})


def project_root() -> str:
    """返回项目根目录（兼容 PyInstaller 打包后的 ``_MEIPASS``）。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_yaml_path() -> str:
    """返回默认的 ``config/settings.yaml`` 路径。"""
    return os.path.join(project_root(), "config", "settings.yaml")


class AppConfig:
    """应用配置访问器。

    yaml 与 app_settings 均为**惰性加载**：首次读取时才真正访问磁盘/数据库，
    因此可以在数据库连接就绪之前先创建实例。

    所有读取方法都不会抛异常：yaml 缺失或损坏、数据库未绑定、类型转换失败，
    一律回退到调用方传入的默认值并记录日志。
    """

    def __init__(self, yaml_path: Optional[str] = None) -> None:
        """
        Args:
            yaml_path: 自定义 yaml 路径，默认 ``config/settings.yaml``。
        """
        self._yaml_path = yaml_path or default_yaml_path()
        self._yaml: Dict[str, Any] = {}
        self._yaml_loaded = False
        self._db: Any = None
        self._db_cache: Dict[str, Any] = {}
        self._db_loaded = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def bind_db(self, conn: Any) -> None:
        """注入 sqlite 连接并载入 ``app_settings``。

        Args:
            conn: ``sqlite3.Connection``；传 ``None`` 表示解绑。
        """
        self._db = conn
        self._db_loaded = False
        self._db_cache = {}
        if conn is not None:
            self._load_db()

    def reload(self) -> None:
        """清空缓存并重新加载（设置面板保存后调用）。"""
        self._yaml_loaded = False
        self._yaml = {}
        self._db_loaded = False
        self._db_cache = {}
        logger.info("配置缓存已清空，将在下次读取时重新加载")

    @property
    def yaml_path(self) -> str:
        """当前使用的 yaml 路径。"""
        return self._yaml_path

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """按规范键读取配置值。

        Args:
            key: 规范键，如 ``llm.model``。
            default: 三级都查不到时的兜底值。

        Returns:
            配置值；``app_settings`` 中的值优先于 yaml。
        """
        self._load_db()
        for candidate in self._db_candidates(key):
            if candidate in self._db_cache:
                value = self._db_cache[candidate]
                if value is not None and str(value) != "":
                    return value
        value = self._lookup_yaml(key)
        return default if value is None else value

    def get_int(self, key: str, default: int = 0) -> int:
        """读取整数配置。

        支持 yaml 中的数字与 ``app_settings`` 中的字符串数字；
        转换失败返回 ``default``。
        """
        raw = self.get(key, None)
        if raw is None:
            return default
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            logger.warning("配置 %s=%r 不是合法整数，回退 %s", key, raw, default)
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """读取浮点配置，转换失败返回 ``default``。"""
        raw = self.get(key, None)
        if raw is None:
            return default
        try:
            return float(str(raw).strip())
        except (TypeError, ValueError):
            logger.warning("配置 %s=%r 不是合法浮点数，回退 %s", key, raw, default)
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """读取布尔配置，识别常见的真/假字面量。"""
        raw = self.get(key, None)
        if raw is None:
            return default
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in _TRUE_VALUES:
            return True
        if text in _FALSE_VALUES:
            return False
        logger.warning("配置 %s=%r 不是合法布尔值，回退 %s", key, raw, default)
        return default

    def get_str(self, key: str, default: str = "") -> str:
        """读取字符串配置，空值回退 ``default``。"""
        raw = self.get(key, None)
        if raw is None:
            return default
        text = str(raw).strip()
        return text if text else default

    def section(self, prefix: str) -> Dict[str, Any]:
        """读取某个 yaml 段的全部内容（只反映 yaml，不含 app_settings 覆盖）。

        Args:
            prefix: 段名，如 ``llm``。

        Returns:
            该段的字典副本；不存在时返回空字典。
        """
        self._ensure_yaml()
        value = self._yaml.get(prefix, {})
        if not isinstance(value, Mapping):
            logger.warning("配置段 %s 不是映射类型，忽略", prefix)
            return {}
        return dict(value)

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> bool:
        """写入 ``app_settings``（用户修改的唯一落点）。

        Args:
            key: 规范键；会同时写入其规范键名与首个历史别名，保持两套读取者一致。
            value: 值，写入前统一转成字符串。

        Returns:
            是否写入成功。
        """
        if self._db is None:
            logger.warning("数据库未绑定，配置 %s 无法写入", key)
            return False
        payload = "" if value is None else str(value)
        targets = [key, *_DB_KEY_ALIASES.get(key, ())]
        try:
            cursor = self._db.cursor()
            for target in targets:
                cursor.execute(
                    "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (target, payload),
                )
                self._db_cache[target] = payload
            self._db.commit()
            logger.info("配置已写入 %s=%s", key, payload)
            return True
        except Exception:
            logger.exception("写入配置 %s 失败", key)
            return False

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _db_candidates(self, key: str) -> Tuple[str, ...]:
        """返回该规范键在 app_settings 中的候选键名（含历史别名）。"""
        if key in _DB_KEY_ALIASES:
            return (key, *_DB_KEY_ALIASES[key])
        return (key,)

    def _ensure_yaml(self) -> None:
        """惰性加载 settings.yaml（失败时降级为空配置，不抛异常）。"""
        if self._yaml_loaded:
            return
        self._yaml_loaded = True
        if not os.path.exists(self._yaml_path):
            logger.warning("配置文件不存在，全部使用默认值: %s", self._yaml_path)
            return
        try:
            import yaml

            with open(self._yaml_path, "r", encoding="utf-8") as fp:
                data = yaml.safe_load(fp)
            if isinstance(data, Mapping):
                self._yaml = dict(data)
                logger.info("配置已加载: %s (%d 个顶层段)",
                            self._yaml_path, len(self._yaml))
            else:
                logger.warning("配置文件内容不是映射结构，忽略: %s", self._yaml_path)
        except Exception:
            logger.exception("读取配置文件失败，全部使用默认值: %s", self._yaml_path)

    def _load_db(self) -> None:
        """惰性加载 app_settings 全部键值。"""
        if self._db_loaded or self._db is None:
            return
        self._db_loaded = True
        try:
            cursor = self._db.execute("SELECT key, value FROM app_settings")
            self._db_cache = {str(k): v for k, v in cursor.fetchall()}
            logger.info("从 app_settings 载入 %d 个配置键", len(self._db_cache))
        except Exception:
            logger.exception("读取 app_settings 失败，将只使用 yaml 默认值")
            self._db_cache = {}

    def _lookup_yaml(self, key: str) -> Any:
        """按点号路径在 yaml 中查找。"""
        self._ensure_yaml()
        node: Any = self._yaml
        for part in str(key).split("."):
            if not isinstance(node, Mapping) or part not in node:
                return None
            node = node[part]
        return node


#: 进程内共享实例。main.py 在数据库就绪后调用 ``config.bind_db(conn)``。
config = AppConfig()
