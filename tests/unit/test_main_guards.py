"""main.py 的回归守卫 —— 防止已修复的缺陷再次出现。

这里只放"难以用常规单测覆盖、但曾经真实踩过"的检查点。
"""

import inspect

import main


class TestWindowsApiImports:
    """V0014：``_check_idle_and_fullscreen`` 依赖 ``ctypes.wintypes``。

    缺陷：``ctypes.wintypes`` 是**独立子模块**，仅 ``import ctypes`` 不会让它
    成为 ``ctypes`` 的属性，于是 ``ctypes.wintypes.RECT()`` 抛 ``AttributeError``。
    该函数由 QTimer 每 5 秒调用一次，导致全屏/闲置检测完全失效，且日志被同一
    异常持续刷屏。
    """

    def test_ctypes_wintypes_is_imported(self):
        """方法体内必须显式导入该子模块。"""
        source = inspect.getsource(main.VelApplication._check_idle_and_fullscreen)
        assert "import ctypes.wintypes" in source, (
            "_check_idle_and_fullscreen 使用了 ctypes.wintypes.RECT()，"
            "必须显式 import ctypes.wintypes（子模块不会随 import ctypes 自动可用）"
        )

    def test_wintypes_rect_usable(self):
        """导入后 RECT 可构造，验证导入方式本身正确。"""
        import ctypes
        import ctypes.wintypes

        rect = ctypes.wintypes.RECT()
        assert rect.right == 0
        assert rect.bottom == 0


class TestChatStreamCallSite:
    """V0013 的旁证：调用点与流式接口签名必须继续匹配。

    真正的参数透传断言在 ``tests/unit/test_llm_service.py::TestGenerateStreamSignature``；
    这里检查 ``chat_manager`` 仍在用 ``memories=`` 关键字 —— 若哪一侧改成位置参数
    或删掉该关键字，两处会再次不一致。
    """

    def test_chat_manager_passes_memories_keyword(self):
        from modules.chat import chat_manager as chat_module

        source = inspect.getsource(chat_module.ChatManager._stream_generate)
        assert "memories=memories" in source


class TestFullscreenDetection:
    """V0015：全屏判定逻辑。

    该函数此前连续踩过三个坑（``ctypes.wintypes`` 未导入 → 误用
    ``QApplication.winId()`` → 未防 ``_floating_pet`` 为 ``None``），根因是整段
    逻辑耦合了 Win32 API、无法被单测覆盖，只能靠真机日志一个个发现。
    现把判定抽成模块级纯函数 ``should_report_fullscreen`` 以便真正覆盖。
    """

    def test_own_window_is_not_fullscreen(self):
        """桌宠自身窗口不能算全屏，否则一切都前台就会自己沉底消失。"""
        assert main.should_report_fullscreen(
            foreground_hwnd=100, own_hwnd=100,
            fg_width=1920, fg_height=1080,
            screen_width=1920, screen_height=1080,
        ) is False

    def test_no_foreground_window(self):
        """无前台窗口（hwnd=0）时不应判定为全屏。"""
        assert main.should_report_fullscreen(0, 100, 1920, 1080, 1920, 1080) is False

    def test_zero_screen_size_guarded(self):
        """屏幕尺寸异常时保守返回 False，避免除零/误判。"""
        assert main.should_report_fullscreen(100, 0, 100, 100, 0, 0) is False

    def test_exact_threshold_counts_as_fullscreen(self):
        """恰好达到 95%（1920×0.95=1824, 1080×0.95=1026）应算全屏。"""
        assert main.should_report_fullscreen(100, 200, 1824, 1026, 1920, 1080) is True

    def test_below_threshold_is_not_fullscreen(self):
        """宽度差 4px 未达阈值即不算全屏。"""
        assert main.should_report_fullscreen(100, 200, 1820, 1026, 1920, 1080) is False

    def test_width_alone_is_not_enough(self):
        """只有宽度达标、高度不足时不算全屏。"""
        assert main.should_report_fullscreen(100, 200, 1920, 900, 1920, 1080) is False

    def test_uses_pet_window_handle(self):
        """必须取桌宠窗口的 winId，而非 QApplication（后者没有该方法）。"""
        source = inspect.getsource(main.VelApplication._check_idle_and_fullscreen)
        assert "self.winId()" not in source, (
            "VelApplication 继承自 QApplication，没有 winId()；应使用 self._floating_pet.winId()"
        )
        assert "self._floating_pet.winId()" in source
        assert "self._floating_pet is not None" in source, (
            "self._floating_pet 初始化为 None，必须判空后再使用"
        )
