"""视线跟随偏移与程序化特效层单元测试。

覆盖：
- ``compute_track_offset``：中心/边缘/限幅/超出半径归零（含修复前的 bug 场景）
- ``PetEffects``：发射节奏、未登记情绪、寿命回收、切换清空、数量上限、异常输入容错
"""

import json

import pytest

import ui.floating_pet as floating_pet
from ui.floating_pet import compute_track_offset, weighted_pick
from ui.pet_fx import EMOTION_EFFECTS, MAX_PARTICLES, Particle, PetEffects


class TestComputeTrackOffset:
    """鼠标视线跟随偏移计算（纯函数）。"""

    def test_center_returns_zero(self):
        assert compute_track_offset(128, 128, 256) == (0.0, 0.0)

    def test_offset_capped_at_max(self):
        """修复点：鼠标远离窗口时偏移被限幅在 max_offset 内。"""
        tx, _ = compute_track_offset(300, 128, 256, max_offset=3.0, radius=1000.0)
        assert tx == pytest.approx(3.0)

    def test_no_unbounded_growth(self):
        """修复点：原实现在鼠标远离时偏移会无限增大（如 20px）。"""
        tx, ty = compute_track_offset(1000, 1000, 256, max_offset=3.0, radius=5000.0)
        assert abs(tx) <= 3.0
        assert abs(ty) <= 3.0

    def test_far_away_returns_zero(self):
        """超出有效半径时偏移归零。"""
        assert compute_track_offset(4000, 4000, 256, radius=220.0) == (0.0, 0.0)

    def test_radius_boundary_inside(self):
        """恰好处于半径内：偏移非零。"""
        tx, _ = compute_track_offset(128 + 200, 128, 256, radius=220.0)
        assert tx != 0.0

    def test_radius_boundary_outside(self):
        """略超出半径：偏移归零。"""
        tx, _ = compute_track_offset(128 + 240, 128, 256, radius=220.0)
        assert tx == 0.0

    def test_symmetric_direction(self):
        """左右对称：偏移符号相反、幅值相同。"""
        left, _ = compute_track_offset(60, 128, 256)
        right, _ = compute_track_offset(196, 128, 256)
        assert left == pytest.approx(-right)

    def test_custom_max_offset(self):
        tx, _ = compute_track_offset(300, 128, 256, max_offset=10.0, radius=1000.0)
        assert tx == pytest.approx(10.0)


class TestPetEffects:
    """程序化特效层。"""

    def test_starts_empty(self):
        fx = PetEffects("happy")
        assert fx.particle_count == 0
        assert fx.has_visible is False

    def test_emits_after_interval(self):
        fx = PetEffects("happy")
        interval = EMOTION_EFFECTS["happy"].interval
        fx.advance(interval * 1000.0, 256)
        assert fx.particle_count >= 1

    def test_idle_has_no_effects(self):
        """未登记的情绪不产生特效。"""
        fx = PetEffects("idle")
        fx.advance(5000.0, 256)
        assert fx.particle_count == 0

    def test_expired_particles_are_removed(self):
        """寿命耗尽的粒子会被回收（用 idle 避免新粒子干扰）。"""
        fx = PetEffects("idle")           # idle 无发射器
        fx._particles.append(
            Particle(x=10.0, y=10.0, vx=0.0, vy=0.0, life=0.05, max_life=0.1, kind="heart")
        )
        assert fx.particle_count == 1
        fx.advance(100.0, 256)            # 推进 0.1s > life 0.05
        assert fx.particle_count == 0

    def test_particle_count_capped(self):
        fx = PetEffects("happy")
        for _ in range(200):
            fx.advance(500.0, 256)
        assert fx.particle_count <= MAX_PARTICLES

    def test_set_emotion_clears(self):
        fx = PetEffects("happy")
        fx.advance(1000.0, 256)
        assert fx.particle_count >= 1
        fx.set_emotion("sad")
        assert fx.particle_count == 0
        assert fx.emotion == "sad"

    def test_set_same_emotion_keeps_particles(self):
        fx = PetEffects("happy")
        fx.advance(1000.0, 256)
        before = fx.particle_count
        fx.set_emotion("happy")
        assert fx.particle_count == before

    def test_disabled_stops_and_clears(self):
        fx = PetEffects("happy")
        fx.advance(1000.0, 256)
        fx.set_enabled(False)
        assert fx.particle_count == 0
        fx.advance(5000.0, 256)
        assert fx.particle_count == 0

    def test_clear(self):
        fx = PetEffects("happy")
        fx.advance(1000.0, 256)
        fx.clear()
        assert fx.particle_count == 0

    def test_non_positive_dt_is_ignored(self):
        fx = PetEffects("happy")
        fx.advance(0.0, 256)
        fx.advance(-100.0, 256)
        assert fx.particle_count == 0

    def test_invalid_dt_type_is_safe(self):
        fx = PetEffects("happy")
        fx.advance("bad", 256)   # type: ignore[arg-type]
        assert fx.particle_count == 0

    def test_zero_size_is_ignored(self):
        fx = PetEffects("happy")
        fx.advance(5000.0, 0)
        assert fx.particle_count == 0

    def test_all_registered_emotions_emit(self):
        """每个登记的情绪都应能产出粒子（防止配置写错 kind/interval）。"""
        for emotion, config in EMOTION_EFFECTS.items():
            fx = PetEffects(emotion)
            steps = int(config.interval / 0.1) + 2      # 按 100ms 小步推进（贴近真实调用）
            for _ in range(steps):
                fx.advance(100.0, 256)
            assert fx.particle_count >= 1, f"{emotion} 未产出粒子"

    def test_color_for_known_and_unknown(self):
        fx = PetEffects()
        assert fx.color_for("heart").isValid()
        assert fx.color_for("not-a-kind").isValid()   # 回退白色

    def test_particle_alpha_decays(self):
        fx = PetEffects("happy")
        fx.advance(500.0, 256)
        particle = fx._particles[0]        # 直接检查内部状态
        first = particle.alpha
        fx.advance(500.0, 256)
        assert particle.alpha <= first


class TestWeightedPick:
    """微动作权重抽签（配置驱动）。"""

    def test_empty_returns_none(self):
        assert weighted_pick([]) is None

    def test_all_zero_weights_returns_none(self):
        assert weighted_pick([("happy", 0.0), ("sad", 0.0)]) is None

    def test_negative_weights_ignored(self):
        assert weighted_pick([("happy", -1.0)]) is None

    def test_single_candidate_always_picked(self):
        assert weighted_pick([("happy", 0.1)]) == "happy"

    def test_zero_weight_never_picked(self):
        for _ in range(20):
            assert weighted_pick([("happy", 1.0), ("sad", 0.0)]) == "happy"

    def test_distribution_respects_weight(self):
        """权重高 10 倍的动作应显著更常出现。"""
        picks = [weighted_pick([("heavy", 10.0), ("light", 1.0)]) for _ in range(400)]
        assert picks.count("heavy") > picks.count("light")


class TestMicroConfig:
    """pet_conf.json 微动作配置加载与容错。"""

    def test_default_when_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(floating_pet, "MICRO_CONF_PATH", str(tmp_path / "nope.json"))
        actions, interval, enabled = floating_pet._load_micro_config()
        assert enabled is True
        assert actions == list(floating_pet.DEFAULT_MICRO_ACTIONS)
        assert interval == floating_pet.DEFAULT_MICRO_INTERVAL

    def test_loaded_from_file(self, monkeypatch, tmp_path):
        path = tmp_path / "pet_conf.json"
        path.write_text(json.dumps({
            "micro_actions_enabled": False,
            "idle_min_interval_ms": 3000,
            "idle_max_interval_ms": 5000,
            "micro_actions": [{"act_list": ["happy", "alert"], "act_prob": 2.0}],
        }), encoding="utf-8")
        monkeypatch.setattr(floating_pet, "MICRO_CONF_PATH", str(path))
        actions, interval, enabled = floating_pet._load_micro_config()
        assert enabled is False
        assert actions == [("happy", 2.0), ("alert", 2.0)]
        assert interval == (3000, 5000)

    def test_broken_json_falls_back(self, monkeypatch, tmp_path):
        path = tmp_path / "pet_conf.json"
        path.write_text("{ not json", encoding="utf-8")
        monkeypatch.setattr(floating_pet, "MICRO_CONF_PATH", str(path))
        actions, _, enabled = floating_pet._load_micro_config()
        assert actions == list(floating_pet.DEFAULT_MICRO_ACTIONS)
        assert enabled is True

    def test_non_dict_json_falls_back(self, monkeypatch, tmp_path):
        path = tmp_path / "pet_conf.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        monkeypatch.setattr(floating_pet, "MICRO_CONF_PATH", str(path))
        actions, _, _ = floating_pet._load_micro_config()
        assert actions == list(floating_pet.DEFAULT_MICRO_ACTIONS)

    def test_interval_high_clamped_above_low(self, monkeypatch, tmp_path):
        """max < min 时自动纠正，避免 randint(low, high) 抛异常。"""
        path = tmp_path / "pet_conf.json"
        path.write_text(json.dumps({"idle_min_interval_ms": 9000,
                                    "idle_max_interval_ms": 1000}), encoding="utf-8")
        monkeypatch.setattr(floating_pet, "MICRO_CONF_PATH", str(path))
        _, interval, _ = floating_pet._load_micro_config()
        assert interval[1] >= interval[0]

    def test_real_pet_conf_is_valid(self):
        """仓库自带的 pet_conf.json 必须能被解析且动作名都有帧目录。"""
        actions, interval, _ = floating_pet._load_micro_config()
        assert actions, "自带配置未解析出任何动作"
        assert interval[0] > 0
        for name, _weight in actions:
            assert name in floating_pet.KNOWN_EMOTIONS, f"{name} 无对应帧目录"
