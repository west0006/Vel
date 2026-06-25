"""
模型管理器模块。

负责 LLM、STT、OCR 等模型的按需加载/卸载及显存监控。
nvidia-ml (pynvml) 在初始化时开启一次，进程退出时关闭。
"""

import threading
from enum import Enum
from typing import Any, Callable, Dict, Optional

from core.event_bus import bus, EVENT_SYSTEM_STATUS
from utils.logger import get_logger

logger = get_logger(__name__)


class ModelType(Enum):
    LLM = "llm"
    STT = "stt"
    OCR = "ocr"
    TTS = "tts"


class ModelStatus(Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    UNLOADING = "unloading"


class ModelManager:
    """模型管理器。"""

    VRAM_ESTIMATES: Dict[ModelType, float] = {
        ModelType.LLM: 4.5,
        ModelType.STT: 2.0,
        ModelType.OCR: 1.5,
        ModelType.TTS: 0.5,
    }

    VRAM_SAFE_MARGIN_MB = 800

    def __init__(self):
        self._models: Dict[ModelType, Any] = {}
        self._status: Dict[ModelType, ModelStatus] = {
            t: ModelStatus.UNLOADED for t in ModelType
        }
        self._loaders: Dict[ModelType, Callable[[], Any]] = {}
        self._unloaders: Dict[ModelType, Callable[[Any], None]] = {}
        self._llm_pause_event = threading.Event()
        self._llm_pause_event.set()
        self._lock = threading.RLock()
        self._nvml_ready = False

    def _ensure_nvml(self) -> bool:
        """确保 nvml 已初始化（只初始化一次）。"""
        if self._nvml_ready:
            return True
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_ready = True
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 加载器注册
    # ------------------------------------------------------------------

    def register_loader(self, model_type: ModelType, loader: Callable[[], Any]) -> None:
        with self._lock:
            self._loaders[model_type] = loader

    def register_unloader(self, model_type: ModelType, unloader: Callable[[Any], None]) -> None:
        with self._lock:
            self._unloaders[model_type] = unloader

    # ------------------------------------------------------------------
    # 加载/卸载
    # ------------------------------------------------------------------

    def load(self, model_type: ModelType) -> bool:
        """加载指定模型。若显存不足则返回 False。"""
        with self._lock:
            if self._status[model_type] == ModelStatus.LOADED:
                return True
            if self._status[model_type] == ModelStatus.LOADING:
                return False

            if model_type != ModelType.LLM:
                available = self._get_available_vram_mb()
                estimate_mb = self.VRAM_ESTIMATES.get(model_type, 1024) * 1024
                if available is not None and available < estimate_mb + self.VRAM_SAFE_MARGIN_MB:
                    logger.warning(
                        f"显存不足，无法加载 {model_type.value} "
                        f"(可用: {available:.0f}MB, 需: {estimate_mb:.0f}MB)"
                    )
                    bus.publish(EVENT_SYSTEM_STATUS, {
                        "type": "model_load_fail",
                        "model": model_type.value,
                        "reason": "vram_insufficient",
                    })
                    return False

            self._status[model_type] = ModelStatus.LOADING
            bus.publish(EVENT_SYSTEM_STATUS, {"type": "model_loading", "model": model_type.value})

        try:
            loader = self._loaders.get(model_type)
            if loader is None:
                logger.error(f"模型 {model_type.value} 没有注册加载器")
                self._status[model_type] = ModelStatus.ERROR
                return False

            if model_type != ModelType.LLM:
                self.pause_llm()

            instance = loader()

            with self._lock:
                self._models[model_type] = instance
                self._status[model_type] = ModelStatus.LOADED

            logger.info(f"模型已加载: {model_type.value}")
            bus.publish(EVENT_SYSTEM_STATUS, {"type": "model_loaded", "model": model_type.value})
            return True

        except Exception:
            logger.exception(f"模型加载失败: {model_type.value}")
            self._status[model_type] = ModelStatus.ERROR
            return False

    def unload(self, model_type: ModelType) -> None:
        """卸载指定模型，释放显存。"""
        if model_type == ModelType.LLM:
            logger.warning("LLM 是常驻模型，不允许卸载")
            return

        with self._lock:
            if self._status[model_type] in (ModelStatus.UNLOADED, ModelStatus.UNLOADING):
                return
            self._status[model_type] = ModelStatus.UNLOADING

        try:
            unloader = self._unloaders.get(model_type)
            instance = self._models.get(model_type)
            if unloader and instance:
                unloader(instance)

            with self._lock:
                self._models.pop(model_type, None)
                self._status[model_type] = ModelStatus.UNLOADED

            logger.info(f"模型已卸载: {model_type.value}")
            bus.publish(EVENT_SYSTEM_STATUS, {"type": "model_unloaded", "model": model_type.value})
        except Exception:
            logger.exception(f"模型卸载失败: {model_type.value}")
            self._status[model_type] = ModelStatus.ERROR

    # ------------------------------------------------------------------
    # LLM 推理暂停/恢复
    # ------------------------------------------------------------------

    def pause_llm(self) -> None:
        self._llm_pause_event.clear()

    def resume_llm(self) -> None:
        self._llm_pause_event.set()

    def wait_llm_if_paused(self, timeout: float = 30.0) -> bool:
        return self._llm_pause_event.wait(timeout=timeout)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_model(self, model_type: ModelType) -> Any:
        return self._models.get(model_type)

    def get_status(self, model_type: ModelType) -> ModelStatus:
        return self._status[model_type]

    def is_loaded(self, model_type: ModelType) -> bool:
        return self._status[model_type] == ModelStatus.LOADED

    # ------------------------------------------------------------------
    # 显存监控
    # ------------------------------------------------------------------

    def _get_available_vram_mb(self) -> Optional[float]:
        """获取可用显存（MB），nvml 已全局初始化。"""
        if not self._ensure_nvml():
            return None
        try:
            import pynvml
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return info.free / (1024 * 1024)
        except Exception:
            return None

    def shutdown(self) -> None:
        """关闭模型管理器，释放 nvml。"""
        if self._nvml_ready:
            try:
                import pynvml
                pynvml.nvmlShutdown()
                self._nvml_ready = False
            except Exception:
                pass


model_manager = ModelManager()