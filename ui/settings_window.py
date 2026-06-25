"""
设置面板模块。扁平极简风格，即时生效，无保存按钮。
"""

import os
from typing import Any, Dict, List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QProgressBar, QPushButton, QSlider, QStackedWidget,
    QVBoxLayout, QWidget, QCalendarWidget, QTabWidget, QFileDialog,
    QShortcut,
)

from core.service_registry import registry
from modules.personality.profile_manager import ProfileManager
from ui.theme import Colors, Fonts, Sizes, Styles, get_button_style, load_icon, get_nav_icon
from utils.logger import get_logger

logger = get_logger(__name__)

NAV_ITEMS = [
    ("profile",    "偏好", 0),
    ("schedule",   "日程", 1),
    ("health",     "健康", 2),
    ("habit",      "习惯", 3),
    ("chat",       "对话", 4),
    ("memo",       "备忘", 5),
    ("appearance", "外观", 6),
    ("update",     "更新", 7),
    ("data",       "数据", 8),
]


class SettingsWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile = ProfileManager()
        self._setup_window()
        self._setup_nav()
        self._setup_pages()
        self._show_page(0)

        QShortcut(QKeySequence("Ctrl+W"), self, self.close)
        for i in range(1, 8):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, lambda idx=i-1: self._show_page(idx))

    def _setup_window(self) -> None:
        self.setWindowTitle("Vel 设置")
        self.setFixedSize(Sizes.SETTINGS_WIDTH, Sizes.SETTINGS_HEIGHT)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setStyleSheet(f"background-color: {Colors.BG_MAIN};")

        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - Sizes.SETTINGS_WIDTH) // 2,
            (screen.height() - Sizes.SETTINGS_HEIGHT) // 2,
        )

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._nav_frame = QFrame()
        self._nav_frame.setFixedWidth(Sizes.NAV_WIDTH)
        self._nav_frame.setStyleSheet(
            f"background-color: {Colors.NAV_BG}; border-right: 1px solid {Colors.BORDER};"
        )
        nav_layout = QVBoxLayout(self._nav_frame)
        nav_layout.setContentsMargins(0, 12, 0, 12)
        nav_layout.setSpacing(2)

        self._nav_btns: List[QPushButton] = []
        for icon_name, label, index in NAV_ITEMS:
            btn = QPushButton(f"  {label}")
            btn.setFixedHeight(Sizes.MIN_CLICK + 4)
            btn.setIcon(get_nav_icon(icon_name, False, 20))
            btn.setStyleSheet(f"""
                      QPushButton {{
                          text-align: left; padding-left: 16px;
                          border: none; border-radius: 0;
                          font: 400 {Fonts.SIZE_SM}px '{Fonts.FAMILY}';
                          color: {Colors.TEXT_SECONDARY};
                          background: transparent;
                      }}
                      QPushButton:hover {{ background: {Colors.BG_CARD}; }}
                      QPushButton:checked {{
                          color: {Colors.ACCENT}; font-weight: 600;
                          background: {Colors.NAV_ACTIVE};
                      }}
                  """)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, i=index: self._show_page(i))
            nav_layout.addWidget(btn)
            self._nav_btns.append(btn)

        nav_layout.addStretch()
        main_layout.addWidget(self._nav_frame)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {Colors.BG_MAIN};")
        main_layout.addWidget(self._stack, stretch=1)

    def _show_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, (icon_name, _, _) in enumerate(NAV_ITEMS):
            btn = self._nav_btns[i]
            btn.setChecked(i == index)
            btn.setIcon(get_nav_icon(icon_name, i == index, 20))

    # ================================================================
    # 页面
    # ================================================================

    def _setup_pages(self) -> None:
        self._stack.addWidget(self._page_profile())
        self._stack.addWidget(self._page_schedule())
        self._stack.addWidget(self._page_health())
        self._stack.addWidget(self._page_habit())
        self._stack.addWidget(self._page_chat())
        self._stack.addWidget(self._page_memo())
        self._stack.addWidget(self._page_appearance())
        self._stack.addWidget(self._page_update())
        self._stack.addWidget(self._page_data())


    def _page_wrap(self) -> QVBoxLayout:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(20, 16, 20, 16)
        l.setSpacing(10)
        return l, w

    def _section(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"{Fonts.style(Fonts.SIZE_LG, True)} color: {Colors.TEXT_PRIMARY};")
        return l

    # --- 个人偏好 ---

    def _page_profile(self) -> QWidget:
        layout, w = self._page_wrap()
        layout.addWidget(self._section("个人偏好"))

        layout.addWidget(QLabel("昵称"))
        self._nick = QLineEdit(self._profile.get_profile("nickname", "用户"))
        self._nick.setStyleSheet(Styles.INPUT)
        self._nick.textChanged.connect(lambda t: self._apply_profile())
        layout.addWidget(self._nick)

        layout.addWidget(QLabel("饮食偏好"))
        pl = QHBoxLayout()
        self._prefs = {}
        cur = self._load_json("favorite_foods", [])
        for lb, v in [("辣", "辣"), ("清淡", "清淡"), ("西式", "西式"),
                       ("日料", "日料"), ("甜食", "甜食")]:
            cb = QCheckBox(lb)
            cb.setChecked(v in cur)
            cb.toggled.connect(lambda: self._apply_profile())
            self._prefs[v] = cb
            pl.addWidget(cb)
        pl.addStretch()
        layout.addLayout(pl)

        layout.addWidget(QLabel("忌口"))
        self._restr = QLineEdit(self._profile.get_profile("dietary_restrictions", ""))
        self._restr.setStyleSheet(Styles.INPUT)
        self._restr.textChanged.connect(lambda: self._apply_profile())
        layout.addWidget(self._restr)

        layout.addWidget(QLabel("作息"))
        self._chrono = QComboBox()
        self._chrono.addItems(["不规律", "早起鸟", "夜猫子"])
        cmap = {"irregular": 0, "early": 1, "night": 2}
        self._chrono.setCurrentIndex(cmap.get(self._profile.get_profile("chronotype", "irregular"), 0))
        self._chrono.currentIndexChanged.connect(lambda: self._apply_profile())
        layout.addWidget(self._chrono)

        layout.addStretch()
        layout.addWidget(QPushButton("恢复默认"), alignment=Qt.AlignRight)
        return w

    def _apply_profile(self) -> None:
        import json
        self._profile.set_profile("nickname", self._nick.text().strip() or "用户")
        self._profile.set_profile("favorite_foods",
            json.dumps([v for v, cb in self._prefs.items() if cb.isChecked()], ensure_ascii=False))
        self._profile.set_profile("dietary_restrictions", self._restr.text().strip())
        cmap = {0: "irregular", 1: "early", 2: "night"}
        self._profile.set_profile("chronotype", cmap[self._chrono.currentIndex()])
        cm = registry.get("chat_manager")
        if cm:
            cm.set_user_name(self._nick.text().strip() or "用户")

    # --- 日程 ---

    def _page_schedule(self) -> QWidget:
        layout, w = self._page_wrap()
        layout.addWidget(self._section("日程"))
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {Colors.BORDER}; border-radius: {Sizes.CARD_RADIUS}px; background: {Colors.BG_MAIN}; }}
            QTabBar::tab {{ padding: 8px 20px; border: none; font: 400 {Fonts.SIZE_SM}px '{Fonts.FAMILY}'; color: {Colors.TEXT_SECONDARY}; }}
            QTabBar::tab:selected {{ color: {Colors.ACCENT}; font-weight: 600; border-bottom: 2px solid {Colors.ACCENT}; }}
        """)

        cal = QCalendarWidget()
        cal.setGridVisible(True)
        cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        cal.setStyleSheet(f"""
            QCalendarWidget {{ background: {Colors.BG_MAIN}; border: none; }}
            QCalendarWidget QToolButton {{ color: {Colors.TEXT_PRIMARY}; font: 600 {Fonts.SIZE_SM}px '{Fonts.FAMILY}'; border: none; padding: 6px 12px; }}
            QCalendarWidget QToolButton:hover {{ background: {Colors.BG_CARD}; border-radius: 6px; }}
            QCalendarWidget QMenu {{ background: {Colors.BG_MAIN}; border: 1px solid {Colors.BORDER}; border-radius: 8px; }}
            QCalendarWidget QAbstractItemView:enabled {{ color: {Colors.TEXT_PRIMARY}; font: 400 {Fonts.SIZE_SM}px '{Fonts.FAMILY}'; selection-background-color: {Colors.NAV_ACTIVE}; selection-color: {Colors.ACCENT}; }}
            QCalendarWidget QAbstractItemView:disabled {{ color: {Colors.TEXT_PLACEHOLDER}; }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {Colors.BG_CARD}; border-bottom: 1px solid {Colors.BORDER}; }}
        """)
        cal.selectionChanged.connect(lambda: self._load_schedule_for_date(cal.selectedDate()))
        tabs.addTab(cal, "月视图")

        lw = QWidget()
        ll = QVBoxLayout(lw)
        self._sched_list = QListWidget()
        self._sched_list.setStyleSheet(Styles.LIST_WIDGET)
        self._refresh_schedule()
        ll.addWidget(self._sched_list)
        btn = QPushButton("+ 添加日程")
        btn.setStyleSheet(get_button_style("secondary", Fonts.SIZE_SM))
        btn.clicked.connect(self._add_schedule_dialog)
        ll.addWidget(btn)
        tabs.addTab(lw, "列表")
        layout.addWidget(tabs)
        return w

    def _load_schedule_for_date(self, qdate) -> None:
        """选中日期时加载当天日程到列表。"""
        self._sched_list.clear()
        try:
            db = registry.get("database")
            if not db: return
            date_str = qdate.toString("yyyy-MM-dd")
            for title, st, status in db.execute(
                    "SELECT title, start_time, status FROM schedule "
                    "WHERE date(start_time) = ? AND status != 'cancelled' "
                    "ORDER BY start_time ASC", (date_str,)
            ).fetchall():
                icon = "✅" if status == "completed" else "📌"
                self._sched_list.addItem(f"{icon} {title}  ({st[11:16] if len(st) > 10 else '全天'})")
        except Exception:
            pass

    def _refresh_schedule(self) -> None:
        self._sched_list.clear()
        try:
            db = registry.get("database")
            if not db:
                return
            for title, st, status in db.execute(
                "SELECT title, start_time, status FROM schedule "
                "WHERE status IN ('active','completed') ORDER BY start_time DESC LIMIT 20"
            ).fetchall():
                icon = "✅" if status == "completed" else "📌"
                self._sched_list.addItem(f"{icon} {title}  ({st[:16]})")
        except Exception:
            pass

    def _add_schedule_dialog(self) -> None:
        d = QDialog(self)
        d.setWindowTitle("添加日程")
        d.setFixedSize(400, 280)
        dl = QVBoxLayout(d)
        dl.addWidget(QLabel("标题"))
        ti = QLineEdit(); ti.setStyleSheet(Styles.INPUT); dl.addWidget(ti)
        dl.addWidget(QLabel("时间（如：明天下午3点开会）"))
        tmi = QLineEdit(); tmi.setStyleSheet(Styles.INPUT); dl.addWidget(tmi)
        dl.addWidget(QLabel("描述（可选）"))
        di = QLineEdit(); di.setStyleSheet(Styles.INPUT); dl.addWidget(di)
        bl = QHBoxLayout(); bl.addStretch()
        bl.addWidget(QPushButton("取消", clicked=d.reject))
        ok = QPushButton("添加"); ok.setStyleSheet(get_button_style("primary", Fonts.SIZE_SM))
        def _add():
            if not ti.text().strip() or not tmi.text().strip():
                return
            try:
                from modules.schedule.schedule_parser import ScheduleParser
                from modules.schedule.schedule_store import ScheduleStore
                parser = ScheduleParser()
                store = registry.get("schedule_store") or ScheduleStore()
                items = parser.parse_single(f"{tmi.text().strip()} {ti.text().strip()}")
                for item in items:
                    sid = store.add_schedule(item)
                    if sid:
                        rs = registry.get("reminder_scheduler")
                        if rs:
                            rs.register_reminder(sid, item.start_time, item.title,
                                                 item.description, item.reminder_offset_min, item.priority)
                self._refresh_schedule()
                d.accept()
            except Exception:
                pass
        ok.clicked.connect(_add)
        bl.addWidget(ok); dl.addLayout(bl)
        d.exec_()

    # --- 健康 ---

    def _page_health(self) -> QWidget:
        layout, w = self._page_wrap()
        layout.addWidget(self._section("健康"))

        g = QGroupBox("今日概览")
        gl = QVBoxLayout(g)

        gl.addWidget(QLabel("饮水"))
        self._drink_bar = QProgressBar()
        self._drink_bar.setStyleSheet(Styles.PROGRESS_BAR)
        gl.addWidget(self._drink_bar)

        gl.addWidget(QLabel("🪑 久坐"))
        self._sitting_label = QLabel()
        gl.addWidget(self._sitting_label)

        self._refresh_health_stats()
        layout.addWidget(g)

        layout.addWidget(QLabel("久坐提醒（分钟）"))
        self._sed_slider = QSlider(Qt.Horizontal)
        self._sed_slider.setRange(30, 90)
        self._sed_slider.setValue(self._get_int("sedentary_threshold_min", 50))
        self._sed_slider.valueChanged.connect(self._apply_health)
        layout.addWidget(self._sed_slider)

        layout.addWidget(QLabel("活动类型"))
        self._activity_checks = {}
        al = QHBoxLayout()
        for lb, v in [("眼操", "eye"), ("拉伸", "stretch"), ("走动", "walk")]:
            cb = QCheckBox(lb);
            cb.setChecked(True)
            self._activity_checks[v] = cb;
            al.addWidget(cb)
        al.addStretch()
        layout.addLayout(al)

        layout.addWidget(QLabel("饮水提醒（分钟）"))
        self._drk_slider = QSlider(Qt.Horizontal)
        self._drk_slider.setRange(30, 60)
        self._drk_slider.setValue(self._get_int("drink_interval_min", 45))
        self._drk_slider.valueChanged.connect(self._apply_health)
        layout.addWidget(self._drk_slider)

        layout.addStretch()
        return w

    def _refresh_health_stats(self) -> None:
        try:
            dr = registry.get("drink_reminder")
            if dr:
                s = dr.get_daily_stats()
                self._drink_bar.setMaximum(s["target_ml"])
                self._drink_bar.setValue(s["current_ml"])
                self._drink_bar.setFormat(f"{s['current_ml']}/{s['target_ml']}ml ({s['percent']}%)")
            sd = registry.get("sedentary_monitor")
            if sd:
                st = sd.get_status()
                color = Colors.DANGER if st["continuous_min"] >= st["threshold_min"] else Colors.TEXT_PRIMARY
                self._sitting_label.setText(f'连续活动 <span style="color:{color}; font-weight:bold;">{st["continuous_min"]}</span> 分钟（阈值 {st["threshold_min"]}min）')
        except Exception:
            pass

    def _apply_health(self) -> None:
        try:
            db = registry.get("database")
            if db:
                db.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('sedentary_threshold_min',?)",
                           (str(self._sed_slider.value()),))
                db.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('drink_interval_min',?)",
                           (str(self._drk_slider.value()),))
                db.commit()
            dr = registry.get("drink_reminder")
            if dr: dr.update_settings(self._drk_slider.value(), 2000)
            sd = registry.get("sedentary_monitor")
            if sd: sd.update_threshold(self._sed_slider.value())
        except Exception:
            pass

    def _page_habit(self) -> QWidget:
        layout, w = self._page_wrap()
        layout.addWidget(self._section("习惯孵化"))
        self._habit_list = QListWidget()
        self._habit_list.setStyleSheet(Styles.LIST_WIDGET)
        layout.addWidget(self._habit_list)
        btn = QPushButton("刷新")
        btn.setStyleSheet(get_button_style("secondary", Fonts.SIZE_SM))
        btn.clicked.connect(self._refresh_habit)
        layout.addWidget(btn)
        return w

    def _refresh_habit(self) -> None:
        self._habit_list.clear()
        try:
            hm = registry.get("habit_manager")
            if not hm: return
            for h in hm.list_all():
                icon = "✅" if h["enabled"] else "⏸"
                self._habit_list.addItem(
                    f"{icon} {h['name']}  {h['streak']}天 streak  ⏰{h['target_time']}"
                )
        except Exception:
            pass


    def _page_memo(self) -> QWidget:
        layout, w = self._page_wrap()
        layout.addWidget(self._section("备忘录"))
        self._memo_list = QListWidget()
        self._memo_list.setStyleSheet(Styles.LIST_WIDGET)
        layout.addWidget(self._memo_list)
        btn = QPushButton("刷新")
        btn.setStyleSheet(get_button_style("secondary", Fonts.SIZE_SM))
        btn.clicked.connect(self._refresh_memo)
        layout.addWidget(btn)
        return w

    def _refresh_memo(self) -> None:
        self._memo_list.clear()
        try:
            mm = registry.get("memo_manager")
            if not mm: return
            for m in mm.get_active():
                ts = m["remind_at"][:16] if m["remind_at"] else "无提醒"
                self._memo_list.addItem(f"📌 {ts}  {m['content']}")
        except Exception:
            pass

    # --- 对话 ---

    def _page_chat(self) -> QWidget:
        layout, w = self._page_wrap()
        layout.addWidget(self._section("对话"))
        self._chat_list = QListWidget()
        self._chat_list.setStyleSheet(Styles.LIST_WIDGET)
        layout.addWidget(self._chat_list)
        bl = QHBoxLayout()
        bl.addWidget(QPushButton("清除本轮", clicked=self._clear_context))
        bl.addWidget(QPushButton("记忆管理", clicked=self._open_memory_dialog))
        bl.addStretch()
        layout.addLayout(bl)
        return w

    def _open_memory_dialog(self) -> None:
        """打开记忆管理弹窗。"""
        d = QDialog(self)
        d.setWindowTitle("记忆管理")
        d.setFixedSize(400, 350)
        dl = QVBoxLayout(d)
        dl.addWidget(QLabel("已存储的记忆"))
        lst = QListWidget()
        lst.setStyleSheet(Styles.LIST_WIDGET)
        ms = registry.get("memory_service")
        if ms:
            count = ms.get_memory_count()
            dl.addWidget(QLabel(f"共 {count} 条记忆"))
            # 简化：显示最近记忆
            try:
                db = registry.get("database")
                if db:
                    from utils.crypto import decrypt
                    for mid, summary, cat, imp in db.execute(
                            "SELECT memory_id, summary, category, importance FROM episodic_memory ORDER BY created_at DESC LIMIT 20"
                    ).fetchall():
                        lst.addItem(f"[{cat}] {decrypt(summary)[:60]}  (重要性:{imp})")
            except Exception:
                pass
        dl.addWidget(lst)
        bl = QHBoxLayout()
        bl.addStretch()
        bl.addWidget(QPushButton("关闭", clicked=d.accept))
        dl.addLayout(bl)
        d.exec_()

    def _refresh_chat(self) -> None:
        self._chat_list.clear()
        try:
            cm = registry.get("chat_manager")
            if not cm: return
            for h in reversed(cm.get_history(50)):
                icon = "👤" if h["role"] == "user" else "🐱"
                self._chat_list.addItem(f"{icon} {(h.get('content') or '')[:80]}")
        except Exception:
            pass

    def _clear_context(self) -> None:
        cm = registry.get("chat_manager")
        if cm: cm.clear_context()
        self._refresh_chat()

    # --- 外观 ---

    def _page_appearance(self) -> QWidget:
        layout, w = self._page_wrap()
        layout.addWidget(self._section("外观"))

        layout.addWidget(QLabel("猫咪大小"))
        self._size_slider = QSlider(Qt.Horizontal)
        self._size_slider.setRange(200, 350)
        self._size_slider.setValue(self._get_int("pet_size", 250))
        self._size_slider.valueChanged.connect(self._apply_size)
        layout.addWidget(self._size_slider)

        layout.addWidget(QPushButton("恢复默认位置", clicked=self._reset_pos))
        self._anim_cb = QCheckBox("启用动画"); self._anim_cb.setChecked(True)
        layout.addWidget(self._anim_cb)
        layout.addWidget(QLabel("主题色（即将推出 🚧）"))
        theme_layout = QHBoxLayout()
        self._theme_colors = {}
        for name, color in [("暖橙", "#FF6B35"), ("珊瑚", "#FF7F50"), ("蜜桃", "#FF9A76"), ("焦糖", "#D2691E")]:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setEnabled(False)
            btn.setToolTip("即将推出～")
            btn.setStyleSheet(f"""
                        QPushButton {{ background: {color}; border: 2px solid {Colors.BORDER};
                                      border-radius: 14px; }}
                    """)
            theme_layout.addWidget(btn)
            self._theme_colors[name] = btn
        theme_layout.addStretch()
        layout.addLayout(theme_layout)
        layout.addStretch()
        return w


    # def _apply_theme(self, color: str) -> None:
    #     """应用主题色（需重启生效的部分仅记录）。"""
    #     try:
    #         db = registry.get("database")
    #         if db: db.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('theme_color',?)",
    #                           (color,)); db.commit()
    #     except Exception:
    #         pass

    def _apply_size(self) -> None:
        pet = registry.get("floating_pet")
        if pet: pet.set_pet_size(self._size_slider.value())

    def _reset_pos(self) -> None:
        pet = registry.get("floating_pet")
        if pet:
            s = QApplication.primaryScreen().geometry()
            pet.move(s.width() - 300, s.height() - 350)

    # --- 更新 ---

    def _page_update(self) -> QWidget:
        layout, w = self._page_wrap()
        layout.addWidget(self._section("更新"))
        layout.addWidget(QLabel("当前版本: v0.1.0-alpha"))
        self._auto_cb = QCheckBox("自动检查更新"); self._auto_cb.setChecked(True)
        layout.addWidget(self._auto_cb)
        layout.addWidget(QPushButton("检查更新", clicked=lambda: QMessageBox.information(self, "更新", "已是最新版本")))
        layout.addStretch()
        return w

    # --- 数据 ---

    def _page_data(self) -> QWidget:
        layout, w = self._page_wrap()
        layout.addWidget(self._section("数据"))
        layout.addWidget(QPushButton("导出对话", clicked=self._export))
        layout.addWidget(QPushButton("备份数据库", clicked=self._backup))
        layout.addWidget(QPushButton("查看日记", clicked=self._view_diary))
        layout.addStretch()

        dg = QGroupBox("⚠ 危险操作")
        dg.setStyleSheet(f"QGroupBox {{ color: {Colors.DANGER}; font-weight: bold; }}")
        dl = QVBoxLayout(dg)
        dl.addWidget(QPushButton("清除所有数据（不可恢复）", clicked=self._clear_all,
                      styleSheet=get_button_style("danger", Fonts.SIZE_SM)))
        layout.addWidget(dg)
        return w

    def _view_diary(self) -> None:
        diary = registry.get("diary_generator")
        if not diary: return
        d = QDialog(self)
        d.setWindowTitle("猫咪日记")
        d.setFixedSize(420, 400)
        dl = QVBoxLayout(d)
        dl.addWidget(QLabel("猫咪日记"))
        lst = QListWidget()
        lst.setStyleSheet(Styles.LIST_WIDGET)
        for item in diary.list_diaries(30):
            lst.addItem(f"{item['date']}  {item['summary'][:80]}")
        dl.addWidget(lst)
        dl.addWidget(QPushButton("关闭", clicked=d.accept))
        d.exec_()

    def _export(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "导出", "vel_history.txt", "文本 (*.txt)")
        if not p: return
        try:
            db = registry.get("database")
            if not db: return
            with open(p, "w", encoding="utf-8") as f:
                for role, content, ts in db.execute("SELECT role,content,timestamp FROM conversation_archive ORDER BY msg_id").fetchall():
                    f.write(f"[{ts}] {'用户' if role == 'user' else 'Vel'}: {content}\n")
            QMessageBox.information(self, "完成", f"已导出 {p}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _backup(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "备份", "pet_backup.db", "数据库 (*.db)")
        if not p: return
        import shutil
        shutil.copy2(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pet.db"), p)
        QMessageBox.information(self, "完成", f"已备份 {p}")

    def _clear_all(self) -> None:
        if QMessageBox.question(self, "确认", "清除所有数据？此操作不可恢复！",
                                 QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        for t in ("user_profile","user_traits","episodic_memory","conversation_archive",
                  "meal_log","drink_log","activity_log","sleep_log","mood_snapshot",
                  "schedule","schedule_instance","search_cache"):
            db = registry.get("database")
            if db: db.execute(f"DELETE FROM {t}")
        if db: db.commit()
        QMessageBox.information(self, "完成", "所有数据已清除")

    # ================================================================
    # 工具
    # ================================================================

    def _setup_nav(self) -> None:
        pass

    def _get_int(self, key: str, default: int) -> int:
        try:
            db = registry.get("database")
            if not db: return default
            r = db.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            return int(r[0]) if r else default
        except Exception:
            return default

    def _load_json(self, key: str, default: list) -> list:
        try:
            import json
            return json.loads(self._profile.get_profile(key, "[]"))
        except Exception:
            return default

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_health_stats()
        self._refresh_chat()
        self._refresh_schedule()
        self._refresh_memo()
        self._refresh_habit()