"""
位置服务模块。

提供基于高德地图 API 的 IP 定位和周边餐饮搜索功能。
包含本地缓存和用量监控，确保不超出免费配额。
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class LocationService:
    """位置服务。

    提供：
    - 高德 IP 定位
    - 周边 POI 搜索（餐饮）
    - 结果缓存（默认4小时）
    - API 用量监控
    """

    def __init__(self, api_key: str = ""):
        from core.config import config

        self._api_key = api_key or self._load_api_key()
        self._base_url = "https://restapi.amap.com/v3"
        self._timeout = 5

        # 缓存
        self._location_cache: Optional[Dict[str, Any]] = None
        self._location_cache_time: Optional[datetime] = None
        # 缓存（配置单位是秒，此处按小时使用：search.cache_ttl_location）
        ttl_seconds = config.get_int("search.cache_ttl_location", 14400)
        self._location_cache_ttl_hours = max(1, ttl_seconds // 3600)

        # 用量统计
        self._daily_count = 0
        self._daily_date = ""
        self._daily_limit = config.get_int("search.gaode_daily_limit", 4500)

    @staticmethod
    def _config_path() -> str:
        """统一获取 secrets.yaml 路径（兼容 PyInstaller 打包）。"""
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            base = meipass
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "config", "secrets.yaml")

    @staticmethod
    def _load_api_key() -> str:
        """加载高德 API Key。"""
        config_path = LocationService._config_path()
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("gaode", {}).get("api_key", "")
        except Exception:
            logger.exception("_load_api_key 执行失败")
        return ""

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """初始化位置服务。"""
        if not self._api_key:
            logger.warning("高德 API Key 未配置，位置服务不可用")
            return False

        # 加载今日用量
        self._load_daily_count()
        logger.info(f"位置服务已启动 (今日已调用 {self._daily_count} 次)")
        return True

    # ------------------------------------------------------------------
    # IP 定位
    # ------------------------------------------------------------------

    def get_location(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """获取当前位置（IP 定位）。

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            {city, province, district, adcode, rectangle, ...}
        """
        if not self._api_key:
            return None

        # 检查缓存
        if not force_refresh and self._is_location_cache_valid():
            logger.debug("使用位置缓存")
            return self._location_cache

        # 检查配额
        if not self._check_quota():
            logger.warning("高德 API 日配额已用尽")
            return self._location_cache or None

        try:
            resp = requests.get(
                f"{self._base_url}/ip",
                params={
                    "key": self._api_key,
                    "output": "JSON",
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "1":
                city = data.get("city", [])
                province = data.get("province", [])
                city_val = city[0] if isinstance(city, list) and city else ""
                prov_val = province[0] if isinstance(province, list) and province else ""

                if city_val or prov_val:
                    self._location_cache = data
                    self._location_cache_time = datetime.now()
                    self._increment_count()
                    logger.info(f"位置获取成功: {city_val}")
                    return data

            # 高德无结果 → 兜底 ip-api.com
            logger.info("高德无定位结果，尝试 ip-api.com 兜底")
            fallback = self._fallback_ip_api()
            if fallback:
                self._increment_count()
            return fallback or {"city": "", "province": "", "district": ""}

        except requests.Timeout:
            logger.warning("IP 定位请求超时")
            return self._location_cache
        except Exception as e:
            logger.error(f"IP 定位异常: {e}")
            return self._location_cache

    def get_city(self) -> str:
        """获取当前城市名称。"""
        location = self.get_location()
        if location:
            return location.get("city", "未知")
        return "未知"

    def _fallback_ip_api(self) -> Optional[Dict[str, Any]]:
        """多源兜底：ipapi.co → ip-api.com"""
        # 源1：ipapi.co（JSON，免费1000次/天）
        try:
            resp = requests.get("https://ipapi.co/json/", timeout=3)
            if resp.status_code == 200:
                j = resp.json()
                city = j.get("city", "")
                region = j.get("region", "")
                country = j.get("country_name", "")
                if city and not city.startswith("{"):
                    logger.info(f"位置(ipapi): {city}, {region}, {country}")
                    return {
                        "city": city, "province": region, "district": "",
                        "adcode": "", "rectangle": f"{j.get('latitude', '')},{j.get('longitude', '')}",
                    }
        except Exception:
            logger.exception("_fallback_ip_api 执行失败")

        # 源2：ip-api.com（JSON，免费无限）
        try:
            resp = requests.get("http://ip-api.com/json/?lang=zh-CN", timeout=3)
            if resp.status_code == 200:
                j = resp.json()
                if j.get("status") == "success":
                    logger.info(f"位置(ip-api): {j.get('city', '')}, {j.get('regionName', '')}")
                    return {
                        "city": j.get("city", ""), "province": j.get("regionName", ""),
                        "district": "", "adcode": "",
                        "rectangle": f"{j.get('lat', '')},{j.get('lon', '')}",
                    }
        except Exception:
            logger.exception("_fallback_ip_api 执行失败")

        return None
    # ------------------------------------------------------------------
    # 周边搜索
    # ------------------------------------------------------------------

    def search_nearby(
        self,
        keywords: str = "餐饮",
        radius: int = 3000,
        limit: int = 5,
        city: str = "",
    ) -> List[Dict[str, Any]]:
        """搜索周边 POI。

        Args:
            keywords: 搜索关键词（如 餐饮|轻食|火锅）
            radius: 搜索半径（米）
            limit: 返回结果数
            city: 城市（为空则使用 IP 定位）

        Returns:
            店铺列表 [{name, address, distance, location, rating, ...}]
        """
        if not self._api_key:
            return []

        # 获取坐标
        location = self.get_location()
        if not location:
            return []

        # 获取城市和坐标
        if not city:
            city = location.get("city", "")
            # IP 定位没有精确坐标，需要地理编码获取
            # 简化版：使用城市名搜索

        # 检查缓存
        cache_key = f"{city}_{keywords}_{radius}"
        cached = self._check_search_cache(cache_key)
        if cached:
            return cached

        # 检查配额
        if not self._check_quota():
            return []

        try:
            params = {
                "key": self._api_key,
                "keywords": keywords,
                "city": city,
                "radius": radius,
                "offset": limit,
                "output": "JSON",
                "extensions": "all",
            }

            # 如果有精确坐标则使用
            rectangle = location.get("rectangle", "")
            if rectangle:
                params["location"] = rectangle.split(";")[0]  # 取矩形中心

            resp = requests.get(
                f"{self._base_url}/place/around" if "location" in params
                else f"{self._base_url}/place/text",
                params=params,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            self._increment_count()

            if data.get("status") == "1":
                pois = data.get("pois", [])
                results = []
                for poi in pois[:limit]:
                    results.append({
                        "name": poi.get("name", ""),
                        "address": poi.get("address", ""),
                        "distance": poi.get("distance", ""),
                        "location": poi.get("location", ""),
                        "rating": poi.get("biz_ext", {}).get("rating", ""),
                        "type": poi.get("type", ""),
                        "tel": poi.get("tel", ""),
                    })

                # 缓存结果
                self._cache_search_result(cache_key, results, ttl_hours=1)

                logger.info(f"周边搜索: {keywords} → {len(results)} 条结果")
                return results
            else:
                logger.warning(f"周边搜索失败: {data.get('info', '')}")
                return []

        except requests.Timeout:
            logger.warning("周边搜索超时")
            return []
        except Exception as e:
            logger.error(f"周边搜索异常: {e}")
            return []

    # ------------------------------------------------------------------
    # 缓存
    # ------------------------------------------------------------------

    def _is_location_cache_valid(self) -> bool:
        """位置缓存是否有效。"""
        if self._location_cache is None or self._location_cache_time is None:
            return False
        elapsed = datetime.now() - self._location_cache_time
        return elapsed < timedelta(hours=self._location_cache_ttl_hours)

    def _check_search_cache(self, key: str) -> Optional[List[Dict]]:
        """检查搜索结果缓存。"""
        try:
            db = registry.get("database")
            if db is None:
                return None

            cursor = db.execute(
                "SELECT result_json, created_at, ttl_seconds FROM search_cache "
                "WHERE query_hash = ?", (self._hash_key(key),)
            )
            row = cursor.fetchone()
            if row:
                result_json, created_at, ttl = row
                created = datetime.fromisoformat(created_at)
                if datetime.now() - created < timedelta(seconds=ttl):
                    return json.loads(result_json)
            return None
        except Exception:
            return None

    def _cache_search_result(self, key: str, results: List[Dict], ttl_hours: int = 1) -> None:
        """缓存搜索结果。"""
        try:
            db = registry.get("database")
            if db is None:
                return
            db.execute(
                "INSERT OR REPLACE INTO search_cache (query_hash, result_json, ttl_seconds) "
                "VALUES (?, ?, ?)",
                (self._hash_key(key), json.dumps(results, ensure_ascii=False), ttl_hours * 3600),
            )
            db.commit()
        except Exception as e:
            logger.debug(f"缓存搜索结果失败: {e}")

    @staticmethod
    def _hash_key(key: str) -> str:
        """SHA256 哈希。"""
        return hashlib.sha256(key.encode()).hexdigest()

    # ------------------------------------------------------------------
    # 用量监控
    # ------------------------------------------------------------------

    def _check_quota(self) -> bool:
        """检查是否超过每日配额。"""
        today = datetime.now().strftime("%Y%m%d")
        if self._daily_date != today:
            self._daily_count = 0
            self._daily_date = today

        if self._daily_count >= self._daily_limit:
            logger.warning(f"高德 API 日配额已用尽 ({self._daily_count}/{self._daily_limit})")
            return False

        # 临近限额警告
        if self._daily_count >= self._daily_limit * 0.9:
            logger.warning(f"高德 API 接近日限额 ({self._daily_count}/{self._daily_limit})")

        return True

    def _increment_count(self) -> None:
        """增加 API 调用计数。"""
        today = datetime.now().strftime("%Y%m%d")
        if self._daily_date != today:
            self._daily_count = 0
            self._daily_date = today

        self._daily_count += 1
        self._save_daily_count()

    def _save_daily_count(self) -> None:
        """保存当日计数到数据库。"""
        try:
            db = registry.get("database")
            if db is None:
                return
            db.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("gaode_daily_count", str(self._daily_count)),
            )
            db.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("gaode_daily_date", self._daily_date),
            )
            db.commit()
        except Exception:
            logger.exception("_save_daily_count 执行失败")

    def _load_daily_count(self) -> None:
        """从数据库加载当日计数。"""
        try:
            db = registry.get("database")
            if db is None:
                return
            today = datetime.now().strftime("%Y%m%d")
            cursor = db.execute(
                "SELECT value FROM app_settings WHERE key = 'gaode_daily_date'"
            )
            row = cursor.fetchone()
            if row and row[0] == today:
                cursor2 = db.execute(
                    "SELECT value FROM app_settings WHERE key = 'gaode_daily_count'"
                )
                row2 = cursor2.fetchone()
                if row2:
                    self._daily_count = int(row2[0])
                    self._daily_date = today
        except Exception:
            logger.exception("_load_daily_count 执行失败")

    def get_quota_status(self) -> Dict[str, Any]:
        """获取配额状态。"""
        return {
            "daily_used": self._daily_count,
            "daily_limit": self._daily_limit,
            "remaining": max(0, self._daily_limit - self._daily_count),
            "location_cache_valid": self._is_location_cache_valid(),
        }

    # ------------------------------------------------------------------
    # 天气（未来扩展）
    # ------------------------------------------------------------------

    def get_weather(self, city: str = "") -> Optional[Dict[str, Any]]:
        """通过 wttr.in 获取天气。"""
        try:
            import requests
            if city:
                resp = requests.get(f"https://wttr.in/{city}?format=%C+%t", timeout=3,
                                   headers={"User-Agent": "curl/7.0"})
            else:
                resp = requests.get("https://wttr.in/?format=%C+%t", timeout=3,
                                   headers={"User-Agent": "curl/7.0"})
            if resp.status_code == 200 and resp.text.strip():
                return {"condition": resp.text.strip()}
        except Exception:
            logger.exception("get_weather 执行失败")
        return None
