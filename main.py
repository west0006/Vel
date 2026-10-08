"""
Vel - 智能AI桌宠 程序入口。
"""

import os
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import QApplication, QShortcut

from utils.logger import log_init, get_logger
from core.event_bus import (
    bus, EVENT_EXIT_REQUEST, EVENT_HEALTH_REMINDER,
    EVENT_SCHEDULE_ALERT, EVENT_SYSTEM_STATUS, EVENT_MODE_CHANGE
)
from core.state_manager import StateManager
from core.service_registry import registry
from ui.floating_pet import FloatingPet
from ui.chat_bubble import ChatBubble
from ui.system_tray import SystemTray
from ui.notification_bubble import NotificationBubble, NotificationManager

logger = get_logger(__name__)

class _ReplyBridge(QObject):
    """信号桥接：后台线程 → 主线程 UI 更新。"""
    ready = pyqtSignal(str, str)

class VelApplication:
    # _reply_signal = pyqtSignal(str, str)

    def __init__(self):
        self._app: QApplication = None
        self._state_manager: StateManager = None
        self._floating_pet: FloatingPet = None
        self._chat_bubble: ChatBubble = None
        self._system_tray: SystemTray = None
        self._notification_bubble: NotificationBubble = None
        self._notification_manager: NotificationManager = None
        # self._animation_controller: AnimationController = None
        self._chat_manager = None
        self._llm_service = None
        self._memory_service = None
        self._db_conn = None
        self._health_scheduler = None
        self._last_activity = datetime.now()
        self._reply_bridge = _ReplyBridge()
        self._reply_bridge.ready.connect(self._on_reply_ready)

    def run(self) -> None:
        self._init_logging()
        self._init_database()
        self._init_app()
        self._init_fonts()
        self._init_state_manager()
        self._register_services()
        self._init_ui()
        self._init_event_listeners()
        self._init_global_shortcuts()
        QTimer.singleShot(100, self._init_services_later)
        self._register_exit()
        logger.info("===== Vel 桌宠启动完成 =====")
        sys.exit(self._app.exec_())

    def _init_logging(self) -> None:
        log_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~/.config")),
            "SmartDesktopPet", "logs"
        )
        log_init(log_dir=log_dir)

    def _init_database(self) -> None:
        db_dir = PROJECT_ROOT / "data" / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = PROJECT_ROOT / "data" / "pet.db"
        schema_path = db_dir / "schema.sql"

        import sqlite3
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        if schema_path.exists():
            schema = schema_path.read_text(encoding="utf-8")
            conn.executescript(schema)
            conn.commit()
            logger.info("数据库初始化完成")

        registry.register("database", conn)
        self._db_conn = conn

    def _init_fonts(self) -> None:
        """加载项目自带字体。失败不阻塞启动。"""
        from PyQt5.QtGui import QFontDatabase

        fonts_dir = PROJECT_ROOT / "ui" / "resources" / "fonts"
        if not fonts_dir.is_dir():
            return

        for f in fonts_dir.glob("*.ttf"):
            font_id = QFontDatabase.addApplicationFont(str(f))
            if font_id == -1:
                logger.warning(f"字体加载失败: {f.name}")
                continue

            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                family_name = families[0]
                self._custom_font_family = family_name
                logger.info(f"字体已加载: {family_name} ({f.name})")
        # 重设应用字体为自定义字体
        if hasattr(self, '_custom_font_family'):
            self._app.setFont(QFont(self._custom_font_family, 9))

    def _init_app(self) -> None:
        self._app = QApplication(sys.argv)
        self._app.setApplicationName("Vel 智能AI桌宠")
        self._app.setApplicationVersion("0.1.0-alpha")
        self._app.setQuitOnLastWindowClosed(False)
        family = getattr(self, '_custom_font_family', None) or "Microsoft YaHei"
        self._app.setFont(QFont(family, 9))
        qss = PROJECT_ROOT / "ui" / "resources" / "styles.qss"
        if qss.exists():
            self._app.setStyleSheet(qss.read_text(encoding="utf-8"))

    def _init_state_manager(self) -> None:
        self._state_manager = StateManager()
        registry.register("state_manager", self._state_manager)

    def _register_services(self) -> None:
        pass

    def _init_global_shortcuts(self) -> None:
        pet = self._floating_pet
        QShortcut(QKeySequence("Ctrl+Shift+P"), pet, self._toggle_pet_visible)
        QShortcut(QKeySequence("Ctrl+Shift+C"), pet, self._toggle_chat_bubble)
        QShortcut(QKeySequence("Ctrl+Shift+S"), pet, self._on_show_settings)

    def _toggle_pet_visible(self) -> None:
        if self._floating_pet.isVisible():
            self._floating_pet.hide()
        else:
            self._floating_pet.show()

    def _init_ui(self) -> None:
        self._floating_pet = FloatingPet()
        registry.register("floating_pet", self._floating_pet)

        self._chat_bubble = ChatBubble(self._floating_pet)
        registry.register("chat_bubble", self._chat_bubble)
        self._chat_bubble.message_sent.connect(self._on_user_message)

        self._floating_pet.clicked.connect(self._toggle_chat_bubble)

        self._notification_manager = NotificationManager()
        self._notification_bubble = NotificationBubble(
            self._floating_pet, manager=self._notification_manager
        )
        self._notification_manager.set_notification_bubble(self._notification_bubble)
        registry.register("notification_manager", self._notification_manager)

        self._system_tray = SystemTray()
        self._system_tray.show_chat.connect(self._toggle_chat_bubble)
        self._system_tray.show_settings.connect(self._on_show_settings)
        self._system_tray.show_about.connect(self._on_show_about)
        self._system_tray.request_exit.connect(self._on_exit)
        self._system_tray.toggle_quiet_hour.connect(
            lambda: self._state_manager.set_quiet_mode(not self._state_manager.is_quiet_mode)
        )
        self._system_tray.toggle_quiet_till_morning.connect(
            lambda: self._state_manager.set_quiet_mode(True)
        )
        self._system_tray.toggle_pause_all.connect(self._on_toggle_pause_all)
        self._system_tray.show_schedule.connect(self._on_show_schedule)
        self._system_tray.initialize()

        self._floating_pet.show()

    def _on_toggle_pause_all(self, paused: bool) -> None:
        from apscheduler.schedulers.qt import QtScheduler
        scheduler: QtScheduler = registry.get("health_scheduler")
        if scheduler is None:
            return
        if paused:
            scheduler.pause()
            self._floating_pet.show_tip("⏸ 所有提醒已暂停", 3000)
        else:
            scheduler.resume()
            self._floating_pet.show_tip("▶ 提醒已恢复", 3000)

    def _init_event_listeners(self) -> None:
        bus.subscribe_ui(EVENT_HEALTH_REMINDER, self._on_health_reminder)
        bus.subscribe_ui(EVENT_SCHEDULE_ALERT, self._on_schedule_alert)
        bus.subscribe_ui(EVENT_SYSTEM_STATUS, self._on_system_status)
        bus.subscribe_ui(EVENT_MODE_CHANGE, self._on_mode_change)
        bus.subscribe_ui("CONTEXT_HINT", lambda d: self._chat_bubble.show_context_hint(d["text"]))
        logger.info("事件监听器已注册")

    def _on_health_reminder(self, data: dict) -> None:
        rt = data.get("type", "")
        msg = data.get("message", "")
        if rt in ("activity_guide", "activity_complete"):
            return
        if rt == "drink_summary":
            self._notification_manager.push({
                "id": f"drink_summary_{data.get('current_ml',0)}",
                "title": "饮水总结", "message": msg, "priority": 0, "duration_ms": 10000,
                "notif_type": "health",
            })
            return
        on_action = self._make_health_callback(rt, data)
        self._notification_manager.push({
            "id": f"health_{data.get('schedule_id','')}",
            "title": "健康提醒", "message": msg,
            "priority": data.get("priority", 0), "duration_ms": 8000,
            "buttons": data.get("buttons", []), "on_action": on_action,
            "notif_type": "health",
        })
        self._floating_pet.show_tip(msg.split("\n")[0][:30], 4000)

    def _make_health_callback(self, rt: str, data: dict):
        if rt == "drink_reminder":
            dr = registry.get("drink_reminder")
            def cb(a):
                if dr:
                    r = dr.handle_feedback(a)
                    if r: self._floating_pet.show_tip(r[:40], 4000)
            return cb
        if rt == "meal_recommendation":
            me = registry.get("meal_engine"); mt = data.get("meal_type", "lunch")
            def cb(a):
                if me:
                    r = me.handle_feedback(mt, a)
                    if r: self._floating_pet.show_tip(r[:40], 4000)
            return cb
        if rt == "sedentary_reminder":
            sd = registry.get("sedentary_monitor")
            def cb(a):
                if sd:
                    r = sd.handle_feedback(a, data.get("activity_name",""),
                                           data.get("guide_text",""),
                                           data.get("duration_min",3))
                    if r: self._floating_pet.show_tip(r[:40], 4000)
            return cb
        if rt == "drink_undo":
            dr = registry.get("drink_reminder")
            log_id = data.get("log_id")
            def cb(a):
                if dr and a == "undo":
                    r = dr.undo_drink(log_id)
                    self._floating_pet.show_tip(r[:40], 4000)
            return cb
        return None

    def _on_schedule_alert(self, data: dict) -> None:
        stage = data.get("stage", "due")
        sid = data.get("schedule_id", "")
        msg = f"⏰ {data.get('title','')}" if stage == "advance" else f"🔔 {data.get('title','')}"
        if data.get("description"): msg += f"\n{data['description']}"

        rs = registry.get("reminder_scheduler")
        def cb(a):
            if not rs: return
            if a == "complete":
                rs.mark_completed(sid)
                self._floating_pet.show_tip("✅ 已完成", 3000)
            elif a == "snooze":
                if not rs.snooze(sid, 5):
                    self._floating_pet.show_tip("已超小睡上限", 3000)

        self._notification_manager.push({
            "id": sid, "title": "📅 日程提醒", "message": msg,
            "priority": 1 if stage == "advance" else 2, "duration_ms": 15000,
            "buttons": [("✅ 完成","complete","primary"),("🔔 5分钟后","snooze","secondary")],
            "on_action": cb,"notif_type": "schedule",
        })
        self._floating_pet.show_tip(f"🔔 {data.get('title','')[:20]}", 5000)

    def _on_system_status(self, data: dict) -> None:
        st = data.get("type", "")
        if st == "key_generated":
            self._floating_pet.show_tip("密钥已生成\n请备份 config/key.bin", 10000)
        elif st == "llm_degrade":
            self._floating_pet.show_tip("AI 降级模式", 5000)
            self._system_tray.set_degraded_mode(True)
        elif st == "llm_recovered":
            self._floating_pet.show_tip("AI 已恢复", 3000)
            self._system_tray.set_degraded_mode(False)
        elif st == "model_loading":
            self._floating_pet.show_tip(f"加载: {data.get('model','')}", 3000)

    def _on_mode_change(self, data: dict) -> None:
        new_mode = data.get("new", "")
        if new_mode == "silent":
            self._system_tray.set_degraded_mode(True)
        else:
            self._system_tray.set_degraded_mode(False)

    def _init_services_later(self) -> None:
        from apscheduler.schedulers.qt import QtScheduler

        self._health_scheduler = QtScheduler()
        self._health_scheduler.start()
        registry.register("health_scheduler", self._health_scheduler)

        # LLM 初始化
        try:
            from services.llm_service import LLMService
            self._llm_service = LLMService(model="qwen2.5:7b", timeout=60, max_tokens=512)
            registry.register("llm_service", self._llm_service)
            ok, msg = self._llm_service.check_connection()
            if ok:
                # 预热：后台发一条短消息触发模型加载
                import threading
                def _warm():
                    try:
                        self._llm_service._call_ollama([
                            {"role": "user", "content": "hi"}
                        ])
                        logger.info("LLM 模型预热完成")
                    except Exception:
                        pass
                threading.Thread(target=_warm, daemon=True).start()
                self._floating_pet.show_tip("Vel 已准备好~", 3000)
            else:
                self._floating_pet.show_tip("AI 未连接，降级模式", 5000)
                self._system_tray.set_degraded_mode(True)
        except Exception as e:
            logger.error(f"LLM 失败: {e}")

        # 记忆服务后台加载（sentence-transformers 3-5s，不阻塞 UI）
        import threading
        def _init_memory():
            try:
                from services.memory_service import MemoryService
                ms = MemoryService(
                    db_path=str(PROJECT_ROOT / "data" / "pet.db"),
                    faiss_path=str(PROJECT_ROOT / "data" / "faiss.index"),
                )
                ms.initialize()
                registry.register("memory_service", ms)
                logger.info("记忆服务已注册")
            except Exception as e:
                logger.warning(f"记忆服务失败: {e}")
        threading.Thread(target=_init_memory, daemon=True).start()

        try:
            from modules.personality.extractor import PersonalityExtractor
            from modules.personality.profile_manager import ProfileManager
            registry.register("personality_extractor", PersonalityExtractor())
            registry.register("profile_manager", ProfileManager())
        except Exception as e:
            logger.warning(f"个性化引擎失败: {e}")

        try:
            from modules.chat.chat_manager import ChatManager
            self._chat_manager = ChatManager()
            self._chat_manager.initialize()
            registry.register("chat_manager", self._chat_manager)
        except Exception as e:
            logger.error(f"对话管理器失败: {e}")

        try:
            from services.tool_executor import ToolExecutor
            registry.register("tool_executor", ToolExecutor())
            logger.info("工具执行器已注册")
        except Exception as e:
            logger.warning(f"工具执行器失败: {e}")

        for mod_name, cls_name, key in [
            ("modules.health.drink_reminder", "DrinkReminder", "drink_reminder"),
            ("modules.health.meal_engine", "MealEngine", "meal_engine"),
            ("modules.health.sedentary_monitor", "SedentaryMonitor", "sedentary_monitor"),
            ("modules.health.sleep_tracker", "SleepTracker", "sleep_tracker"),
        ]:
            try:
                mod = __import__(mod_name, fromlist=[cls_name])
                instance = getattr(mod, cls_name)()
                instance.initialize()
                registry.register(key, instance)
            except Exception as e:
                logger.warning(f"{key} 失败: {e}")

        try:
            from modules.schedule.schedule_store import ScheduleStore
            from modules.schedule.reminder_scheduler import ReminderScheduler
            store = ScheduleStore()
            registry.register("schedule_store", store)
            def on_reminder_trigger(data: dict):
                bus.publish(EVENT_SCHEDULE_ALERT, data)
            scheduler = ReminderScheduler()
            scheduler.initialize(on_trigger=on_reminder_trigger)
            scheduler.load_snapshot()
            scheduler.rebuild_from_database()
            registry.register("reminder_scheduler", scheduler)
            logger.info("日程模块已注册")
        except Exception as e:
            logger.warning(f"日程模块初始化失败: {e}")

        try:
            from services.search_service import SearchService
            search = SearchService()
            search.initialize()
            registry.register("search_service", search)
            logger.info("搜索服务已注册")
        except Exception as e:
            logger.warning(f"搜索服务初始化失败: {e}")

        try:
            from services.location_service import LocationService
            location = LocationService()
            location.initialize()
            registry.register("location_service", location)
            logger.info("位置服务已注册")
        except Exception as e:
            logger.warning(f"位置服务初始化失败: {e}")

        try:
            from modules.onboarding.wizard import OnboardingWizard
            if OnboardingWizard.check_first_run():
                wizard = OnboardingWizard(self._floating_pet)
                wizard.wizard_finished.connect(self._on_wizard_finished)
                wizard.exec_()
        except Exception as e:
            logger.warning(f"引导向导失败: {e}")

        self._idle_timer = QTimer()
        self._idle_timer.setInterval(5000)
        self._idle_timer.timeout.connect(self._check_idle_and_fullscreen)
        self._idle_timer.start()
        try:
            from modules.easter_egg import EasterEggEngine
            registry.register("easter_egg_engine", EasterEggEngine())
        except Exception as e:
            logger.warning(f"彩蛋引擎失败: {e}")

        try:
            from modules.memo import MemoManager
            registry.register("memo_manager", MemoManager())
        except Exception as e:
            logger.warning(f"备忘录管理器失败: {e}")

        try:
            from modules.diary import DiaryGenerator
            diary = DiaryGenerator()
            registry.register("diary_generator", diary)
            # 每日21:00自动生成
            self._health_scheduler.add_job(
                func=lambda: diary.generate(),
                trigger=__import__('apscheduler').triggers.cron.CronTrigger(hour=21, minute=0),
                id="diary_daily", replace_existing=True,
            )
            logger.info("日记模块已注册")
        except Exception as e:
            logger.warning(f"日记模块失败: {e}")

        try:
            from modules.pomodoro import PomodoroTimer
            pomo = PomodoroTimer()
            registry.register("pomodoro_timer", pomo)
            self._chat_bubble.pomodoro_clicked.connect(
                lambda: pomo.start() if pomo.state != "running" else pomo.cancel()
            )
            logger.info("番茄钟已注册")
        except Exception as e:
            logger.warning(f"番茄钟失败: {e}")

        try:
            from modules.habit import HabitManager
            registry.register("habit_manager", HabitManager())
            logger.info("习惯模块已注册")
        except Exception as e:
            logger.warning(f"习惯模块失败: {e}")

        try:
            from modules.greeting import GreetingService
            registry.register("greeting_service", GreetingService())
            logger.info("问候服务已注册")
        except Exception as e:
            logger.warning(f"问候服务失败: {e}")

    def _register_exit(self) -> None:
        bus.subscribe_sync(EVENT_EXIT_REQUEST, lambda _: self._graceful_exit())

    def _toggle_chat_bubble(self) -> None:
        if self._chat_bubble.is_bubble_visible:
            self._chat_bubble.hide_bubble()
        else:
            QTimer.singleShot(0, lambda: self._show_bubble_safe())

    def _show_bubble_safe(self) -> None:
        """延迟展开气泡，避免同事件循环内被 OutsideClickFilter 误杀。"""
        self._chat_bubble.show_bubble(self._floating_pet.geometry())
        # 每日问候检测
        greeting = registry.get("greeting_service")
        if greeting:
            msg = greeting.check_and_greet()
            if msg:
                self._notification_manager.push({
                    "id": f"greeting_{id(msg)}",
                    "title": "🌅 早上好" if "早" in msg else "☀️ 你好",
                    "message": msg,
                    "priority": 5,
                    "duration_ms": 5000,
                    "notif_type": "greeting",
                })

    def _on_user_message(self, text: str) -> None:
        self._last_activity = datetime.now()
        if not self._chat_manager:
            self._chat_bubble.add_message("assistant", "喵...我还没准备好")
            return
        self._floating_pet.set_emotion("thinking", loop=True)
        self._chat_bubble.show_thinking()
        import threading

        # 流式回调：后台线程通过信号逐 chunk 推送到主线程 UI
        def _on_stream(chunk: str) -> None:
            self._reply_bridge.ready.emit(text, chunk)

        self._chat_manager.set_stream_callback(_on_stream)

        def _worker():
            try:
                reply = self._chat_manager.process_message(text)
                # 标记流结束 → 主线程固化
                self._reply_bridge.ready.emit(text, "\0__END__")
            except Exception as e:
                logger.exception(f"消息异常: {e}")
                self._reply_bridge.ready.emit(text, "\0__ERR__" + str(e))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_reply_ready(self, user_text: str, data: str) -> None:
        if data == "\0__END__":
            self._chat_bubble.stream_finish()
            self._floating_pet.set_emotion("idle")
        elif data.startswith("\0__ERR__"):
            self._chat_bubble.stream_clear()
            self._chat_bubble.add_message("assistant", "喵...没听清，再说一遍吗~")
            self._floating_pet.set_emotion("idle")
        else:
            self._chat_bubble.stream_append(data)

    def _on_show_schedule(self) -> None:
        from ui.mini_schedule import MiniScheduleWidget
        if not hasattr(self, '_mini_schedule'):
            self._mini_schedule = MiniScheduleWidget(self._system_tray)
        self._mini_schedule.show_at_tray()

    def _on_show_settings(self) -> None:
        from ui.settings_window import SettingsWindow
        self._settings_win = SettingsWindow(self._floating_pet)
        self._settings_win.show()

    def _on_show_about(self) -> None:
        from ui.about_dialog import AboutDialog
        dlg = AboutDialog(self._floating_pet)
        dlg.exec_()

    def _on_exit(self) -> None:
        logger.info("用户请求退出")
        bus.publish(EVENT_EXIT_REQUEST)

    def _on_wizard_finished(self, data: dict) -> None:
        nickname = data.get("nickname", "用户")
        if self._chat_manager:
            self._chat_manager.set_user_name(nickname)

    def _check_idle_and_fullscreen(self) -> None:
        from core.state_manager import UserActivityState
        import ctypes
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                rect = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                fw, fh = rect.right - rect.left, rect.bottom - rect.top
                sw = QApplication.primaryScreen().geometry()
                is_fs = (fw >= sw.width() * 0.95 and fh >= sw.height() * 0.95)
                if hwnd != int(self.winId() if self._floating_pet else 0):
                    self._floating_pet.check_fullscreen(is_fs)
                    if is_fs:
                        self._state_manager.set_user_state(UserActivityState.BUSY)
                    elif self._state_manager.user_state == UserActivityState.BUSY:
                        self._state_manager.set_user_state(UserActivityState.ACTIVE)
        except Exception:
            pass
        elapsed = (datetime.now() - self._last_activity).total_seconds()
        if elapsed > 300 and self._state_manager.user_state == UserActivityState.ACTIVE:
            self._state_manager.set_user_state(UserActivityState.IDLE)
        elif elapsed < 10 and self._state_manager.user_state == UserActivityState.IDLE:
            self._state_manager.set_user_state(UserActivityState.ACTIVE)

    def _graceful_exit(self) -> None:
        logger.info("关闭中...")
        self._floating_pet.save_position()
        self._system_tray.hide()
        self._floating_pet.cleanup()

        # 关闭调度器（顺序重要：scheduler → eventbus → db）
        if hasattr(self, '_health_scheduler') and self._health_scheduler:
            try:
                rs = registry.get("reminder_scheduler")
                if rs:
                    rs.shutdown()
                logger.info("提醒调度器已关闭")
            except Exception as e:
                logger.warning(f"提醒调度器关闭异常: {e}")
            try:
                self._health_scheduler.shutdown(wait=False)
                logger.info("健康调度器已关闭")
            except Exception as e:
                logger.warning(f"健康调度器关闭异常: {e}")

        bus.shutdown(wait=True)
        self._db_conn.close()
        logger.info("Vel 已关闭")
        self._app.quit()


def main() -> None:
    app = VelApplication()
    app.run()


if __name__ == "__main__":
    main()