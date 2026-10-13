"""integration 测试共享夹具。

integration 测试的特点：使用**真实**的 EventBus / ServiceRegistry / SQLite schema，
只对无法在测试环境使用的外部依赖（LLM、网络）打桩。
"""

import os

import pytest

# 必须在导入 PyQt5 之前设置，避免无显示环境下创建窗口失败
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from core.service_registry import registry


@pytest.fixture(scope="session")
def qt_app():
    """offscreen 模式的 QApplication（事件总线的 UI 投递需要事件循环）。"""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def clean_registry():
    """清空全局服务注册表，测试后同样清理。

    注意：`registry.register()` 默认不允许重复注册（会抛 ValueError），
    因此集成测试必须显式隔离，否则会相互干扰。
    """
    registry.clear()
    yield registry
    registry.clear()
