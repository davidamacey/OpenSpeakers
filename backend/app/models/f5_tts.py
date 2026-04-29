"""F5-TTS model — flow matching, zero-shot cloning, 15x realtime.

Install: pip install f5-tts
HuggingFace: SWivid/F5-TTS
"""

from __future__ import annotations

import io
import logging
import wave
from pathlib import Path

from app.core.config import settings
from app.models._ref_audio import prepare_reference_to_file
from app.models.base import GenerateRequest, GenerateResult, TTSModelBase

logger = logging.getLogger(__name__)


class F5TTSModel(TTSModelBase):
    model_id = "f5-tts"
    model_name = "F5-TTS"
    description = "Flow-matching TTS with zero-shot cloning and 15x realtime speed — MIT license"
    supports_voice_cloning = True
    supports_streaming = False
    supports_speed = True
    supported_languages = ["en", "zh", "de", "fr", "es", "pt", "hi", "ar", "ru", "ja", "ko", "nl"]
    hf_repo = "SWivid/F5-TTS"
    vram_gb_estimate = 3.0
    help_text = (
        "Fast flow-matching TTS (15x realtime). Reference-audio voice cloning. "
        "MIT license. English focused. Requires reference audio for best results."
    )

    def __init__(self) -> None:
        self._model = None
        self._device = "cuda"

    def load(self, device: str = "cuda") -> None:
        logger.info("Loading F5-TTS on %s", device)
        self._device = device
        from f5_tts.api import F5TTS

        self._model = F5TTS(device=device)
        self._loaded = True
        logger.info("F5-TTS loaded on %s", device)

    def unload(self) -> None:
        self._model = None
        self._loaded = False
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    # Default reference audio bundled with the f5-tts package
    _DEFAULT_REF_AUDIO = (
        "/usr/local/lib/python3.12/site-packages/f5_tts/infer/examples/basic/basic_ref_en.wav"
    )
    _DEFAULT_REF_TEXT = "Some call me nature, others call me mother nature."

    def generate(self, request: GenerateRequest) -> GenerateResult:
        if not self._loaded or self._model is None:
            raise RuntimeError("F5-TTS is not loaded")

        import numpy as np

        # voice_id is a path to a reference audio file; fall back to bundled example
        ref_file = None
        ref_text = request.extra.get("ref_text", "")
        using_user_ref = False
        if request.voice_id and Path(request.voice_id).exists():
            ref_file = request.voice_id
            using_user_ref = True
        elif Path(self._DEFAULT_REF_AUDIO).exists():
            ref_file = self._DEFAULT_REF_AUDIO
            # Provide the known transcription to avoid Whisper download
            if not ref_text:
                ref_text = self._DEFAULT_REF_TEXT
        else:
            raise RuntimeError(
                "F5-TTS requires a reference audio file. "
                "Pass voice_id pointing to a WAV/MP3 file, or use a cloned voice profile."
            )

        # If we're on a user-uploaded reference with no transcript, decide whether
        # we're allowed to fall back to F5's internal Whisper transcription pass.
        # The setting may not exist on older configs — graceful degrade to True.
        auto_transcribe = bool(getattr(settings, "F5_TTS_AUTO_TRANSCRIBE", True))
        if using_user_ref and not ref_text:
            if not auto_transcribe:
                raise RuntimeError("F5-TTS requires reference_text — auto-transcribe is disabled.")
            logger.warning(
                "F5-TTS: no reference_text provided; upstream will run Whisper "
                "auto-transcribe (slow on first call, downloads weights)."
            )

        # Pre-clean the reference (mono, 24 kHz, trimmed silence, normalized
        # loudness, ≤12s) — F5-TTS hard-clips at 12s anyway.
        cleaned_path = prepare_reference_to_file(ref_file, 24000, max_seconds=12)

        wav, sr, _ = self._model.infer(
            ref_file=str(cleaned_path),
            ref_text=ref_text,
            gen_text=request.text,
            nfe_step=int(request.extra.get("nfe_step", 32)),
            cfg_strength=float(request.extra.get("cfg_strength", 2.0)),
            sway_sampling_coef=float(request.extra.get("sway_sampling_coef", -1.0)),
            speed=request.speed,
            target_rms=float(request.extra.get("target_rms", 0.1)),
            cross_fade_duration=float(request.extra.get("cross_fade_duration", 0.15)),
            remove_silence=bool(request.extra.get("remove_silence", False)),
            seed=request.extra.get("seed"),
        )

        duration = len(wav) / sr if hasattr(wav, "__len__") else 0.0

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            # Convert float32 to int16 if needed
            if hasattr(wav, "dtype") and wav.dtype != np.int16:
                wav_int16 = (wav * 32767).astype(np.int16)
            else:
                wav_int16 = wav
            wf.writeframes(wav_int16.tobytes())
        buf.seek(0)

        return GenerateResult(
            audio_bytes=buf.getvalue(),
            sample_rate=sr,
            duration_seconds=duration,
            format="wav",
        )

    def clone_voice(self, audio_path: str, name: str = "") -> dict:  # noqa: ARG002
        """F5-TTS uses direct reference audio — no separate embedding step needed."""
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Reference audio not found: {audio_path}")
        return {"reference_audio_path": audio_path, "model": self.model_id}
