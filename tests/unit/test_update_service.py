"""UpdateService 单元测试。

`UpdateService` 目前是**占位骨架**（阶段7才实现），因此本测试锁定两件事：

1. **版本号来源唯一** —— 此前硬编码在方法内、与 `settings.yaml` 的 `app.version`
   形成两个来源；现统一为「表 > 配置 > 兜底常量」，本测试固化该优先级。
2. **占位契约明确** —— 未实现的方法必须返回 `None` / `False`，且 `main.py` 不注册它，
   避免把空壳当成可用功能接进 UI。
"""

import sqlite3
from pathlib import Path

import pytest

from core.config import config
from core.service_registry import registry
from services.update_service import UpdateService

MAIN_PY = Path(__file__).resolve().parents[2] / "main.py"


@pytest.fixture
def svc():
    return UpdateService()


@pytest.fixture
def clean_registry():
    registry.clear()
    yield registry
    registry.clear()


def _db_with_version(version=None):
    """按真实 schema 的 update_info 结构建内存库。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS update_info (
            id               INTEGER PRIMARY KEY CHECK(id = 1),
            current_version  TEXT NOT NULL,
            last_check_time  DATETIME,
            latest_version   TEXT,
            download_url     TEXT,
            sha256           TEXT,
            update_status    TEXT DEFAULT 'none'
        )
    """)
    if version is not None:
        conn.execute("INSERT INTO update_info (id, current_version) VALUES (1, ?)",
                     (version,))
        conn.commit()
    return conn


def _configured_version() -> str:
    return config.get_str("app.version", UpdateService.FALLBACK_VERSION)


class TestVersionPriority:
    """版本号来源优先级：update_info 表 > settings.yaml > 兜底常量。"""

    def test_database_value_wins(self, svc, clean_registry):
        clean_registry.register("database", _db_with_version("9.9.9"))
        assert svc.get_current_version() == "9.9.9"

    def test_falls_back_to_config_when_table_empty(self, svc, clean_registry):
        """表里没有记录时回退配置（这是消除"版本号双源"的关键路径）。"""
        clean_registry.register("database", _db_with_version(None))
        assert svc.get_current_version() == _configured_version()

    def test_falls_back_to_config_when_no_database(self, svc, clean_registry):
        assert svc.get_current_version() == _configured_version()

    def test_blank_database_value_falls_back(self, svc, clean_registry):
        clean_registry.register("database", _db_with_version(""))
        assert svc.get_current_version() == _configured_version()

    def test_database_error_falls_back(self, svc, clean_registry):
        class _Broken:
            def execute(self, *args, **kwargs):
                raise sqlite3.Error("boom")

        clean_registry.register("database", _Broken())
        assert svc.get_current_version() == _configured_version()

    def test_never_returns_empty(self, svc, clean_registry):
        assert svc.get_current_version()


class TestPlaceholderContract:
    """占位方法的契约：明确返回空值，不得伪装成可用功能。"""

    def test_check_for_updates_returns_none(self, svc):
        assert svc.check_for_updates() is None

    def test_download_update_returns_false(self, svc):
        assert svc.download_update("1.0.0", "https://example.invalid/pkg.zip") is False

    def test_apply_update_returns_false(self, svc):
        assert svc.apply_update() is False

    def test_main_does_not_register_update_service(self):
        """锁定"未接线"决策：若将来要接线，应先实现功能并更新本测试与文档。"""
        source = MAIN_PY.read_text(encoding="utf-8")
        assert "UpdateService" not in source, (
            "main.py 不应注册尚未实现的 UpdateService（见 doc/dev/盘点-质量与生态现状.md Q5）"
        )

    def test_fallback_version_constant_present(self):
        assert UpdateService.FALLBACK_VERSION
