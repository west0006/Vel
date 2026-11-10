"""健康页滑块数值标签测试。

用轻量假对象调用绑定方法，不创建 QApplication / QWidget。
"""

from ui import settings_window


class _FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


class _FakeSlider:
    def __init__(self, value):
        self._value = value
        self.valueChanged = _FakeSignal()

    def value(self):
        return self._value

    def set_value(self, value):
        self._value = value


class _FakeLabel:
    def __init__(self):
        self.text = ""
        self.style = ""

    def setText(self, text):
        self.text = text

    def setStyleSheet(self, style):
        self.style = style


def test_initial_value_is_shown():
    slider = _FakeSlider(50)
    label = _FakeLabel()

    settings_window.SettingsWindow._bind_slider_value_label(
        slider, label, "分钟"
    )

    assert label.text == "50 分钟"
    assert label.style, "数值标签应套用统一的小字号样式"


def test_value_change_updates_label():
    slider = _FakeSlider(45)
    label = _FakeLabel()
    settings_window.SettingsWindow._bind_slider_value_label(
        slider, label, "分钟"
    )

    slider.set_value(60)
    slider.valueChanged.slots[0](60)

    assert label.text == "60 分钟"
