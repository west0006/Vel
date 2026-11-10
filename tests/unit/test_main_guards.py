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
