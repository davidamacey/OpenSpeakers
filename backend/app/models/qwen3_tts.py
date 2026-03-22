"""Qwen3 TTS model implementation.

Model variants (Qwen/Qwen3-TTS-12Hz-*):
  - 1.7B-CustomVoice: 9 built-in speakers, instruction-based style control
  - 1.7B-Base: Voice cloning from 3s reference audio
  - 0.6B variants also available (lighter weight)

Install: pip install qwen-tts

References:
  https://github.com/QwenLM/Qwen3-TTS
  https://huggingface.co/collections/Qwen/qwen3-tts
"""

from __future__ import annotations

import gc
import io
import logging
from typing import Any

import numpy as np

from app.models.base import GenerateRequest, GenerateResult, TTSModelBase

logger = logging.getLogger(__name__)

# Built-in speakers for the CustomVoice variant
QWEN3_BUILTIN_SPEAKERS: dict[str, dict[str, str]] = {
    "Ryan": {"name": "Ryan", "language": "English"},
    "Aiden": {"name": "Aiden", "language": "English"},
    "Vivian": {"name": "Vivian", "language": "Chinese"},
    "Serena": {"name": "Serena", "language": "Chinese"},
    "Uncle_Fu": {"name": "Uncle_Fu", "language": "Chinese"},
    "Dylan": {"name": "Dylan", "language": "Chinese"},
    "Eric": {"name": "Eric", "language": "Chinese"},
    "Ono_Anna": {"name": "Ono_Anna", "language": "Japanese"},
    "Sohee": {"name": "Sohee", "language": "Korean"},
}

# Map our language codes to Qwen3 TTS language names
LANG_CODE_MAP: dict[str, str] = {
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}

DEFAULT_SPEAKER = "Ryan"


class Qwen3TTSModel(TTSModelBase):
    """Qwen3 TTS — multilingual TTS with built-in speakers and voice cloning."""

    model_id = "qwen3-tts"
    model_name = "Qwen3 TTS 1.7B"
    description = "Alibaba Qwen3 TTS — multilingual, expressive, with voice cloning"
    supports_voice_cloning = True
    supports_streaming = False
    supported_languages = ["en", "zh", "ja", "ko", "fr", "de", "es", "pt", "it", "ru"]
    hf_repo = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    vram_gb_estimate = 10.0

    def __init__(self) -> None:
        self._custom_voice_model: Any = None
        self._clone_model: Any = None
        self._device: str = "cuda"

    def load(self, device: str = "cuda") -> None:
        import torch
        from qwen_tts import Qwen3TTSModel as QwenModel

        self._device = device
        logger.info("Loading Qwen3 TTS CustomVoice on %s", device)

        # Determine attention implementation
        attn_impl = "flash_attention_2"
        try:
            import flash_attn  # noqa: F401
        except ImportError:
            attn_impl = "sdpa"
            logger.info("flash-attn not available, using sdpa for Qwen3 TTS")

        # Load CustomVoice model (built-in speakers with style control)
        self._custom_voice_model = QwenModel.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
            device_map=device,
            dtype=torch.bfloat16,
            attn_implementation=attn_impl,
        )

        self._loaded = True
        logger.info("Qwen3 TTS loaded (%.1f GB VRAM estimate)", self.vram_gb_estimate)

    def unload(self) -> None:
        del self._custom_voice_model
        del self._clone_model
        self._custom_voice_model = None
        self._clone_model = None
        self._loaded = False
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def generate(self, request: GenerateRequest) -> GenerateResult:
        import soundfile as sf

        if not self._loaded or self._custom_voice_model is None:
            raise RuntimeError("Qwen3 TTS is not loaded")

        language = LANG_CODE_MAP.get(request.language, "English")

        # Check if voice_id is a file path (voice cloning)
        if request.voice_id and self._is_audio_file(request.voice_id):
            return self._generate_clone(request, language)

        # Use built-in speaker (CustomVoice model)
        speaker = self._resolve_speaker(request.voice_id)
        instruct = request.extra.get("instruct", "")

        logger.debug(
            "Qwen3 TTS generating: speaker=%s, language=%s, text=%d chars",
            speaker,
            language,
            len(request.text),
        )

        wavs, sample_rate = self._custom_voice_model.generate_custom_voice(
            text=request.text,
            language=language,
            speaker=speaker,
            instruct=instruct,
        )

        if not wavs or len(wavs[0]) == 0:
            raise RuntimeError("Qwen3 TTS generated no audio output")

        audio_np = self._to_float32_numpy(wavs[0])
        duration = len(audio_np) / sample_rate

        buf = io.BytesIO()
        sf.write(buf, audio_np, sample_rate, format="WAV")

        return GenerateResult(
            audio_bytes=buf.getvalue(),
            sample_rate=sample_rate,
            duration_seconds=duration,
            format="wav",
        )

    def _generate_clone(
        self, request: GenerateRequest, language: str
    ) -> GenerateResult:
        """Generate speech using voice cloning from reference audio."""
        import soundfile as sf
        import torch
        from qwen_tts import Qwen3TTSModel as QwenModel

        # Lazy-load the Base (cloning) model if not already loaded
        if self._clone_model is None:
            attn_impl = "flash_attention_2"
            try:
                import flash_attn  # noqa: F401
            except ImportError:
                attn_impl = "sdpa"

            logger.info("Loading Qwen3 TTS Base model for voice cloning…")
            self._clone_model = QwenModel.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                device_map=self._device,
                dtype=torch.bfloat16,
                attn_implementation=attn_impl,
            )

        ref_text = request.extra.get("ref_text", "")

        wavs, sample_rate = self._clone_model.generate_voice_clone(
            text=request.text,
            language=language,
            ref_audio=request.voice_id,
            ref_text=ref_text,
        )

        if not wavs or len(wavs[0]) == 0:
            raise RuntimeError("Qwen3 TTS clone generation produced no audio")

        audio_np = self._to_float32_numpy(wavs[0])
        duration = len(audio_np) / sample_rate

        buf = io.BytesIO()
        sf.write(buf, audio_np, sample_rate, format="WAV")

        return GenerateResult(
            audio_bytes=buf.getvalue(),
            sample_rate=sample_rate,
            duration_seconds=duration,
            format="wav",
        )

    def clone_voice(self, audio_path: str, name: str) -> dict:
        """Qwen3 TTS performs zero-shot cloning at inference time.

        We just store the reference audio path — the cloning happens
        when generate() is called with the voice_id pointing to the audio.
        """
        logger.info("Preparing Qwen3 TTS voice profile from %s", audio_path)
        return {
            "model_id": self.model_id,
            "reference_audio_path": audio_path,
            "cloning_method": "zero_shot",
        }

    def _resolve_speaker(self, voice_id: str | None) -> str:
        """Resolve a voice_id to a Qwen3 built-in speaker name."""
        if voice_id is None:
            return DEFAULT_SPEAKER

        # Direct match
        if voice_id in QWEN3_BUILTIN_SPEAKERS:
            return voice_id

        # Case-insensitive match
        for name in QWEN3_BUILTIN_SPEAKERS:
            if name.lower() == voice_id.lower():
                return name

        logger.warning(
            "Speaker %r not found, using default %s", voice_id, DEFAULT_SPEAKER
        )
        return DEFAULT_SPEAKER

    @staticmethod
    def _to_float32_numpy(audio) -> np.ndarray:
        """Convert audio output (bf16/fp16 tensor or list) to float32 numpy array."""
        import torch

        if isinstance(audio, torch.Tensor):
            return audio.cpu().float().numpy()
        return np.array(audio, dtype=np.float32)

    @staticmethod
    def _is_audio_file(path: str) -> bool:
        """Check if the path looks like an audio file."""
        from pathlib import Path

        p = Path(path)
        return p.exists() and p.suffix.lower() in {
            ".wav",
            ".mp3",
            ".flac",
            ".ogg",
            ".m4a",
        }
