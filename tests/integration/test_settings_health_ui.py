"""健康页滑块数值标签的 UI 冒烟测试（offscreen）。

只构建健康页，不实例化整个设置窗口；用 stub 提供页面容器与配置读取。
"""

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from ui.settings_window import SettingsWindow


def test_health_page_shows_and_updates_slider_values(qt_app):
    window = SettingsWindow.__new__(SettingsWindow)
    window._page_wrap = lambda: (QVBoxLayout(), QWidget())
    window._get_int = lambda key, default: default
    window._refresh_health_stats = lambda: None

    page = SettingsWindow._page_health(window)

    assert page is not None
    assert window._sed_value_label.text() == "50 分钟"
    assert window._drk_value_label.text() == "45 分钟"

    window._sed_slider.setValue(60)
    assert window._sed_value_label.text() == "60 分钟"

    window._drk_slider.setValue(30)
    assert window._drk_value_label.text() == "30 分钟"
