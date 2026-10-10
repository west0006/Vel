"""
首次引导向导模块。

扁平极简风格，圆点步骤指示器，600x450。
"""

from typing import Any, Dict, List

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
    QSlider, QVBoxLayout, QWidget,
)

from core.service_registry import registry
from modules.personality.profile_manager import ProfileManager
from ui.theme import Colors, Fonts, Sizes, get_button_style
from utils.logger import get_logger

logger = get_logger(__name__)


class WizardStep(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Dict[str, Any] = {}
    def get_data(self) -> Dict[str, Any]:
        return self._data
    def validate(self) -> bool:
        return True


class WelcomeStep(WizardStep):
    def __init__(self, parent=None):
        super().__init__(parent)
        l = QVBoxLayout(self); l.setAlignment(Qt.AlignCenter); l.setSpacing(16)
        cat = QLabel("🐱"); cat.setAlignment(Qt.AlignCenter); cat.setStyleSheet("font-size: 56px;")
        l.addWidget(cat)
        wl = QLabel("欢迎来到 Vel 的世界！")
        wl.setAlignment(Qt.AlignCenter)
        wl.setStyleSheet(f"{Fonts.style(Fonts.SIZE_XL, True)} color: {Colors.ACCENT};")
        l.addWidget(wl)
        d = QLabel("我是你的桌面猫咪伙伴~\n陪你聊天、提醒喝水、帮你记日程\n所有数据都在你的电脑上 🔒")
        d.setAlignment(Qt.AlignCenter); d.setWordWrap(True)
        d.setStyleSheet(f"{Fonts.style(Fonts.SIZE_MD)} color: {Colors.TEXT_SECONDARY};")
        l.addWidget(d)
        self._data["step"] = 1


class ProfileStep(WizardStep):
    def __init__(self, parent=None):
        super().__init__(parent)
        l = QVBoxLayout(self); l.setSpacing(12); l.setContentsMargins(40, 16, 40, 16)

        l.addWidget(QLabel("👤 让我了解一下你"))
        l.addWidget(QLabel("昵称"))
        self._nick = QLineEdit()
        self._nick.setPlaceholderText("输入昵称（跳过则叫\"用户\"）")
        self._nick.setStyleSheet(f"""
            QLineEdit {{ border:1px solid {Colors.BORDER}; border-radius:8px;
            padding:8px 12px; font:normal {Fonts.SIZE_MD}px '{Fonts.FAMILY}'; }}
            QLineEdit:focus {{ border:2px solid {Colors.BORDER_FOCUS}; }}
        """)
        l.addWidget(self._nick)

        l.addWidget(QLabel("饮食偏好（可多选）"))
        pl = QHBoxLayout(); pl.setSpacing(10); self._pfs = {}
        for lb, v in [("🌶 辣","辣"),("🥗 清淡","清淡"),("🍝 西式","西式"),("🍣 日料","日料"),("🍰 甜食","甜食")]:
            cb = QCheckBox(lb); self._pfs[v]=cb; pl.addWidget(cb)
        pl.addStretch(); l.addLayout(pl)

        l.addWidget(QLabel("忌口"))
        self._restr = QLineEdit(); self._restr.setPlaceholderText("如：不吃香菜")
        self._restr.setStyleSheet(self._nick.styleSheet()); l.addWidget(self._restr)

        l.addWidget(QLabel("作息类型"))
        cl = QHBoxLayout(); cl.setSpacing(10); self._cg = QButtonGroup(self); self._crs = {}
        for lb, v in [("🌅 早起鸟","early"),("🌙 夜猫子","night"),("🤷 不规律","irregular")]:
            rb = QRadioButton(lb); self._cg.addButton(rb); self._crs[v]=rb; cl.addWidget(rb)
        cl.addStretch(); l.addLayout(cl); self._crs["irregular"].setChecked(True)
        l.addStretch()

    def get_data(self) -> Dict[str, Any]:
        return {
            "step":2,
            "nickname": self._nick.text().strip() or "用户",
            "favorite_foods": [v for v,cb in self._pfs.items() if cb.isChecked()],
            "dietary_restrictions": self._restr.text().strip(),
            "chronotype": next((v for v,rb in self._crs.items() if rb.isChecked()),"irregular"),
        }


class TryChatStep(WizardStep):
    def __init__(self, parent=None):
        super().__init__(parent)
        l = QVBoxLayout(self); l.setSpacing(10); l.setContentsMargins(40,16,40,16)
        l.addWidget(QLabel("💬 试试和我聊天"))
        l.addWidget(QLabel("尝试输入：\"提醒我10分钟后喝水\""))
        il = QHBoxLayout()
        self._inp = QLineEdit(); self._inp.setPlaceholderText("在这里输入...")
        self._inp.setStyleSheet(f"border:1px solid {Colors.BORDER}; border-radius:8px; padding:8px;")
        il.addWidget(self._inp)
        sb = QPushButton("发送"); sb.setFixedSize(56,34)
        sb.setStyleSheet(get_button_style("primary", Fonts.SIZE_SM))
        sb.clicked.connect(self._on_send); il.addWidget(sb)
        l.addLayout(il)
        self._fb = QLabel(""); self._fb.setAlignment(Qt.AlignCenter)
        self._fb.setStyleSheet(f"{Fonts.style(Fonts.SIZE_MD)} color: {Colors.SUCCESS};")
        self._fb.setWordWrap(True); l.addWidget(self._fb)
        l.addWidget(QLabel("所有提醒都不会发出声音打扰你 ✨"))
        l.addStretch()

    def _on_send(self) -> None:
        t = self._inp.text().strip()
        if not t: return
        if "提醒" in t:
            self._fb.setText("✅ 收到！我会在10分钟后提醒你～喵~")
        else:
            self._fb.setText(f"✅ 收到：「{t[:20]}」")
        self._inp.clear()


class HealthSettingsStep(WizardStep):
    def __init__(self, parent=None):
        super().__init__(parent)
        l = QVBoxLayout(self); l.setSpacing(12); l.setContentsMargins(40,16,40,16)
        l.addWidget(QLabel("❤️ 健康提醒设置"))
        l.addWidget(QLabel("久坐提醒（分钟）"))
        self._sed = QSlider(Qt.Horizontal); self._sed.setRange(30,90); self._sed.setValue(50)
        self._sed_lb = QLabel("50 分钟"); self._sed.valueChanged.connect(lambda v: self._sed_lb.setText(f"{v} 分钟"))
        l.addWidget(self._sed); l.addWidget(self._sed_lb)
        l.addWidget(QLabel("饮水提醒（分钟）"))
        self._drk = QSlider(Qt.Horizontal); self._drk.setRange(30,60); self._drk.setValue(45)
        self._drk_lb = QLabel("45 分钟"); self._drk.valueChanged.connect(lambda v: self._drk_lb.setText(f"{v} 分钟"))
        l.addWidget(self._drk); l.addWidget(self._drk_lb)
        self._sk = QCheckBox("暂时跳过"); l.addWidget(self._sk); l.addStretch()

    def get_data(self) -> Dict[str, Any]:
        if self._sk.isChecked(): return {"step":4,"skip_health":True}
        return {"step":4,"sedentary_threshold_min":self._sed.value(),"drink_interval_min":self._drk.value(),"skip_health":False}


class FinishStep(WizardStep):
    def __init__(self, parent=None):
        super().__init__(parent)
        l = QVBoxLayout(self); l.setAlignment(Qt.AlignCenter); l.setSpacing(12)
        l.addWidget(QLabel("🐱", alignment=Qt.AlignCenter, styleSheet="font-size:56px;"))
        l.addWidget(QLabel("都设置好啦！🎉", alignment=Qt.AlignCenter,
                     styleSheet=f"{Fonts.style(Fonts.SIZE_XL,True)} color:{Colors.ACCENT};"))
        l.addWidget(QLabel("我平时会在右下角打瞌睡~\n想我了就点我一下 💬\n所有数据都在你的电脑上 🔐",
                     alignment=Qt.AlignCenter, wordWrap=True,
                     styleSheet=f"{Fonts.style(Fonts.SIZE_MD)} color:{Colors.TEXT_SECONDARY};"))
        self._data["step"] = 5


class OnboardingWizard(QDialog):
    wizard_finished = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vel - 欢迎向导")
        self.setFixedSize(600, 450)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setStyleSheet(f"background-color:{Colors.BG_MAIN};")

        s = QApplication.primaryScreen().geometry()
        self.move((s.width()-600)//2, (s.height()-450)//2)

        self._steps: List[WizardStep] = [
            WelcomeStep(), ProfileStep(), TryChatStep(), HealthSettingsStep(), FinishStep()
        ]
        self._step_index = 0

        main_l = QVBoxLayout(self)
        main_l.setContentsMargins(0,0,0,0)
        main_l.setSpacing(0)

        # 圆点指示器
        dots_l = QHBoxLayout()
        dots_l.setAlignment(Qt.AlignCenter)
        dots_l.setContentsMargins(0, 16, 0, 8)
        self._dots: List[QLabel] = []
        for i in range(5):
            d = QLabel("●")
            d.setAlignment(Qt.AlignCenter)
            d.setFixedSize(24, 24)
            d.setStyleSheet(f"font-size:10px; color:{Colors.BORDER};")
            dots_l.addWidget(d)
            self._dots.append(d)
        main_l.addLayout(dots_l)

        # 步骤内容
        self._content = QVBoxLayout()
        self._content.setContentsMargins(0, 0, 0, 0)
        main_l.addLayout(self._content, stretch=1)

        # 底部导航
        nav = QFrame()
        nav.setFixedHeight(56)
        nav.setStyleSheet(f"background:{Colors.BG_CARD}; border-top:1px solid {Colors.BORDER};")
        nl = QHBoxLayout(nav); nl.setContentsMargins(20,10,20,10)

        self._prev = QPushButton("上一步")
        self._prev.setFixedSize(80, 32)
        self._prev.setStyleSheet(get_button_style("secondary", Fonts.SIZE_SM))
        self._prev.clicked.connect(self._prev_step)
        nl.addWidget(self._prev)

        nl.addStretch()

        self._skip = QPushButton("跳过")
        self._skip.setStyleSheet(get_button_style("text", Fonts.SIZE_SM))
        self._skip.clicked.connect(self._next_step)
        nl.addWidget(self._skip)

        self._next = QPushButton("下一步 →")
        self._next.setStyleSheet(get_button_style("primary", Fonts.SIZE_SM))
        self._next.clicked.connect(self._next_step)
        nl.addWidget(self._next)

        main_l.addWidget(nav)
        self._render_step()

    def _render_step(self) -> None:
        # 清空内容
        for i in reversed(range(self._content.count())):
            w = self._content.itemAt(i).widget()
            if w: w.hide(); self._content.removeWidget(w)

        # 显示当前步骤
        self._content.addWidget(self._steps[self._step_index])
        self._steps[self._step_index].show()

        # 更新圆点
        for i, d in enumerate(self._dots):
            if i < self._step_index:
                d.setStyleSheet(f"font-size:10px; color:{Colors.BORDER};")
            elif i == self._step_index:
                d.setStyleSheet(f"font-size:10px; color:{Colors.ACCENT}; font-weight:bold;")
            else:
                d.setStyleSheet(f"font-size:10px; color:{Colors.TEXT_PLACEHOLDER};")

        self._prev.setVisible(self._step_index > 0)
        if self._step_index == len(self._steps) - 1:
            self._next.setText("🎉 开始使用")
            self._skip.setVisible(False)
        else:
            self._next.setText("下一步 →")
            self._skip.setVisible(True)

    def _prev_step(self) -> None:
        if self._step_index > 0:
            self._step_index -= 1
            self._render_step()

    def _next_step(self) -> None:
        if self._step_index < len(self._steps) - 1:
            self._step_index += 1
            self._render_step()
        else:
            self._finish()

    def _finish(self) -> None:
        import json
        all_data: Dict[str, Any] = {}
        for s in self._steps:
            all_data.update(s.get_data())

        logger.info(f"引导向导完成: {all_data.get('nickname','用户')}")

        pm = ProfileManager()
        if all_data.get("nickname"):
            pm.set_profile("nickname", all_data["nickname"])
        if all_data.get("favorite_foods"):
            pm.set_profile("favorite_foods", json.dumps(all_data["favorite_foods"], ensure_ascii=False))
        if all_data.get("dietary_restrictions"):
            pm.set_profile("dietary_restrictions", all_data["dietary_restrictions"])
        if all_data.get("chronotype"):
            pm.set_profile("chronotype", all_data["chronotype"])

        if not all_data.get("skip_health"):
            try:
                db = registry.get("database")
                if db:
                    for k in ("sedentary_threshold_min","drink_interval_min"):
                        if all_data.get(k):
                            db.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)",
                                       (k, str(all_data[k])))
                    db.commit()
            except Exception:
                logger.exception("_finish 执行失败")

        self.wizard_finished.emit(all_data)
        self.accept()

    @staticmethod
    def check_first_run() -> bool:
        try:
            db = registry.get("database")
            if not db: return True
            return not db.execute("SELECT key FROM user_profile WHERE key='nickname'").fetchone()
        except Exception:
            return True
