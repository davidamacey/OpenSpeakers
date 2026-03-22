"""Fish Speech TTS model implementation.

Model: fishaudio/fish-speech-1.5
  - DAC codec + DualAR LLM + decoder
  - Voice cloning from 3-10 second reference clips (zero-shot)
  - Multi-language, high quality

Fish Speech v2.0 API:
  - TTSInferenceEngine.inference(ServeTTSRequest) -> Generator[InferenceResult]
  - InferenceResult: code="header"|"segment"|"final"|"error", audio=(sr, np.ndarray)
  - launch_thread_safe_queue for the LLM backend
  - load_model from fish_speech.models.dac.inference for the DAC decoder

References:
  https://github.com/fishaudio/fish-speech
"""

from __future__ import annotations

import gc
import io
import logging
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.models.base import GenerateRequest, GenerateResult, TTSModelBase

logger = logging.getLogger(__name__)

# Decoder checkpoint filename in the model directory
DECODER_FILENAME = "codec.pth"


class FishSpeechModel(TTSModelBase):
    """Fish Speech — zero-shot voice cloning TTS (v2.0 API)."""

    model_id = "fish-speech-s2"
    model_name = "Fish Audio S2-Pro"
    description = "Fish Audio S2-Pro — zero-shot voice cloning, emotion tags, 80+ languages"
    supports_voice_cloning = True
    supports_streaming = True
    supported_languages = ["en", "zh", "ja", "ko", "fr", "de", "ar", "es", "ru", "nl"]
    hf_repo = "fishaudio/s2-pro"
    vram_gb_estimate = 8.0

    def __init__(self) -> None:
        self._engine: Any = None
        self._llama_queue: Any = None
        self._decoder_model: Any = None
        self._device: str = "cuda"
        self._model_path: str = ""

    def load(self, device: str = "cuda") -> None:
        import torch
        import torchaudio

        # Patch for torchaudio 2.10+ which removed list_audio_backends
        if not hasattr(torchaudio, "list_audio_backends"):
            torchaudio.list_audio_backends = lambda: ["soundfile"]

        from fish_speech.inference_engine import TTSInferenceEngine
        from fish_speech.models.dac.inference import load_model as load_decoder_model
        from fish_speech.models.text2semantic.inference import launch_thread_safe_queue

        self._device = device
        self._model_path = settings.FISH_SPEECH_MODEL_PATH
        logger.info("Loading Fish Speech from %s on %s", self._model_path, device)

        checkpoint_path = self._model_path
        decoder_path = str(Path(checkpoint_path) / DECODER_FILENAME)

        logger.info("Launching Fish Speech LLM queue...")
        self._llama_queue = launch_thread_safe_queue(
            checkpoint_path=checkpoint_path,
            device=device,
            precision=torch.float16,
            compile=False,
        )

        logger.info("Loading Fish Speech DAC decoder from %s...", decoder_path)
        self._decoder_model = load_decoder_model(
            config_name="modded_dac_vq",
            checkpoint_path=decoder_path,
            device=device,
        )

        self._engine = TTSInferenceEngine(
            llama_queue=self._llama_queue,
            decoder_model=self._decoder_model,
            precision=torch.float16,
            compile=False,
        )

        self._loaded = True
        logger.info("Fish Speech loaded (%.1f GB VRAM estimate)", self.vram_gb_estimate)

    def unload(self) -> None:
        del self._engine
        del self._llama_queue
        del self._decoder_model
        self._engine = None
        self._llama_queue = None
        self._decoder_model = None
        self._loaded = False
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def generate(self, request: GenerateRequest) -> GenerateResult:
        """Synthesize speech using Fish Speech TTSInferenceEngine."""
        import soundfile as sf
        from fish_speech.utils.schema import ServeReferenceAudio, ServeTTSRequest

        if not self._loaded or self._engine is None:
            raise RuntimeError("Fish Speech is not loaded")

        # Build reference audio list for voice cloning
        references: list = []
        if request.voice_id:
            ref_path = Path(request.voice_id)
            if ref_path.exists():
                references.append(
                    ServeReferenceAudio(
                        audio=ref_path.read_bytes(),
                        text="",
                    )
                )

        tts_request = ServeTTSRequest(
            text=request.text,
            references=references,
            max_new_tokens=2048,
            temperature=request.extra.get("temperature", 0.7),
            top_p=request.extra.get("top_p", 0.8),
            repetition_penalty=request.extra.get("repetition_penalty", 1.1),
            format="wav",
            streaming=False,
        )

        # Collect audio segments from the generator
        # InferenceResult: code="header"|"segment"|"final"|"error"
        #                  audio=(sample_rate, np.ndarray) or None
        audio_segments: list[np.ndarray] = []
        sample_rate = 44100

        for result in self._engine.inference(tts_request):
            if result.code == "error":
                raise RuntimeError(f"Fish Speech generation error: {result.error}")
            if result.code == "header" and result.audio:
                sample_rate = result.audio[0]
            elif result.code in ("segment", "final") and result.audio:
                sr, audio_data = result.audio
                sample_rate = sr
                if isinstance(audio_data, np.ndarray) and audio_data.size > 0:
                    audio_segments.append(audio_data)

        if not audio_segments:
            raise RuntimeError("Fish Speech generated no audio output")

        # Concatenate all segments
        full_audio = np.concatenate(audio_segments)
        if full_audio.dtype != np.float32:
            full_audio = full_audio.astype(np.float32)

        duration = len(full_audio) / sample_rate

        buf = io.BytesIO()
        sf.write(buf, full_audio, sample_rate, format="WAV")
        audio_bytes = buf.getvalue()

        return GenerateResult(
            audio_bytes=audio_bytes,
            sample_rate=sample_rate,
            duration_seconds=duration,
            format="wav",
        )

    def clone_voice(self, audio_path: str, _name: str) -> dict:
        """Fish Speech performs zero-shot cloning at inference time.

        No separate embedding extraction needed — the reference audio path
        is stored and passed at generation time.
        """
        return {
            "model_id": self.model_id,
            "reference_audio_path": audio_path,
            "cloning_method": "zero_shot",
        }
