"""AppConfig 统一配置模块单元测试。

覆盖：yaml 嵌套读取 · 类型转换 · app_settings 覆盖优先级 · 历史键名别名兼容 ·
空值回退 · yaml 缺失/损坏/非法值容错 · 写入行为。
"""

import sqlite3

import pytest

from core.config import AppConfig

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

_YAML = """
app:
  name: "Vel - 智能AI桌宠"
  version: "0.1.0-alpha"

llm:
  model: "qwen2.5:7b-instruct-q4_K_M"
  host: "127.0.0.1"
  port: 11434
  timeout: 30
  max_tokens: 2048
  temperature: 0.7

health:
  drink_interval_min: 45
  drink_target_ml: 2000

sleep:
  start: "23:00"
  end: "07:00"

memory:
  faiss_dimension: 384
"""


def _yaml_file(tmp_path, text=_YAML):
    """写一个临时 settings.yaml 并返回路径。"""
    path = tmp_path / "settings.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _db(rows=()):
    """建一个带 app_settings 表的内存数据库。"""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    for key, value in rows:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)", (key, value)
        )
    conn.commit()
    return conn


class TestYamlReading:
    """仅读 yaml 的场景。"""

    def test_nested_path(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        assert cfg.get("llm.model") == "qwen2.5:7b-instruct-q4_K_M"
        assert cfg.get("app.name") == "Vel - 智能AI桌宠"

    def test_int_conversion(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        assert cfg.get_int("llm.port") == 11434
        assert cfg.get_int("llm.timeout") == 30

    def test_float_conversion(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        assert cfg.get_float("llm.temperature") == pytest.approx(0.7)

    def test_str_conversion_strips(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        assert cfg.get_str("llm.host") == "127.0.0.1"

    def test_section_returns_copy(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        llm = cfg.section("llm")
        assert llm["model"] == "qwen2.5:7b-instruct-q4_K_M"
        llm["model"] = "mutated"
        assert cfg.get("llm.model") == "qwen2.5:7b-instruct-q4_K_M"

    def test_section_missing_returns_empty(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        assert cfg.section("not_exist") == {}


class TestDbOverride:
    """app_settings 覆盖 yaml 的优先级。"""

    def test_db_overrides_yaml(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(_db([("llm.timeout", "60")]))
        assert cfg.get_int("llm.timeout") == 60

    def test_alias_key_is_honoured(self, tmp_path):
        """历史键名 drink_daily_target_ml 应映射到 health.drink_target_ml。"""
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(_db([("drink_daily_target_ml", "2500")]))
        assert cfg.get_int("health.drink_target_ml") == 2500

    def test_alias_key_for_sleep(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(_db([("sleep_start", "22:30")]))
        assert cfg.get_str("sleep.start") == "22:30"

    def test_canonical_key_beats_alias(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(
            _db([("health.drink_target_ml", "3000"), ("drink_daily_target_ml", "1")])
        )
        assert cfg.get_int("health.drink_target_ml") == 3000

    def test_empty_db_value_falls_back_to_yaml(self, tmp_path):
        """app_settings 中的空串视为未设置，继续回退到 yaml。"""
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(_db([("llm.model", "")]))
        assert cfg.get("llm.model") == "qwen2.5:7b-instruct-q4_K_M"

    def test_db_only_key(self, tmp_path):
        """yaml 中没有、仅 app_settings 有的键也能读到。"""
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(_db([("theme_color", "#D2691E")]))
        assert cfg.get_str("theme_color") == "#D2691E"


class TestFallback:
    """异常与缺失场景一律回退默认值，不抛异常。"""

    def test_missing_yaml_uses_default(self, tmp_path):
        cfg = AppConfig(str(tmp_path / "not_exist.yaml"))
        assert cfg.get("llm.model", "fallback") == "fallback"

    def test_broken_yaml_uses_default(self, tmp_path):
        path = _yaml_file(tmp_path, "llm: [unclosed\n  bad: : :")
        cfg = AppConfig(path)
        assert cfg.get("llm.model", "fallback") == "fallback"

    def test_non_mapping_yaml_uses_default(self, tmp_path):
        path = _yaml_file(tmp_path, "- just\n- a list\n")
        cfg = AppConfig(path)
        assert cfg.get("llm.model", "fallback") == "fallback"

    def test_invalid_int_uses_default(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(_db([("llm.timeout", "not-a-number")]))
        assert cfg.get_int("llm.timeout", 30) == 30

    def test_bool_literals(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(
            _db([("flag_on", "true"), ("flag_off", "0"), ("flag_bad", "maybe")])
        )
        assert cfg.get_bool("flag_on", False) is True
        assert cfg.get_bool("flag_off", True) is False
        assert cfg.get_bool("flag_bad", True) is True

    def test_no_db_bound_is_safe(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        assert cfg.get_int("llm.timeout") == 30
        assert cfg.get("nonexistent.key", "d") == "d"

    def test_db_without_table_is_safe(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(sqlite3.connect(":memory:"))
        assert cfg.get_int("llm.timeout") == 30


class TestWrite:
    """写入 app_settings。"""

    def test_set_writes_value(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        conn = _db()
        cfg.bind_db(conn)
        assert cfg.set("llm.timeout", 45) is True
        assert cfg.get_int("llm.timeout") == 45
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'llm.timeout'"
        ).fetchone()
        assert row[0] == "45"

    def test_set_writes_alias_too(self, tmp_path):
        """写入规范键时同步写别名，保证两套读取者都能看到。"""
        cfg = AppConfig(_yaml_file(tmp_path))
        conn = _db()
        cfg.bind_db(conn)
        cfg.set("health.drink_target_ml", 2500)
        aliased = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'drink_daily_target_ml'"
        ).fetchone()
        assert aliased[0] == "2500"

    def test_set_overwrites_existing(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        cfg.bind_db(_db([("llm.timeout", "10")]))
        cfg.set("llm.timeout", 99)
        assert cfg.get_int("llm.timeout") == 99

    def test_set_without_db_returns_false(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        assert cfg.set("llm.timeout", 1) is False

    def test_reload_refreshes_from_db(self, tmp_path):
        cfg = AppConfig(_yaml_file(tmp_path))
        conn = _db()
        cfg.bind_db(conn)
        assert cfg.get_int("llm.timeout") == 30  # 来自 yaml
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES ('llm.timeout', '77')"
        )
        conn.commit()
        cfg.reload()
        assert cfg.get_int("llm.timeout") == 77
