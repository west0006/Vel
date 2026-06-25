"""StateManager 单元测试。"""

import pytest
from core.state_manager import StateManager, UserActivityState, PetMode


class TestStateManager:
    def setup_method(self):
        self.sm = StateManager()

    # 用户状态

    def test_initial_state_is_active(self):
        assert self.sm.user_state == UserActivityState.ACTIVE

    def test_set_user_state_changes(self):
        self.sm.set_user_state(UserActivityState.IDLE)
        assert self.sm.user_state == UserActivityState.IDLE

    def test_same_state_no_event(self):
        # 不应抛异常
        self.sm.set_user_state(UserActivityState.ACTIVE)

    # 模式自动调整

    def test_active_to_busy_triggers_silent(self):
        self.sm.set_user_state(UserActivityState.BUSY)
        assert self.sm.pet_mode == PetMode.SILENT

    def test_active_to_idle_triggers_caretaker(self):
        self.sm.set_user_state(UserActivityState.IDLE)
        assert self.sm.pet_mode == PetMode.CARETAKER

    def test_idle_to_active_triggers_companion(self):
        self.sm.set_user_state(UserActivityState.IDLE)
        self.sm.set_user_state(UserActivityState.ACTIVE)
        assert self.sm.pet_mode == PetMode.COMPANION

    # 免打扰

    def test_quiet_mode_prevents_manual_switch(self):
        self.sm.set_quiet_mode(True)
        self.sm.set_pet_mode(PetMode.COMPANION, auto=False)
        assert self.sm.pet_mode == PetMode.SILENT  # quiet 强制

    def test_quiet_mode_allows_auto_switch(self):
        self.sm.set_quiet_mode(True)
        self.sm.set_pet_mode(PetMode.SILENT, auto=True)
        assert self.sm.pet_mode == PetMode.SILENT

    def test_exit_quiet_mode(self):
        self.sm.set_quiet_mode(True)
        self.sm.set_quiet_mode(False)
        assert self.sm.pet_mode == PetMode.COMPANION

    # 告警模式

    def test_alarm_saves_and_restores(self):
        self.sm.enter_alarm_mode()
        assert self.sm.pet_mode == PetMode.ALARM
        self.sm.exit_alarm_mode()
        assert self.sm.pet_mode == PetMode.COMPANION

    # 通知判断

    def test_can_notify_active_companion(self):
        assert self.sm.can_notify()

    def test_cannot_notify_silent(self):
        self.sm.set_user_state(UserActivityState.BUSY)
        assert not self.sm.can_notify()

    def test_is_user_active(self):
        assert self.sm.is_user_active()
        self.sm.set_user_state(UserActivityState.SLEEP)
        assert not self.sm.is_user_active()