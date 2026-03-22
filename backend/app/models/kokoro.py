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
    "ko-female-1": "kf_alpha",  # Korean female
    "zh-female-1": "zf_xiaobai",  # Chinese female
}

DEFAULT_VOICE = "en-female-1"


class KokoroModel(TTSModelBase):
    model_id = "kokoro"
    model_name = "Kokoro 82M"
    description = "Lightweight StyleTTS2-derived model with 50+ preset voices — fast, < 1 GB VRAM"
    supports_voice_cloning = False
    supports_streaming = False
    supported_languages = ["en", "fr", "ja", "ko", "zh", "hi", "pt", "it", "es", "pl"]
    hf_repo = "hexgrad/Kokoro-82M"
    vram_gb_estimate = 0.5

    def __init__(self) -> None:
        self._pipeline = None

    def load(self, device: str = "cuda") -> None:
        logger.info("Loading Kokoro on %s", device)
        try:
            from kokoro import KPipeline

            self._pipeline = KPipeline(lang_code="a", device=device)
            self._loaded = True
            logger.info("Kokoro loaded")
        except ImportError:
            logger.warning(
                "kokoro package not installed. Install with: pip install kokoro soundfile"
            )
            self._pipeline = None
            self._loaded = True

    def unload(self) -> None:
        del self._pipeline
        self._pipeline = None
        self._loaded = False

    def generate(self, request: GenerateRequest) -> GenerateResult:
        if not self._loaded:
            raise RuntimeError("Kokoro is not loaded")
        if self._pipeline is None:
            raise RuntimeError("kokoro package not installed. Run: pip install kokoro")

        import numpy as np
        import soundfile as sf

        voice_key = request.voice_id or DEFAULT_VOICE
        kokoro_voice = KOKORO_VOICES.get(voice_key, KOKORO_VOICES[DEFAULT_VOICE])

        samples = []
        sample_rate = 24000
        for _, _, audio in self._pipeline(request.text, voice=kokoro_voice, speed=request.speed):
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
