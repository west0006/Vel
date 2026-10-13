"""远程文本获取的异步缓存。

**要解决的问题**：天气、一言、周边 POI 等远程数据此前用**同步** ``requests`` 获取
（``timeout`` 3~5s）。这些调用出现在 UI 线程路径上（例如点击桌宠展开对话气泡时
触发 ``greeting.check_and_greet()``）或 ``QtScheduler`` 的主线程任务里（health 模块），
一旦网络慢就会**卡住界面数秒** —— 违反 `AGENTS.md` §4.3「UI 线程单次阻塞不得超过 200ms」。

**做法**：后台线程拉取 → 内存 TTL 缓存 → **UI 线程只读缓存**（永不阻塞）。
缓存未命中时返回 ``None``（调用方降级处理，如问候语不含天气），同时触发一次后台刷新；
下次读取即为就绪值。

本模块位于 ``utils`` 层，只依赖标准库与 ``utils.logger``（AGENTS.md §三 分层边界）。
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

#: 默认缓存有效期（秒）——30 分钟，与天气类数据的合理刷新频率一致
DEFAULT_TTL_SECONDS = 1800
#: 默认请求超时（秒）——仅影响后台线程，不阻塞 UI
DEFAULT_TIMEOUT_SECONDS = 3


class RemoteTextCache:
    """后台拉取 + TTL 缓存的远程文本读取器。

    - ``get()`` 永不阻塞：命中返回文本，未命中返回 ``None``（并可触发后台刷新）；
    - 同一 key 不会并发重复请求（``_pending`` 去重）；
    - 任何网络异常都只记日志并保持旧缓存（或空缓存），不会抛出。
    """

    def __init__(self,
                 ttl_seconds: int = DEFAULT_TTL_SECONDS,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 headers: Optional[Dict[str, str]] = None) -> None:
        """
        Args:
            ttl_seconds: 缓存有效期（秒）。
            timeout: 后台请求超时（秒）。
            headers: 可选请求头（部分服务需要 User-Agent）。
        """
        self._ttl = max(1, int(ttl_seconds))
        self._timeout = float(timeout)
        self._headers = headers or {"User-Agent": "curl/7.0"}
        self._cache: Dict[str, Tuple[float, str]] = {}
        self._pending: set = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get(self, key: str, url: Optional[str] = None) -> Optional[str]:
        """读取缓存文本（**永不阻塞**）。

        Args:
            key: 缓存键，如 ``"weather"``。
            url: 提供时，若缓存未命中/已过期则触发一次后台刷新。

        Returns:
            命中且未过期的文本；否则 ``None``。
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and (time.time() - entry[0]) < self._ttl:
                return entry[1]

        if url:
            self.refresh(key, url)
        return None

    def peek(self, key: str) -> Optional[str]:
        """仅查看缓存，不触发刷新（用于诊断/测试）。"""
        with self._lock:
            entry = self._cache.get(key)
        return entry[1] if entry else None

    def is_stale(self, key: str) -> bool:
        """缓存是否缺失或已过期。"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return True
            return (time.time() - entry[0]) >= self._ttl

    # ------------------------------------------------------------------
    # 写入与刷新
    # ------------------------------------------------------------------

    def put(self, key: str, value: str) -> None:
        """直接写入缓存（供预热或测试使用）。"""
        with self._lock:
            self._cache[key] = (time.time(), value)

    def clear(self) -> None:
        """清空缓存。"""
        with self._lock:
            self._cache.clear()

    def refresh(self, key: str, url: str) -> bool:
        """在后台线程刷新指定 key。

        Args:
            key: 缓存键。
            url: 目标地址。

        Returns:
            是否真正启动了请求（同 key 已有在途请求时返回 ``False``）。
        """
        with self._lock:
            if key in self._pending:
                return False
            self._pending.add(key)
        thread = threading.Thread(
            target=self._fetch, args=(key, url), name=f"remote-text-{key}", daemon=True
        )
        thread.start()
        return True

    def prefetch(self, mapping: Dict[str, str]) -> None:
        """批量触发后台预热（启动时调用，不阻塞）。

        Args:
            mapping: ``{key: url}`` 映射。
        """
        for key, url in mapping.items():
            if self.is_stale(key):
                self.refresh(key, url)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _fetch(self, key: str, url: str) -> None:
        """后台线程体：发起请求并写入缓存。"""
        try:
            import requests

            resp = requests.get(url, timeout=self._timeout, headers=self._headers)
            text = (resp.text or "").strip()
            if resp.status_code == 200 and text:
                with self._lock:
                    self._cache[key] = (time.time(), text)
                logger.debug("远程文本已更新: %s", key)
            else:
                logger.warning("远程文本获取异常: %s status=%s", key, resp.status_code)
        except Exception as exc:                      # noqa: BLE001
            # 网络类失败是可预期的（离线/超时），记 warning 但不影响缓存旧值
            logger.warning("远程文本获取失败: %s (%s)", key, exc)
        finally:
            with self._lock:
                self._pending.discard(key)


#: 进程内共享实例：天气 / 一言 / 周边 POI 共用一个缓存
remote_text = RemoteTextCache()
