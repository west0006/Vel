"""
主题模块。扁平暖橙风格，Feather SVG 图标系统。
"""

import os
from typing import Dict, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush
from PyQt5.QtSvg import QSvgRenderer

from utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 配色
# ============================================================

class Colors:
    BG_MAIN = "#FFFBF5"
    BG_CARD = "#FAFAFA"
    TEXT_PRIMARY = "#2C2C2C"
    TEXT_SECONDARY = "#4A4A4A"
    TEXT_PLACEHOLDER = "#8A8A8A"
    BORDER = "#E8E4E0"
    BORDER_FOCUS = "#FF6B35"
    NAV_BG = "#FAFAFA"
    NAV_ACTIVE = "#FFF2ED"

    ACCENT = "#FF6B35"
    ACCENT_HOVER = "#E55A2B"
    ACCENT_PRESSED = "#CC4F26"

    DANGER = "#D32F2F"
    DANGER_HOVER = "#B71C1C"
    SUCCESS = "#2E7D32"

    BG_USER_BUBBLE = "#EDEDED"
    BG_PET_BUBBLE = "#FFFFFF"
    PET_BUBBLE_BORDER = "#FF6B35"

    TRAY_ICON = "#FF6B35"
    TRAY_ICON_DIM = "#CCCCCC"


# ============================================================
# 字体
# ============================================================

class Fonts:
    FAMILY = "Microsoft YaHei UI"
    FAMILY_CUSTOM = "MaokenAssortedSans"  # 项目自带字体，优先使用
    FAMILY_MONO = "Consolas"

    SIZE_XS = 12
    SIZE_SM = 13
    SIZE_MD = 14
    SIZE_LG = 16
    SIZE_XL = 20
    SIZE_XXL = 24

    CHAT_MSG = 15       # 对话气泡字号
    CHAT_INPUT = 14     # 输入框字号
    CHAT_TITLE = 15     # 标题栏

    @staticmethod
    def style(size: int = SIZE_MD, weight: int = 400) -> str:
        return f"font: {weight} {size}px '{Fonts.FAMILY_CUSTOM}', '{Fonts.FAMILY}';"

    @staticmethod
    def mono(size: int = SIZE_SM) -> str:
        return f"font: 400 {size}px '{Fonts.FAMILY_MONO}';"


# ============================================================
# 动画
# ============================================================

class PetAnimation:
    IDLE = "idle"
    HAPPY = "happy"
    SAD = "sad"
    SLEEPY = "sleepy"
    TALKING = "talking"
    STRETCH = "stretch"

    FRAME_INTERVAL_MS = {IDLE: 2000, HAPPY: 500, SAD: 1500,
                         SLEEPY: 3000, TALKING: 800, STRETCH: 1000}
    ANIMATION_DURATION = {IDLE: 0, HAPPY: 3000, SAD: 4000,
                          SLEEPY: 0, TALKING: 0, STRETCH: 5000}
    EMOTION_TIP = {HAPPY: "Vel 很开心~", SAD: "Vel 有点难过...",
                   SLEEPY: "Vel 在打瞌睡~", TALKING: "Vel 在听你说话~",
                   STRETCH: "Vel 伸了个懒腰~"}


# ============================================================
# 尺寸
# ============================================================

class Sizes:
    PET_WINDOW_DEFAULT = 250
    PET_WINDOW_MIN = 200
    PET_WINDOW_MAX = 350

    CHAT_BUBBLE_WIDTH = 360
    CHAT_BUBBLE_HEIGHT = 460
    CHAT_BUBBLE_MIN_W = 300
    CHAT_BUBBLE_MIN_H = 320
    CHAT_BUBBLE_MAX_W = 540
    CHAT_BUBBLE_MAX_H = 660
    CHAT_BUBBLE_TAIL = 10
    CHAT_BUBBLE_RADIUS = 12
    CHAT_MSG_MAX_W = 260
    CHAT_RESIZE = 10

    NOTIFICATION_WIDTH = 300
    NOTIFICATION_RADIUS = 10

    SETTINGS_WIDTH = 700
    SETTINGS_HEIGHT = 500
    NAV_WIDTH = 150

    BUTTON_RADIUS = 8
    CARD_RADIUS = 12
    INPUT_RADIUS = 8
    PANEL_RADIUS = 12
    MIN_CLICK = 32


# ============================================================
# QSS 片段
# ============================================================

class Styles:
    INPUT = f"""
        QLineEdit {{
            border: 1px solid {Colors.BORDER};
            border-radius: {Sizes.INPUT_RADIUS}px;
            padding: 8px 12px;
            font: 400 {Fonts.CHAT_INPUT}px '{Fonts.FAMILY_CUSTOM}', '{Fonts.FAMILY}';
            background: {Colors.BG_MAIN}; color: {Colors.TEXT_PRIMARY};
        }}
        QLineEdit:focus {{ border: 2px solid {Colors.BORDER_FOCUS}; }}
    """

    SCROLL_AREA = f"""
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ width: 6px; background: transparent; }}
        QScrollBar::handle:vertical {{
            background: {Colors.BORDER}; border-radius: 3px; min-height: 24px;
        }}
    """

    PROGRESS_BAR = f"""
        QProgressBar {{
            border: 1px solid {Colors.BORDER}; border-radius: 4px;
            text-align: center; font: 600 {Fonts.SIZE_XS}px '{Fonts.FAMILY_CUSTOM}', '{Fonts.FAMILY}';
            color: {Colors.TEXT_PRIMARY}; background: {Colors.BG_MAIN}; height: 22px;
        }}
        QProgressBar::chunk {{ background-color: {Colors.ACCENT}; border-radius: 3px; }}
    """

    LIST_WIDGET = f"""
        QListWidget {{
            border: 1px solid {Colors.BORDER};
            border-radius: {Sizes.CARD_RADIUS}px;
            background: {Colors.BG_MAIN}; padding: 4px;
        }}
        QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
        QListWidget::item:hover {{ background: {Colors.BG_CARD}; }}
    """

    TRAY_TOOLTIP = "Vel - 智能AI桌宠"


# ============================================================
# 按钮工厂
# ============================================================

def get_button_style(variant: str = "primary", size: int = Fonts.SIZE_SM,
                     fixed_width: int = 0) -> str:
    base = f"""
        QPushButton {{
            border-radius: {Sizes.BUTTON_RADIUS}px;
            padding: 6px 16px;
            font: 600 {size}px '{Fonts.FAMILY_CUSTOM}', '{Fonts.FAMILY}';
            {'min-width:' + str(fixed_width) + 'px;' if fixed_width else ''}
        }}
    """
    if variant == "primary":
        return base + f"""
            QPushButton {{ background: {Colors.ACCENT}; color: {Colors.BG_MAIN}; border: none; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
            QPushButton:pressed {{ background: {Colors.ACCENT_PRESSED}; }}
            QPushButton:disabled {{ opacity: 0.4; }}
        """
    elif variant == "secondary":
        return base + f"""
            QPushButton {{ background: {Colors.BG_MAIN}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; }}
            QPushButton:hover {{ background: {Colors.BG_CARD}; }}
            QPushButton:pressed {{ background: #F0F0F0; }}
            QPushButton:disabled {{ opacity: 0.4; }}
        """
    elif variant == "text":
        return base + f"""
            QPushButton {{ background: transparent; border: none; color: {Colors.TEXT_SECONDARY}; }}
            QPushButton:hover {{ background: {Colors.BG_CARD}; }}
        """
    elif variant == "danger":
        return base + f"""
            QPushButton {{ background: {Colors.DANGER}; color: {Colors.BG_MAIN}; border: none; }}
            QPushButton:hover {{ background: {Colors.DANGER_HOVER}; }}
        """
    return base


# ============================================================
# 图标系统
# ============================================================

ICON_MAP: Dict[str, str] = {
    "chat": "message-circle", "schedule": "calendar",
    "health": "heart", "appearance": "palette",
    "update": "refresh-cw", "data": "database",
    "settings": "settings", "exit": "log-out",
    "about": "info","profile": "user",
    "drink": "droplet", "meal": "utensils",
    "rest": "coffee", "mood": "smile",
    "search": "search", "reminder": "bell",
    "memo": "memo", "habit": "habit",
    "quiet": "bell-off", "pause_all": "pause-circle",
    "success": "check-circle", "warning": "alert-triangle",
    "error": "x-circle", "loading": "loader",
}

_ICON_CACHE: Dict[str, QIcon] = {}


def _svg_to_pixmap(svg_path: str, size: int, color: str = Colors.ACCENT) -> QPixmap:
    """将 SVG 渲染为 QPixmap，自动替换描边颜色。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)

    if not os.path.exists(svg_path):
        return pix

    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            svg_content = f.read()
        # 替换描边颜色
        svg_content = svg_content.replace('stroke="#FF6B35"', f'stroke="{color}"')
        svg_content = svg_content.replace('fill="#FF6B35"', f'fill="{color}"')

        renderer = QSvgRenderer(bytearray(svg_content, "utf-8"))
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
    except Exception:
        logger.exception("load_icon 渲染 SVG 失败")

    return pix


def load_icon(name: str, size: int = 20, color: str = Colors.ACCENT) -> QIcon:
    """加载图标。SVG → 纯色圆形回退。

    Args:
        name: ICON_MAP 的键名
        size: 图标尺寸
        color: 描边颜色

    Returns:
        QIcon
    """
    cache_key = f"{name}_{size}_{color}"
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    svg_name = ICON_MAP.get(name, "circle")
    base = os.path.dirname(__file__)
    svg_path = os.path.join(base, "resources", "icons", f"{svg_name}.svg")

    if os.path.exists(svg_path):
        pix = _svg_to_pixmap(svg_path, size, color)
    else:
        # 回退：纯色圆形 + 首字母
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)

        # 纯色圆
        painter.setBrush(QBrush(QColor(color)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, size - 4, size - 4)

        # 首字母
        initial = name[0].upper() if name else "?"
        painter.setPen(QPen(QColor(Colors.BG_MAIN)))
        font = QFont(Fonts.FAMILY, size // 2 - 2)
        font.setWeight(600)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignCenter, initial)

        painter.end()

    icon = QIcon(pix)
    _ICON_CACHE[cache_key] = icon
    return icon


def get_nav_icon(name: str, active: bool = False, size: int = 20) -> QIcon:
    """获取导航图标（active 时用强调色，否则用灰色）。"""
    color = Colors.ACCENT if active else Colors.TEXT_SECONDARY
    return load_icon(name, size, color)