"""设置页「清除本轮」的 UI 行为测试。

只调用未绑定的方法，用轻量 stub 代替 QWidget / 真实通知气泡，
不创建 QApplication，也不弹真实消息框。
"""

from ui import settings_window


class _FakeChatManager:
    def __init__(self):
        self.cleared = 0

    def clear_context(self):
        self.cleared += 1


class _FakeChatBubble:
    def __init__(self):
        self.cleared = 0

    def clear_messages(self):
        self.cleared += 1


class _StubWindow:
    def __init__(self):
        self.refreshed = 0

    def _refresh_chat(self):
        self.refreshed += 1


def test_clear_context_clears_bubble_and_shows_feedback(monkeypatch):
    cm = _FakeChatManager()
    bubble = _FakeChatBubble()
    services = {"chat_manager": cm, "chat_bubble": bubble}
    monkeypatch.setattr(
        settings_window.registry,
        "get",
        lambda name, default=None: services.get(name, default),
    )

    feedback = []
    monkeypatch.setattr(
        settings_window.QMessageBox,
        "information",
        lambda *args, **kwargs: feedback.append(args),
    )

    stub = _StubWindow()
    settings_window.SettingsWindow._clear_context(stub)

    assert cm.cleared == 1
    assert bubble.cleared == 1
    assert stub.refreshed == 1
    assert feedback, "清除后必须给用户明确反馈"
    assert "历史存档仍保留" in feedback[0][2]


def test_clear_context_without_manager_warns(monkeypatch):
    monkeypatch.setattr(
        settings_window.registry, "get", lambda name, default=None: default
    )
    warnings = []
    monkeypatch.setattr(
        settings_window.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )

    stub = _StubWindow()
    settings_window.SettingsWindow._clear_context(stub)

    assert warnings
    assert stub.refreshed == 0
