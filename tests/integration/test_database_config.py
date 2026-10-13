"""数据库 schema 与配置体系的端到端集成测试。

验证 `data/db/schema.sql` 可被真实应用，且 `core/config.py` 能按设计的三层优先级
（`app_settings` 用户修改 > `settings.yaml` 出厂默认 > 调用方兜底）读取，
以及历史键名的别名映射在**真实表结构**上生效。
"""

import sqlite3
from pathlib import Path

import pytest

from core.config import AppConfig

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "schema.sql"

#: 迁移脚本所在目录（AGENTS.md §2 要求表结构变更必须留 migration）
MIGRATIONS_DIR = SCHEMA_PATH.parent / "migrations"


def _new_db() -> sqlite3.Connection:
    """按真实 schema.sql 建立内存库。"""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    return conn


@pytest.fixture
def db():
    conn = _new_db()
    yield conn
    conn.close()


class TestSchema:
    """schema.sql 自身可用性。"""

    def test_schema_file_exists(self):
        assert SCHEMA_PATH.exists(), "data/db/schema.sql 缺失"

    def test_creates_all_expected_tables(self, db):
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {
            "user_profile", "user_traits", "episodic_memory", "conversation_archive",
            "meal_log", "drink_log", "activity_log", "sleep_log", "mood_snapshot",
            "schedule", "schedule_instance", "search_cache", "location_cache",
            "app_settings", "update_info", "memo", "daily_diary", "habit",
        }
        assert not (expected - tables), f"schema 缺少表: {expected - tables}"

    def test_app_settings_seeded(self, db):
        rows = dict(db.execute("SELECT key, value FROM app_settings").fetchall())
        assert rows["drink_interval_min"] == "45"
        assert rows["drink_daily_target_ml"] == "2000"
        assert rows["sleep_start"] == "23:00"

    def test_schema_is_idempotent(self, db):
        """重复执行 schema.sql 不应报错（IF NOT EXISTS / INSERT OR IGNORE）。"""
        db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        db.commit()

    def test_migrations_dir_exists(self):
        assert MIGRATIONS_DIR.is_dir(), "data/db/migrations/ 应存在（AGENTS.md §2 约定）"


class TestConfigAgainstRealDb:
    """端到端：schema → app_settings → core.config → 调用方。"""

    def test_reads_app_settings_without_yaml(self, db, tmp_path):
        config = AppConfig(yaml_path=str(tmp_path / "absent.yaml"))   # 无 yaml 文件
        config.bind_db(db)
        assert config.get_int("drink_interval_min") == 45

    def test_alias_maps_historical_key(self, db, tmp_path):
        """表中的历史键 drink_daily_target_ml 应能通过规范键读取。"""
        config = AppConfig(yaml_path=str(tmp_path / "absent.yaml"))
        config.bind_db(db)
        assert config.get_int("health.drink_target_ml") == 2000

    def test_write_then_read_roundtrip(self, db, tmp_path):
        """写入落到 app_settings，并能读回（含别名双写）。"""
        config = AppConfig(yaml_path=str(tmp_path / "absent.yaml"))
        config.bind_db(db)
        assert config.set("health.sedentary_threshold_min", 65) is True
        assert config.get_int("health.sedentary_threshold_min") == 65
        row = db.execute(
            "SELECT value FROM app_settings WHERE key='sedentary_threshold_min'"
        ).fetchone()
        assert row[0] == "65"

    def test_yaml_default_used_when_key_absent_in_db(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("llm:\n  timeout: 42\n", encoding="utf-8")
        config = AppConfig(str(yaml_path))
        config.bind_db(_new_db())
        assert config.get_int("llm.timeout") == 42

    def test_db_overrides_yaml_default(self, tmp_path):
        """同一键两处都有时，app_settings（用户修改）优先。"""
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("llm:\n  timeout: 42\n", encoding="utf-8")
        config = AppConfig(str(yaml_path))
        config.bind_db(_new_db())
        config.set("llm.timeout", 99)
        assert config.get_int("llm.timeout") == 99

    def test_real_settings_yaml_is_readable(self, db):
        """仓库自带的出厂配置必须可被解析（防止 yaml 语法错误导致全线回退默认值）。"""
        config = AppConfig()                 # 使用仓库默认 config/settings.yaml
        config.bind_db(db)
        assert config.get_str("llm.model"), "llm.model 未从 settings.yaml 读到"
        assert config.get_int("llm.max_tokens") > 0
        assert config.get_int("search.gaode_daily_limit") > 0
