"""Model Manager — singleton that owns GPU model lifecycle.

Only one model is loaded at a time. When a new model is requested the current
model is unloaded, GPU cache is cleared, and the new model is loaded.

Models are automatically unloaded after an idle timeout (default 5 minutes)
to free GPU VRAM for other workers sharing the same GPU.

Usage (inside a Celery task):
    manager = ModelManager.get_instance()
    model = manager.load_model("vibevoice")
    result = model.generate(request)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.base import TTSModelBase

logger = logging.getLogger(__name__)

# Idle timeout in seconds before auto-unloading a model from GPU
MODEL_IDLE_TIMEOUT = int(os.environ.get("MODEL_IDLE_TIMEOUT", "60"))


class ModelManager:
    """Singleton model manager for single-GPU hot-swap with idle unload."""

    _instance: "ModelManager | None" = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self._load_lock = threading.Lock()
        self.current_model_id: str | None = None
        self.current_model: "TTSModelBase | None" = None
        self._loading_model_id: str | None = None
        self._last_used: float = 0.0
        # Registry: model_id → class (not instance)
        self._registry: dict[str, type["TTSModelBase"]] = {}
        self._device: str = "cuda"
        self._register_defaults()
        self._start_idle_timer()

    @classmethod
    def get_instance(cls) -> "ModelManager":
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── Registration ──────────────────────────────────────────────────────────

    def _register_defaults(self) -> None:
        """Register all known model implementations."""
        try:
            from app.models.vibevoice import VibeVoiceModel

            self.register("vibevoice", VibeVoiceModel)
        except ImportError:
            logger.debug("VibeVoice dependencies not installed")

        try:
            from app.models.vibevoice_1p5b import VibeVoice1p5BModel

            self.register("vibevoice-1.5b", VibeVoice1p5BModel)
        except ImportError:
            logger.debug("VibeVoice 1.5B dependencies not installed")

        try:
            from app.models.fish_speech import FishSpeechModel

            self.register("fish-speech-s2", FishSpeechModel)
        except ImportError:
            logger.debug("Fish Speech dependencies not installed")

        try:
            from app.models.kokoro import KokoroModel

            self.register("kokoro", KokoroModel)
        except ImportError:
            logger.debug("Kokoro dependencies not installed")

        try:
            from app.models.qwen3_tts import Qwen3TTSModel

            self.register("qwen3-tts", Qwen3TTSModel)
        except ImportError:
            logger.debug("Qwen3 TTS dependencies not installed")

    def register(self, model_id: str, model_class: type["TTSModelBase"]) -> None:
        self._registry[model_id] = model_class
        logger.info("Registered model: %s", model_id)

    # ── Model loading ──────────────────────────────────────────────────────────

    def load_model(self, model_id: str, device: str | None = None) -> "TTSModelBase":
        """Load model_id, unloading the current model if different.

        Thread-safe via _load_lock (Celery uses concurrency=1 but we protect anyway).
        Returns the loaded model instance.
        """
        device = device or self._device

        with self._load_lock:
            self._last_used = time.monotonic()

            if self.current_model_id == model_id and self.current_model is not None:
                logger.debug("Model %s already loaded", model_id)
                return self.current_model

            if model_id not in self._registry:
                raise ValueError(
                    f"Unknown model: {model_id!r}. Available: {list(self._registry)}"
                )

            # Unload current model
            if self.current_model is not None:
                self._unload_current()

            # Load new model
            logger.info("Loading model %s on device %s", model_id, device)
            self._loading_model_id = model_id
            model_class = self._registry[model_id]
            model = model_class()
            model.load(device=device)
            self.current_model = model
            self.current_model_id = model_id
            self._loading_model_id = None
            self._last_used = time.monotonic()
            logger.info("Model %s loaded successfully", model_id)
            return model

    def _unload_current(self) -> None:
        """Unload the current model and free GPU memory."""
        if self.current_model is None:
            return
        logger.info("Unloading model %s", self.current_model_id)
        try:
            self.current_model.unload()
        except Exception:
            logger.exception("Error unloading model %s", self.current_model_id)
        finally:
            self.current_model = None
            self.current_model_id = None
            self._clear_gpu_cache()

    def _clear_gpu_cache(self) -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("GPU cache cleared")
        except ImportError:
            pass

    def unload_all(self) -> None:
        with self._load_lock:
            self._unload_current()

    # ── Idle auto-unload ─────────────────────────────────────────────────────

    def _start_idle_timer(self) -> None:
        """Start a background thread that unloads models after idle timeout."""
        if MODEL_IDLE_TIMEOUT <= 0:
            logger.info("Model idle unload disabled (MODEL_IDLE_TIMEOUT=0)")
            return

        def _check_idle():
            while True:
                time.sleep(60)  # check every minute
                if self.current_model is None:
                    continue
                idle_seconds = time.monotonic() - self._last_used
                if idle_seconds >= MODEL_IDLE_TIMEOUT:
                    logger.info(
                        "Model %s idle for %.0fs (timeout=%ds), unloading to free GPU",
                        self.current_model_id,
                        idle_seconds,
                        MODEL_IDLE_TIMEOUT,
                    )
                    with self._load_lock:
                        # Double-check after acquiring lock
                        if self.current_model is not None:
                            idle_now = time.monotonic() - self._last_used
                            if idle_now >= MODEL_IDLE_TIMEOUT:
                                self._unload_current()

        t = threading.Thread(target=_check_idle, daemon=True, name="model-idle-timer")
        t.start()
        logger.info("Model idle unload timer started (timeout=%ds)", MODEL_IDLE_TIMEOUT)

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self, model_id: str) -> dict:
        """Return status dict for a specific model."""
        if model_id not in self._registry:
            return {"id": model_id, "status": "unknown"}

        if model_id == self._loading_model_id:
            status = "loading"
        elif model_id == self.current_model_id:
            status = "loaded"
        else:
            status = "available"

        model_class = self._registry[model_id]
        instance = model_class()
        return {**instance.get_info(), "status": status}

    def list_models(self) -> list[dict]:
        """Return status dicts for all registered models."""
        return [self.get_status(mid) for mid in self._registry]

    @property
    def registered_ids(self) -> list[str]:
        return list(self._registry.keys())
