"""
全局状态管理器模块。

维护两个关联的状态机：
1. 用户活动状态 (active / idle / busy / sleep / away)
2. 桌宠行为模式 (companion / caretaker / alarm / silent)

状态变更通过事件总线发布通知。
"""

from enum import Enum
from typing import Optional

from core.event_bus import bus, EVENT_USER_ACTIVITY_CHANGE, EVENT_MODE_CHANGE
from utils.logger import get_logger

logger = get_logger(__name__)


class UserActivityState(Enum):
    """用户活动状态。"""
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    SLEEP = "sleep"
    AWAY = "away"


class PetMode(Enum):
    """桌宠行为模式。"""
    COMPANION = "companion"      # 陪伴模式，轻量互动
    CARETAKER = "caretaker"      # 关怀模式，主动推送
    ALARM = "alarm"              # 通知模式，强提醒
    SILENT = "silent"            # 静默模式


class StateManager:
    """状态管理器，负责状态转换和通知。"""

    def __init__(self):
        self._user_state: UserActivityState = UserActivityState.ACTIVE
        self._pet_mode: PetMode = PetMode.COMPANION
        self._previous_mode: Optional[PetMode] = None  # alarm 临时切换时保存原模式
        self._quiet_mode = False  # 手动免打扰
        self._quiet_start: Optional[str] = None
        self._quiet_end: Optional[str] = None

    # ------------------------------------------------------------------
    # 用户活动状态
    # ------------------------------------------------------------------

    @property
    def user_state(self) -> UserActivityState:
        return self._user_state

    def set_user_state(self, new_state: UserActivityState) -> None:
        """设置用户活动状态，并按规则触发桌宠模式切换。"""
        old = self._user_state
        if old == new_state:
            return

        self._user_state = new_state
        logger.info(f"用户状态: {old.value} → {new_state.value}")

        # 发布状态变更事件
        bus.publish(EVENT_USER_ACTIVITY_CHANGE, {
            "old": old.value,
            "new": new_state.value,
        })

        # 根据用户状态自动调整桌宠模式
        self._auto_adjust_mode(old, new_state)

    def _auto_adjust_mode(self, old_state: UserActivityState, new_state: UserActivityState) -> None:
        """用户状态变化时自动调整桌宠模式。"""
        if self._pet_mode == PetMode.ALARM:
            return

        # 免打扰状态下：允许自动进入 SILENT，但不自动退出（保留人工控制）
        if self._quiet_mode:
            return

        if new_state in (UserActivityState.BUSY, UserActivityState.SLEEP, UserActivityState.AWAY):
            self.set_pet_mode(PetMode.SILENT, auto=True)
        elif new_state == UserActivityState.IDLE:
            if old_state in (UserActivityState.ACTIVE,):
                self.set_pet_mode(PetMode.CARETAKER, auto=True)
        elif new_state == UserActivityState.ACTIVE:
            if self._pet_mode in (PetMode.SILENT, PetMode.CARETAKER):
                self.set_pet_mode(PetMode.COMPANION, auto=True)

    # ------------------------------------------------------------------
    # 桌宠行为模式
    # ------------------------------------------------------------------

    @property
    def pet_mode(self) -> PetMode:
        return self._pet_mode

    def set_pet_mode(self, mode: PetMode, auto: bool = False) -> None:
        """设置桌宠模式。

        Args:
            mode: 目标模式
            auto: 是否为自动切换（True 时忽略免打扰状态）
        """
        old = self._pet_mode
        if old == mode:
            return

        # 免打扰状态下不允许手动切换
        if self._quiet_mode and not auto:
            logger.info(f"免打扰模式中，忽略手动模式切换: {mode.value}")
            return

        self._pet_mode = mode
        logger.info(f"桌宠模式: {old.value} → {mode.value}")

        bus.publish(EVENT_MODE_CHANGE, {
            "old": old.value,
            "new": mode.value,
            "auto": auto,
        })

    def enter_alarm_mode(self) -> None:
        """临时进入提醒模式，记录原模式以便恢复。"""
        if self._pet_mode == PetMode.ALARM:
            return
        self._previous_mode = self._pet_mode
        self._pet_mode = PetMode.ALARM

        bus.publish(EVENT_MODE_CHANGE, {
            "old": self._previous_mode.value,
            "new": "alarm",
            "auto": True,
        })

    def exit_alarm_mode(self) -> None:
        """退出提醒模式，恢复之前的模式。"""
        previous = self._previous_mode or PetMode.COMPANION
        self._previous_mode = None
        self._pet_mode = previous

        bus.publish(EVENT_MODE_CHANGE, {
            "old": "alarm",
            "new": previous.value,
            "auto": True,
        })

    # ------------------------------------------------------------------
    # 免打扰
    # ------------------------------------------------------------------

    @property
    def is_quiet_mode(self) -> bool:
        return self._quiet_mode

    def set_quiet_mode(self, enabled: bool) -> None:
        """手动设置免打扰模式。"""
        self._quiet_mode = enabled
        if enabled:
            self.set_pet_mode(PetMode.SILENT, auto=True)
        else:
            self.set_pet_mode(PetMode.COMPANION, auto=True)

    # ------------------------------------------------------------------
    # 便捷查询
    # ------------------------------------------------------------------

    def can_notify(self) -> bool:
        """判断当前是否可以发出通知。"""
        return (
            self._pet_mode != PetMode.SILENT
            and not self._quiet_mode
            and self._user_state not in (UserActivityState.BUSY, UserActivityState.SLEEP)
        )

    def is_user_active(self) -> bool:
        """用户是否处于可交互状态。"""
        return self._user_state in (UserActivityState.ACTIVE, UserActivityState.IDLE)