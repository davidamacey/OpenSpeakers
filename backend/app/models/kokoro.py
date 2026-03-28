"""Kokoro TTS model implementation.

Model: hexgrad/Kokoro-82M
  - Very small (82M params), fast inference, < 1 GB VRAM
  - No voice cloning — uses 50+ preset voices
  - Good for testing hot-swap behavior with minimal VRAM

Install: pip install kokoro soundfile
"""

from __future__ import annotations

import io
import logging
from typing import Any

from app.models.base import GenerateRequest, GenerateResult, TTSModelBase

logger = logging.getLogger(__name__)

# A selection of the best Kokoro voices across languages
KOKORO_VOICES: dict[str, str] = {
    "en-female-1": "af_heart",  # American English female
    "en-male-1": "am_michael",  # American English male
    "en-female-2": "bf_emma",  # British English female
    "en-male-2": "bm_george",  # British English male
    "fr-female-1": "ff_siwis",  # French female
    "ja-female-1": "jf_alpha",  # Japanese female
    # Note: no native Korean voices in hexgrad/Kokoro-82M; ko is handled via pipeline fallback
    "zh-female-1": "zf_xiaobei",  # Chinese female (xiaobei, not xiaobai)
}

DEFAULT_VOICE = "en-female-1"

# Map our BCP-47 language codes to Kokoro pipeline lang_codes
LANG_TO_KOKORO: dict[str, str] = {
    "en": "a",
    "fr": "f",
    "ja": "j",
    "ko": "a",  # not natively supported, fallback to English
    "zh": "z",
    "hi": "h",
    "pt": "p",
    "it": "i",
    "es": "e",
    "pl": "a",  # not natively supported, fallback to English
}


class KokoroModel(TTSModelBase):
    model_id = "kokoro"
    model_name = "Kokoro 82M"
    description = "Lightweight StyleTTS2-derived model with 50+ preset voices — fast, < 1 GB VRAM"
    supports_voice_cloning = False
    supports_streaming = False
    supports_speed = True
    supported_languages = ["en", "fr", "ja", "ko", "zh", "hi", "pt", "it", "es", "pl"]
    hf_repo = "hexgrad/Kokoro-82M"
    vram_gb_estimate = 0.5

    def __init__(self) -> None:
        self._pipelines: dict[str, Any] = {}  # lang_code -> KPipeline
        self._device: str = "cuda"

    def load(self, device: str = "cuda") -> None:
        import torch

        # Kokoro's KPipeline raises RuntimeError if device="cuda" but CUDA unavailable.
        # Fall back to CPU automatically rather than crashing the worker.
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available — falling back to CPU for Kokoro")
            device = "cpu"

        logger.info("Loading Kokoro on %s", device)
        self._device = device
        try:
            from kokoro import KPipeline

            # Create default American English pipeline (internally creates KModel)
            self._pipelines["a"] = KPipeline(lang_code="a", device=device)
            self._loaded = True
            logger.info("Kokoro loaded on %s", device)
        except ImportError:
            logger.warning(
                "kokoro package not installed. Install with: pip install kokoro soundfile"
            )
            self._loaded = False

    def unload(self) -> None:
        import torch

        self._pipelines.clear()
        self._loaded = False
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def generate(self, request: GenerateRequest) -> GenerateResult:
        if not self._loaded:
            raise RuntimeError("Kokoro is not loaded")
        if not self._pipelines:
            raise RuntimeError("kokoro package not installed. Run: pip install kokoro")

        import numpy as np
        import soundfile as sf

        voice_key = request.voice_id or DEFAULT_VOICE
        # Allow raw kokoro voice names (e.g. "af_heart") as well as our slugs
        kokoro_voice = KOKORO_VOICES.get(voice_key, voice_key)

        # Determine the correct language pipeline
        pipeline = self._get_pipeline(kokoro_voice, request.language)

        samples = []
        sample_rate = 24000
        for _, _, audio in pipeline(request.text, voice=kokoro_voice, speed=request.speed):
            samples.append(audio)

        audio_np = np.concatenate(samples) if samples else np.zeros(0, dtype=np.float32)
        duration = len(audio_np) / sample_rate

        buf = io.BytesIO()
        sf.write(buf, audio_np, sample_rate, format="WAV")

        return GenerateResult(
            audio_bytes=buf.getvalue(),
            sample_rate=sample_rate,
            duration_seconds=duration,
            format="wav",
        )

    def _get_pipeline(self, kokoro_voice: str, language: str):
        """Get or create a KPipeline for the appropriate language.

        Kokoro voice names encode language as the first letter (e.g. "af_heart"
        -> "a" for American English). We use this to select the right G2P
        pipeline. Each pipeline shares the same KModel to avoid duplicate
        weight loading.
        """
        # Voice names encode language as first letter
        voice_lang = kokoro_voice[0] if kokoro_voice else "a"
        # Use voice language if it looks valid, otherwise fall back to request language
        lang_code = (
            voice_lang
            if voice_lang in LANG_TO_KOKORO.values()
            else LANG_TO_KOKORO.get(language, "a")
        )

        if lang_code in self._pipelines:
            return self._pipelines[lang_code]

        # Create a new pipeline for this language, sharing the model
        try:
            from kokoro import KPipeline

            # Share the KModel from the default English pipeline
            shared_model = self._pipelines["a"].model
            pipeline = KPipeline(lang_code=lang_code, model=shared_model)
            self._pipelines[lang_code] = pipeline
            logger.info("Created Kokoro pipeline for lang_code=%s", lang_code)
            return pipeline
        except Exception as exc:
            logger.warning(
                "Failed to create %s pipeline (%s), falling back to English",
                lang_code,
                exc,
            )
            return self._pipelines["a"]
