"""
饮食推荐引擎模块。

在饭点时段自动触发，收集上下文信息（用户画像/饮食记录/情绪/天气/位置），
调用 LLM 生成个性化饮食推荐，通过通知气泡呈现给用户。
"""

from datetime import datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from apscheduler.schedulers.qt import QtScheduler
from apscheduler.triggers.cron import CronTrigger

from core.event_bus import bus, EVENT_HEALTH_REMINDER
from core.service_registry import registry
from core.state_manager import StateManager, UserActivityState, PetMode
from utils.logger import get_logger

logger = get_logger(__name__)


class MealEngine:
    """饮食推荐引擎。

    在饭点触发，收集多维度上下文生成推荐，
    通过 LLM 生成个性化饮食建议，支持反馈闭环学习。
    """

    def __init__(self):
        self._scheduler: Optional[QtScheduler] = None
        self._state_manager: Optional[StateManager] = None
        self._today_recommended: Dict[str, bool] = {}  # meal_type -> 今日是否已推荐
        self._retry_count: Dict[str, int] = {}          # meal_type -> 换一个次数
        self._max_retries = 3
        self._retry_delay_min = 60  # 忽略后1小时重试
        self._callback: Optional[Callable] = None
        self._scheduler = None

        # 饭点配置
        self._meal_times: Dict[str, Tuple[time, time]] = {
            "lunch": (time(11, 30), time(12, 30)),
            "dinner": (time(17, 30), time(18, 30)),
        }
        self._meal_names = {"lunch": "午餐", "dinner": "晚餐"}

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize(self, callback: Optional[Callable] = None) -> None:
        self._state_manager = registry.get("state_manager")
        self._callback = callback

        self._scheduler = registry.get("health_scheduler")
        if self._scheduler is None:
            self._scheduler = QtScheduler()
            self._scheduler.start()
            registry.register("health_scheduler", self._scheduler)

        for meal_type, (start, end) in self._meal_times.items():
            self._scheduler.add_job(
                func=lambda mt=meal_type: self._on_meal_time(mt),
                trigger=CronTrigger(hour=start.hour, minute=start.minute),
                id=f"meal_{meal_type}",
                replace_existing=True,
            )

        logger.info("饮食推荐引擎已启动")

    # ------------------------------------------------------------------
    # 饭点触发
    # ------------------------------------------------------------------

    def _on_meal_time(self, meal_type: str) -> None:
        """饭点触发回调。

        Args:
            meal_type: lunch / dinner
        """
        # 检查今日是否已推荐
        date_key = f"{datetime.now().strftime('%Y%m%d')}_{meal_type}"
        if self._today_recommended.get(date_key, False):
            logger.debug(f"今日{meal_type}已推荐过，跳过")
            return

        # 检查用户状态
        if self._state_manager:
            state = self._state_manager.user_state
            if state in (UserActivityState.BUSY, UserActivityState.SLEEP):
                logger.debug(f"用户状态 {state.value}，跳过{meal_type}推荐")
                # 30分钟后重试
                self._schedule_retry(meal_type, 30)
                return

        # 开始推荐流程
        self._generate_recommendation(meal_type)

    def _generate_recommendation(self, meal_type: str) -> str:
        """生成饮食推荐。

        Args:
            meal_type: lunch / dinner

        Returns:
            推荐文本
        """
        meal_name = self._meal_names.get(meal_type, "用餐")
        logger.info(f"生成{meal_name}推荐...")

        # 1. 收集上下文
        context = self._collect_context(meal_type)

        # 2. 构建提示词
        prompt = self._build_meal_prompt(meal_type, context)

        # 3. 调用 LLM
        recommendation = self._call_llm(prompt)

        if not recommendation:
            recommendation = f"到{meal_name}时间啦~记得按时吃饭哦！🍚"
        else:
            # 追加一句健康小贴士
            tip = self._health_tip(context)
            if tip:
                recommendation += f"\n💡 {tip}"

        # 4. 发送通知
        schedule_id = f"meal_{meal_type}_{datetime.now().strftime('%Y%m%d%H%M')}"

        bus.publish(EVENT_HEALTH_REMINDER, {
            "type": "meal_recommendation",
            "schedule_id": schedule_id,
            "meal_type": meal_type,
            "recommendation": recommendation,
            "shops": context.get("shops", []),
            "buttons": [
                ("就吃这个", "accept", "primary"),
                ("换一个", "switch", "secondary"),
                ("已吃过", "eaten", "secondary"),
            ],
        })

        # 标记今日已推荐
        date_key = f"{datetime.now().strftime('%Y%m%d')}_{meal_type}"
        self._today_recommended[date_key] = True

        # 外部回调
        if self._callback:
            self._callback(meal_type, recommendation, context.get("shops", []))

        return recommendation

    # ------------------------------------------------------------------
    # 上下文收集
    # ------------------------------------------------------------------

    def _collect_context(self, meal_type: str) -> Dict[str, Any]:
        """收集推荐所需的上下文信息。

        Returns:
            {profile, dietary, recent_meals, mood, weather, shops}
        """
        context = {
            "profile": self._get_user_profile(),
            "dietary": self._get_dietary_prefs(),
            "recent_meals": self._get_recent_meals(3),
            "mood": self._get_latest_mood(),
            "weather": self._get_weather(),
            "shops": self._get_nearby_shops(meal_type),
        }
        return context

    def _get_user_profile(self) -> Dict[str, str]:
        """获取用户画像（昵称、喜好等）。"""
        try:
            db = registry.get("database")
            if db is None:
                return {}
            cursor = db.execute("SELECT key, value FROM user_profile")
            from utils.crypto import decrypt
            return {row[0]: decrypt(row[1]) for row in cursor.fetchall()}
        except Exception:
            return {}

    def _get_dietary_prefs(self) -> List[str]:
        """获取饮食偏好。"""
        try:
            db = registry.get("database")
            if db is None:
                return []
            cursor = db.execute(
                "SELECT trait_name, value FROM user_traits "
                "WHERE (trait_name LIKE 'prefer_%' OR trait_name LIKE 'diet_%') "
                "AND confidence >= 0.6"
            )
            return [f"{row[0]}: {row[1]}" for row in cursor.fetchall()]
        except Exception:
            return []

    def _get_recent_meals(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近 N 天的饮食记录。"""
        try:
            db = registry.get("database")
            if db is None:
                return []
            db.row_factory = None
            cursor = db.execute(
                "SELECT meal_type, content, timestamp FROM meal_log "
                "WHERE timestamp >= date('now', ?) ORDER BY timestamp DESC LIMIT 20",
                (f"-{days} days",)
            )
            return [{"type": r[0], "content": r[1], "time": r[2]} for r in cursor.fetchall()]
        except Exception:
            return []

    def _get_latest_mood(self) -> Optional[str]:
        """获取最近一次情绪快照。"""
        try:
            db = registry.get("database")
            if db is None:
                return None
            cursor = db.execute(
                "SELECT mood_label, intensity FROM mood_snapshot "
                "ORDER BY timestamp DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return f"{row[0]}({row[1]:.1f})" if row else None
        except Exception:
            return None

    def _get_weather(self) -> Optional[str]:
        try:
            import requests
            resp = requests.get("https://wttr.in/?format=%C+%t", timeout=3,
                                headers={"User-Agent": "curl/7.0"})
            if resp.status_code == 200 and resp.text.strip():
                return resp.text.strip()
        except Exception:
            pass
        return None

    def _get_nearby_shops(self, meal_type: str) -> List[Dict[str, Any]]:
        """获取附近餐饮店铺。"""
        try:
            location_service = registry.get("location_service")
            if location_service:
                return location_service.search_nearby("餐饮", limit=5)
        except Exception:
            pass
        return []

    # ------------------------------------------------------------------
    # 提示词构建
    # ------------------------------------------------------------------

    def _build_meal_prompt(self, meal_type: str, context: Dict[str, Any]) -> str:
        """构建送给 LLM 的饮食推荐提示词。

        Args:
            meal_type: lunch / dinner
            context: 上下文信息

        Returns:
            提示词文本
        """
        meal_name = self._meal_names.get(meal_type, "用餐")
        now = datetime.now()

        parts = [
            f"现在是{now.strftime('%H:%M')}，{meal_name}时间到了。",
            "请你作为贴心的饮食助手，给用户推荐今天吃什么。",
        ]

        # 用户信息
        profile = context.get("profile", {})
        if profile.get("nickname"):
            parts.append(f"用户昵称: {profile['nickname']}")

        # 饮食偏好
        prefs = context.get("dietary", [])
        if prefs:
            parts.append(f"饮食偏好: {', '.join(prefs)}")

        if profile.get("dietary_restrictions"):
            parts.append(f"忌口: {profile['dietary_restrictions']}")

        # 近期饮食
        recent = context.get("recent_meals", [])
        if recent:
            parts.append("最近吃过的:")
            for m in recent[:6]:
                parts.append(f"  - {m.get('type', '')}: {m.get('content', '')}")

        # 情绪
        mood = context.get("mood")
        if mood:
            parts.append(f"用户当前情绪: {mood}")

        # 附近店铺
        shops = context.get("shops", [])
        if shops:
            parts.append("附近可选的店铺:")
            for s in shops[:5]:
                name = s.get("name", "")
                dist = s.get("distance", "")
                parts.append(f"  - {name} ({dist})")

        # 推荐要求
        parts.append("\n请生成一条简短的饮食推荐（不超过120字），")
        parts.append("包含1-2个具体建议，语气温柔亲切（猫咪口吻）。")
        parts.append("如果有附近店铺，优先推荐其中一个。")
        parts.append("推荐要简单明了，不要问问题。")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # LLM 调用
    # ------------------------------------------------------------------

    def _health_tip(self, ctx: dict) -> Optional[str]:
        """生成一句饮食健康小贴士。"""
        llm = registry.get("llm_service")
        if llm is None or getattr(llm, '_is_degraded', True):
            return None
        try:
            profile = ctx.get("profile", {})
            recent = ctx.get("recent_meals", [])
            tip_prompt = (
                f"用户最近吃了：{', '.join(m.get('content','')[:20] for m in recent[:3] if m.get('content'))}。"
                f"给一句15字以内的饮食健康小提醒，猫咪口吻。"
            )
            reply = llm._call_ollama([
                {"role": "system", "content": "你是健康助手，回复15字以内。"},
                {"role": "user", "content": tip_prompt},
            ])
            return reply.strip() if reply and len(reply) > 2 else None
        except Exception:
            return None

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM 生成饮食推荐。"""
        llm = registry.get("llm_service")
        if llm is None:
            return None
        try:
            # 使用独立的 LLM 调用（不影响对话上下文）
            if hasattr(llm, '_call_ollama'):
                reply = llm._call_ollama([
                    {"role": "system", "content": "你是饮食推荐助手，回复简洁，不超过120字。"},
                    {"role": "user", "content": prompt},
                ])
            else:
                reply = llm.generate(prompt)
            return reply.strip()
        except Exception as e:
            logger.error(f"饮食推荐 LLM 调用失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 反馈处理
    # ------------------------------------------------------------------

    def handle_feedback(self, meal_type: str, action: str, content: str = "") -> str:
        """处理用户对推荐的反馈。

        Args:
            meal_type: lunch / dinner
            action: accept / switch / eaten
            content: 用户输入的内容（accept/eaten 时）

        Returns:
            回复文本
        """
        date_key = f"{datetime.now().strftime('%Y%m%d')}_{meal_type}"

        if action == "accept":
            # 记录采纳的推荐
            self._record_meal(meal_type, content or "按推荐选择", source="recommendation")
            self._update_preference_confidence(content or "recommendation", delta=1)
            return "太好了！记得好好享受哦～🍽️"

        elif action == "switch":
            # 换一个推荐
            retries = self._retry_count.get(meal_type, 0)
            if retries >= self._max_retries:
                return "喵~我已经没新点子了，你就随便吃点吧？😸"

            self._retry_count[meal_type] = retries + 1
            # 允许再次推荐
            self._today_recommended.pop(date_key, None)
            # 同步触发重新推荐
            recommendation = self._generate_recommendation(meal_type)
            return recommendation

        elif action == "eaten":
            # 记录已吃
            self._record_meal(meal_type, content or "用户自选", source="manual")
            return "好的，已记录！记得好好吃饭，保持健康~ 💪"

        elif action == "ignore":
            # 忽略 → 1小时后重试
            self._schedule_retry(meal_type, self._retry_delay_min)
            return ""

        return ""

    def _record_meal(self, meal_type: str, content: str, source: str = "manual") -> None:
        """记录饮食到数据库。"""
        try:
            db = registry.get("database")
            if db:
                db.execute(
                    "INSERT INTO meal_log (meal_type, content, source, accepted) VALUES (?, ?, ?, ?)",
                    (meal_type, content, source, 1 if source == "recommendation" else 1),
                )
                db.commit()
                logger.info(f"饮食记录: {meal_type} - {content}")
        except Exception as e:
            logger.error(f"饮食记录失败: {e}")

    def _update_preference_confidence(self, content: str, delta: int = 1) -> None:
        """更新偏好置信度。"""
        try:
            db = registry.get("database")
            if db is None:
                return
            # 简化版：增加相关偏好的 occurrences
            db.execute(
                "UPDATE user_traits SET occurrences = occurrences + ?, "
                "confidence = MIN(confidence + 0.1, 0.95), "
                "last_active = datetime('now') "
                "WHERE trait_name LIKE 'prefer_%'",
                (delta,)
            )
            db.commit()
        except Exception as e:
            logger.debug(f"偏好更新失败: {e}")

    def _schedule_retry(self, meal_type: str, delay_min: int) -> None:
        """安排延迟重试。"""
        if self._scheduler is None:
            return
        from apscheduler.triggers.date import DateTrigger
        run_time = datetime.now() + timedelta(minutes=delay_min)
        self._scheduler.add_job(
            func=lambda mt=meal_type: self._on_meal_time(mt),
            trigger=DateTrigger(run_date=run_time),
            id=f"meal_retry_{meal_type}",
            replace_existing=True,
        )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_today_meals(self) -> List[Dict[str, Any]]:
        """获取今日饮食记录。"""
        try:
            db = registry.get("database")
            if db is None:
                return []
            cursor = db.execute(
                "SELECT meal_type, content, timestamp FROM meal_log "
                "WHERE date(timestamp) = date('now') ORDER BY timestamp DESC"
            )
            return [{"type": r[0], "content": r[1], "time": r[2]} for r in cursor.fetchall()]
        except Exception:
            return []

    def get_weekly_summary(self) -> Dict[str, Any]:
        """获取本周饮食概览。"""
        try:
            db = registry.get("database")
            if db is None:
                return {}
            cursor = db.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN source='recommendation' AND accepted=1 THEN 1 ELSE 0 END) as accepted, "
                "AVG(CASE WHEN accepted=1 THEN 1.0 ELSE 0.0 END) as accept_rate "
                "FROM meal_log WHERE timestamp >= date('now', '-7 days')"
            )
            row = cursor.fetchone()
            return {
                "total_meals": row[0] or 0,
                "accepted": row[1] or 0,
                "accept_rate": round((row[2] or 0) * 100, 1),
            }
        except Exception:
            return {}

    def reset_daily_state(self) -> None:
        """每日重置状态。"""
        self._today_recommended.clear()
        self._retry_count.clear()

    def shutdown(self) -> None:
        """关闭引擎。"""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)