"""
联网搜索服务模块。

实现多级搜索降级链：Azure Bing API → SearXNG (本地) → DuckDuckGo。
包含结果缓存、质量检查、用量监控和安全过滤。
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from core.event_bus import bus, EVENT_SYSTEM_STATUS
from core.service_registry import registry
from utils.logger import get_logger

logger = get_logger(__name__)


class SearchService:
    """联网搜索服务。

    三级降级链：
    1. Azure Bing API（主通道，1000次/月免费）
    2. SearXNG（本地 Docker，备用）
    3. DuckDuckGo（HTML 抓取，兜底）

    结果缓存：30分钟（泛化匹配）。
    """

    SAFE_DOMAINS = [
        ".bing.com", ".wikipedia.org", ".baidu.com", ".zhihu.com",
        ".csdn.net", ".jianshu.com", ".github.com", ".stackoverflow.com",
        ".amap.com", ".duckduckgo.com",
        "duckduckgo.com", "www.duckduckgo.com",
    ]

    def __init__(self):
        from core.config import config

        self._bing_key = ""
        self._bing_endpoint = "https://api.bing.microsoft.com/v7.0/search"
        self._bing_timeout = config.get_int("search.bing_timeout", 5)
        self._bing_monthly_limit = config.get_int("search.bing_monthly_limit", 900)

        self._searxng_url = "http://localhost:8080/search"
        self._duckduckgo_url = "https://html.duckduckgo.com/html/"

        self._bing_monthly_count = 0
        self._bing_monthly_month = ""
        self._degraded_to_duckduckgo = False

    def initialize(self) -> bool:
        self._load_config()
        self._load_monthly_count()
        if self._bing_key:
            logger.info("搜索服务已启动 (主通道: Bing API)")
        else:
            logger.warning("Bing API Key 未配置，搜索将直接使用 DuckDuckGo")
            self._degraded_to_duckduckgo = True
        return True

    @staticmethod
    def _config_path() -> str:
        """统一获取 secrets.yaml 路径（兼容 PyInstaller 打包）。"""
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            base = meipass
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "config", "secrets.yaml")

    def _load_config(self) -> None:
        try:
            import yaml
            config_path = self._config_path()
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
                bing = cfg.get("bing", {})
                self._bing_key = bing.get("api_key", "")
                self._bing_endpoint = bing.get("endpoint", self._bing_endpoint)
        except Exception:
            logger.exception("_load_config 执行失败")

        # 检测占位符 / 无效 key，直接跳过 Bing
        if not self._bing_key or "你的" in self._bing_key or len(self._bing_key) < 20:
            logger.warning("Bing API Key 无效或未配置，搜索将直接使用 DuckDuckGo")
            self._degraded_to_duckduckgo = True

    def search(self, query: str, max_results: int = 5) -> str:
        if not query.strip(): return ""
        logger.info(f"搜索查询: {query[:60]}...")
        cached = self._check_cache(query)
        if cached: return cached

        # 1. DDG 库（免费主通道）
        result = self._search_duckduckgo_lib(query, max_results)
        if result: self._save_cache(query, result); return result

        # 2. Bing（有Key才试）
        if not self._degraded_to_duckduckgo:
            result = self._search_bing(query, max_results)
            if result: self._save_cache(query, result); return result

        # 3. SearXNG
        result = self._search_searxng(query, max_results)
        if result: self._save_cache(query, result); return result

        # 4. DDG HTML 兜底
        result = self._search_duckduckgo(query, max_results)
        if result: self._save_cache(query, result); return result

        return "搜索服务暂不可用，请稍后重试 😿"

    def search_raw(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        text = self.search(query, max_results)
        if not text or "暂不可用" in text:
            return []
        return [{"title": "搜索结果", "url": "", "snippet": text[:200]}]

    def _search_bing(self, query: str, count: int = 5) -> Optional[str]:
        if not self._bing_key:
            return None
        if not self._check_bing_quota():
            logger.warning("Bing 月配额已用尽，切换到备用通道")
            self._degraded_to_duckduckgo = True
            return None
        try:
            headers = {"Ocp-Apim-Subscription-Key": self._bing_key}
            params = {"q": query, "count": count, "mkt": "zh-CN", "safeSearch": "Moderate"}
            resp = requests.get(self._bing_endpoint, headers=headers, params=params, timeout=self._bing_timeout)
            if resp.status_code == 200:
                self._increment_bing_count()
                data = resp.json()
                results = data.get("webPages", {}).get("value", [])
                results = self._filter_safe(results)
                if not self._quality_check(results):
                    logger.warning("Bing 结果质量不足，降级")
                    return None
                return self._format_results(results)
            elif resp.status_code in (401, 403):
                logger.error(f"Bing API 认证失败（{resp.status_code}），永久降级到 DuckDuckGo")
                self._degraded_to_duckduckgo = True
                return None
            else:
                logger.warning(f"Bing API 返回 {resp.status_code}")
                return None
        except requests.Timeout:
            logger.warning("Bing 搜索超时")
            return None
        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            logger.warning(f"Bing 搜索编码异常，降级: {e}")
            self._degraded_to_duckduckgo = True
            return None
        except Exception as e:
            logger.error(f"Bing 搜索异常: {e}")
            return None

    def _search_searxng(self, query: str, count: int = 5) -> Optional[str]:
        try:
            resp = requests.get(
                self._searxng_url,
                params={"q": query, "format": "json", "categories": "general"},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])[:count]
                results = self._filter_safe(results)
                if not results:
                    return None
                formatted = []
                for r in results:
                    title = r.get("title", "")
                    snippet = r.get("content", "") or r.get("snippet", "")
                    url = r.get("url", "")
                    formatted.append(f"**{title}**\n{snippet[:200]}\n{url}")
                return "\n\n".join(formatted)
            return None
        except requests.ConnectionError:
            logger.debug("SearXNG 未运行")
            return None
        except Exception as e:
            logger.debug(f"SearXNG 搜索失败: {e}")
            return None

    def _search_duckduckgo(self, query: str, count: int = 5) -> Optional[str]:
        try:
            resp = requests.post(
                self._duckduckgo_url,
                data={"q": query},
                timeout=10,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            )
            if resp.status_code != 200:
                return None

            from html.parser import HTMLParser

            class DDGParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.results = []
                    self._in_result = False
                    self._in_snippet = False
                    self._current_title = ""
                    self._current_snippet = ""
                    self._capture = False

                def handle_starttag(self, tag, attrs):
                    attrs_dict = dict(attrs)
                    cls = attrs_dict.get("class", "")
                    if tag == "a" and "result__a" in cls:
                        self._in_result = True
                        self._current_title = ""
                        self._current_snippet = ""
                    if tag == "span" and "result__snippet" in cls:
                        self._in_snippet = True
                    if self._in_result or self._in_snippet:
                        self._capture = True

                def handle_endtag(self, tag):
                    if tag == "a" and self._in_result:
                        if self._current_title.strip():
                            self.results.append({
                                "title": self._current_title.strip(),
                                "snippet": self._current_snippet.strip(),
                            })
                        self._current_title = ""
                        self._current_snippet = ""
                        self._in_result = False
                    if tag == "span" and self._in_snippet:
                        self._in_snippet = False
                    self._capture = False

                def handle_data(self, data):
                    if self._capture:
                        if self._in_result and not self._in_snippet:
                            self._current_title += data
                        elif self._in_snippet:
                            self._current_snippet += data

            parser = DDGParser()
            parser.feed(resp.text)

            if parser.results:
                logger.info(f"DuckDuckGo 返回 {len(parser.results)} 条结果")
                formatted = []
                for r in parser.results[:count]:
                    formatted.append(f"**{r['title']}**\n{r['snippet'][:200]}")
                return "\n\n".join(formatted)

            return self._search_duckduckgo_lib(query, count)
        except Exception as e:
            logger.error(f"DuckDuckGo 搜索异常: {e}")
            return None

    def _search_duckduckgo_lib(self, query: str, count: int = 5) -> Optional[str]:
        """通过 ddgs / duckduckgo_search 包兜底。"""
        DDGS = None
        # 优先新包名 ddgs
        try:
            from ddgs import DDGS as DDGS_new
            DDGS = DDGS_new
        except ImportError:
            logger.exception("_search_duckduckgo_lib 执行失败")
        # 回退旧包名，抑制弃用警告
        if DDGS is None:
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    from duckduckgo_search import DDGS
            except ImportError:
                return self._search_duckduckgo_api(query, count)

    def _search_duckduckgo_api(self, query: str, count: int = 5) -> Optional[str]:
        try:
            resp = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                abstract = data.get("AbstractText", "")
                if abstract:
                    return f"**{data.get('Heading', query)}**\n{abstract[:500]}"
                related = data.get("RelatedTopics", [])
                if related:
                    items = []
                    for r in related[:count]:
                        if isinstance(r, dict):
                            items.append(f"- {r.get('Text', '')[:200]}")
                    return "\n".join(items) if items else None
            return None
        except Exception:
            return None

    def _check_cache(self, query: str) -> Optional[str]:
        try:
            db = registry.get("database")
            if db is None:
                return None
            generalized = self._generalize_query(query)
            query_hash = self._hash(generalized)
            cursor = db.execute(
                "SELECT result_json, created_at, ttl_seconds FROM search_cache WHERE query_hash = ?",
                (query_hash,)
            )
            row = cursor.fetchone()
            if row:
                result_json, created_at, ttl = row
                created = datetime.fromisoformat(created_at)
                if datetime.now() - created < timedelta(seconds=ttl):
                    return result_json
            return None
        except Exception:
            return None

    def _save_cache(self, query: str, result: str) -> None:
        try:
            db = registry.get("database")
            if db is None:
                return
            generalized = self._generalize_query(query)
            query_hash = self._hash(generalized)
            db.execute(
                "INSERT OR REPLACE INTO search_cache (query_hash, result_json, ttl_seconds) VALUES (?, ?, ?)",
                (query_hash, result, 1800),
            )
            db.commit()
        except Exception as e:
            logger.debug(f"搜索缓存保存失败: {e}")

    def _generalize_query(self, query: str) -> str:
        import re
        cleaned = re.sub(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', '', query)
        cleaned = re.sub(r'\d{1,2}月\d{1,2}[日号]', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned[:60]

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _format_results(self, results: List[Dict]) -> str:
        parts = []
        for i, r in enumerate(results, 1):
            title = r.get("name", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            parts.append(f"{i}. **{title}**\n{snippet[:200]}\n{url}")
        return "\n\n".join(parts)

    def _quality_check(self, results: List[Dict]) -> bool:
        count = sum(1 for r in results if r.get("snippet", "").strip())
        return count >= 2

    def _is_safe_url(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return any(domain.endswith(d) for d in self.SAFE_DOMAINS)

    def _filter_safe(self, results: List[Dict]) -> List[Dict]:
        return [r for r in results if self._is_safe_url(r.get("url", ""))]

    def _check_bing_quota(self) -> bool:
        month = datetime.now().strftime("%Y%m")
        if self._bing_monthly_month != month:
            self._bing_monthly_count = 0
            self._bing_monthly_month = month
        return self._bing_monthly_count < self._bing_monthly_limit

    def _increment_bing_count(self) -> None:
        month = datetime.now().strftime("%Y%m")
        if self._bing_monthly_month != month:
            self._bing_monthly_count = 0
            self._bing_monthly_month = month
        self._bing_monthly_count += 1
        self._save_monthly_count()

    def _save_monthly_count(self) -> None:
        try:
            db = registry.get("database")
            if db:
                db.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                    ("bing_monthly_count", str(self._bing_monthly_count)),
                )
                db.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                    ("bing_monthly_month", self._bing_monthly_month),
                )
                db.commit()
        except Exception:
            logger.exception("_save_monthly_count 执行失败")

    def _load_monthly_count(self) -> None:
        try:
            db = registry.get("database")
            if db is None:
                return
            month = datetime.now().strftime("%Y%m")
            cursor = db.execute("SELECT value FROM app_settings WHERE key = 'bing_monthly_month'")
            row = cursor.fetchone()
            if row and row[0] == month:
                cursor2 = db.execute("SELECT value FROM app_settings WHERE key = 'bing_monthly_count'")
                row2 = cursor2.fetchone()
                if row2:
                    self._bing_monthly_count = int(row2[0])
                    self._bing_monthly_month = month
        except Exception:
            logger.exception("_load_monthly_count 执行失败")

    def get_quota_status(self) -> Dict[str, Any]:
        return {
            "bing_monthly_used": self._bing_monthly_count,
            "bing_monthly_limit": self._bing_monthly_limit,
            "degraded": self._degraded_to_duckduckgo,
        }

    def needs_search(self, user_input: str) -> bool:
        search_triggers = [
            "天气", "新闻", "热搜", "股价", "比赛", "排名",
            "搜索", "帮我搜", "查一下", "查查",
        ]
        return any(trigger in user_input for trigger in search_triggers)

    def format_for_chat(self, query: str, search_result: str) -> str:
        if not search_result or "暂不可用" in search_result:
            return ""
        return f"\n\n【搜索结果（关于'{query}'）】\n{search_result}\n\n请根据以上搜索结果回答用户。如果搜索结果不相关，可以忽略。"
