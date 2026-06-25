"""
服务注册器模块。

轻量级依赖注入容器，各模块通过注册/获取来共享服务实例。
"""

from typing import Any, Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class ServiceRegistry:
    """服务注册器，管理全局服务实例。"""

    def __init__(self):
        self._services: Dict[str, Any] = {}

    def register(self, name: str, instance: Any, override: bool = False) -> None:
        """注册服务实例。

        Args:
            name: 服务名称
            instance: 服务实例
            override: 是否允许覆盖已存在的服务

        Raises:
            ValueError: 服务已存在且 override=False
        """
        if name in self._services and not override:
            raise ValueError(f"服务 '{name}' 已存在，如需覆盖请设置 override=True")
        self._services[name] = instance
        logger.info(f"服务已注册: {name} = {instance.__class__.__name__}")

    def get(self, name: str, default: Any = None) -> Any:
        """获取服务实例。

        Args:
            name: 服务名称
            default: 不存在时返回的默认值

        Returns:
            服务实例，不存在时返回 default
        """
        return self._services.get(name, default)

    def has(self, name: str) -> bool:
        """检查服务是否已注册。"""
        return name in self._services

    def remove(self, name: str) -> None:
        """移除已注册的服务。"""
        if name in self._services:
            del self._services[name]
            logger.info(f"服务已移除: {name}")

    def list_services(self) -> Dict[str, str]:
        """列出所有已注册的服务及类型名称。"""
        return {k: v.__class__.__name__ for k, v in self._services.items()}

    def clear(self) -> None:
        """清空所有服务注册。"""
        self._services.clear()


# 全局单例
registry = ServiceRegistry()