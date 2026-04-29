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

import contextlib
import gc
import io
import logging
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.models._ref_audio import prepare_reference_to_file
from app.models.base import GenerateRequest, GenerateResult, TTSModelBase

logger = logging.getLogger(__name__)

# Decoder checkpoint filenames to search (fish-speech model naming changed across versions)
_DECODER_CANDIDATES = [
    "codec.pth",
    "firefly-gan-vq-fsq-8x1024-21hz-generator.pth",
]


class FishSpeechModel(TTSModelBase):
    """Fish Speech — zero-shot voice cloning TTS (v2.0 API)."""

    model_id = "fish-speech-s2"
    model_name = "Fish Audio S2-Pro"
    description = "Fish Audio S2-Pro — zero-shot voice cloning, emotion tags, 80+ languages"
    supports_voice_cloning = True
    supports_streaming = False
    supports_speed = True  # post-processed via librosa.effects.time_stretch
    supported_languages = ["en", "zh", "ja", "ko", "fr", "de", "ar", "es", "ru", "nl"]
    hf_repo = "fishaudio/s2-pro"
    vram_gb_estimate = 22.0
    help_text = (
        "High-quality multilingual TTS (80+ languages). Emotion tags like [happy], [sad]. "
        "Zero-shot voice cloning. Large model (~22 GB VRAM). Non-commercial license."
    )

    def __init__(self) -> None:
        self._engine: Any = None
        self._llama_queue: Any = None
        self._decoder_model: Any = None
        self._device: str = "cuda"
        self._model_path: str = ""

    def load(self, device: str = "cuda") -> None:
        import torch
        import torchaudio

        # Patch for torchaudio 2.10+ which removed list_audio_backends.
        if not hasattr(torchaudio, "list_audio_backends"):
            torchaudio.list_audio_backends = lambda: ["soundfile"]

        # Monkey-patch ReferenceLoader.__init__ to work around a Python scoping bug
        # in fish_speech's reference_loader.py.  The except block in __init__ does
        #   import torchaudio.io._load_audio_fileobj
        # which makes 'torchaudio' a local variable for the entire function, causing
        # an UnboundLocalError on the earlier `torchaudio.list_audio_backends()` call.
        #
        # IMPORTANT: do NOT assign to ``self_ref.encode_reference`` or
        # ``self_ref.decoder_model`` here. Those names are *type annotations* in
        # upstream's __init__ (no runtime assignment) — the actual values come
        # from ``VQManager`` (method) and from the engine's __init__ (attribute).
        # Setting them to ``None`` shadows the real method/attribute on the
        # instance and produces ``TypeError: 'NoneType' object is not callable``
        # the moment a reference clip is encoded — which silently broke voice
        # cloning for every job that supplied a reference.
        from fish_speech.inference_engine import reference_loader as _ref_loader

        def _patched_init(self_ref):
            self_ref.ref_by_id = {}
            self_ref.ref_by_hash = {}
            # Determine backend safely using module-level torchaudio
            _ta = torchaudio
            if hasattr(_ta, "list_audio_backends"):
                try:
                    backends = _ta.list_audio_backends()
                    self_ref.backend = "ffmpeg" if "ffmpeg" in backends else "soundfile"
                except Exception:
                    self_ref.backend = "soundfile"
            else:
                self_ref.backend = "soundfile"

        _ref_loader.ReferenceLoader.__init__ = _patched_init

        # Replace ReferenceLoader.load_audio: upstream calls
        # ``torchaudio.load(path, backend=self.backend)`` which on torchaudio
        # 2.10 routes through the new TorchCodec dispatcher. TorchCodec isn't
        # installed in this image and the call raises ImportError, killing
        # voice-clone jobs at the prompt-encoding step. soundfile + manual
        # resampling reproduces the exact behaviour without that dependency.
        import io as _io

        import soundfile as _sf

        def _patched_load_audio(self_ref, reference_audio, sr):  # noqa: ARG001
            if isinstance(reference_audio, (bytes, bytearray)):
                src = _io.BytesIO(reference_audio)
            elif isinstance(reference_audio, str) and (
                len(reference_audio) > 255 or not Path(reference_audio).exists()
            ):
                src = _io.BytesIO(reference_audio.encode("latin1"))
            else:
                src = reference_audio
            wav, original_sr = _sf.read(src, dtype="float32", always_2d=True)
            # (samples, channels) -> mono (channels-first like torchaudio.load)
            audio = wav.mean(axis=1).astype(np.float32)
            if original_sr != sr:
                import torchaudio.functional as _F  # noqa: N812

                tensor = torch.from_numpy(audio).unsqueeze(0)
                audio = _F.resample(tensor, original_sr, sr).squeeze(0).numpy()
            return audio

        _ref_loader.ReferenceLoader.load_audio = _patched_load_audio

        from fish_speech.inference_engine import TTSInferenceEngine
        from fish_speech.models.dac.inference import load_model as load_decoder_model
        from fish_speech.models.text2semantic.inference import launch_thread_safe_queue

        self._device = device
        self._model_path = settings.FISH_SPEECH_MODEL_PATH
        logger.info("Loading Fish Speech from %s on %s", self._model_path, device)

        # If the configured path is a HuggingFace Hub ID (no local path separator),
        # resolve it to a local snapshot via huggingface_hub. This handles first-run
        # downloads automatically.
        checkpoint_path = self._model_path
        if not Path(checkpoint_path).exists():
            from huggingface_hub import snapshot_download

            logger.info("Downloading Fish Speech model from HuggingFace Hub: %s", checkpoint_path)
            checkpoint_path = snapshot_download(
                repo_id=checkpoint_path,
                repo_type="model",
                ignore_patterns=["*.md", "*.txt"],
            )
            logger.info("Fish Speech model downloaded to: %s", checkpoint_path)

        # Find the decoder .pth file — filename changed between model versions
        decoder_path = None
        for candidate in _DECODER_CANDIDATES:
            p = Path(checkpoint_path) / candidate
            if p.exists():
                decoder_path = str(p)
                break
        if decoder_path is None:
            raise FileNotFoundError(
                f"Could not find Fish Speech decoder in {checkpoint_path}. "
                f"Tried: {_DECODER_CANDIDATES}"
            )

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
        # Signal the background LLM thread to stop (it exits on None sentinel)
        if self._llama_queue is not None:
            with contextlib.suppress(Exception):
                self._llama_queue.put(None)
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

        # Build reference audio list for voice cloning. Pre-clean the reference
        # (mono, 44.1 kHz, trimmed silence, normalized loudness, ≤30s) before
        # handing the bytes to Fish Speech — upstream pairs prompt tokens with
        # prompt texts, so feeding both a clean clip and the transcript is what
        # the inference engine actually expects.
        ref_text = request.extra.get("ref_text", "")
        references: list = []
        if request.voice_id:
            ref_path = Path(request.voice_id)
            if ref_path.exists():
                cleaned_path = prepare_reference_to_file(ref_path, 44100, max_seconds=30)
                references.append(
                    ServeReferenceAudio(
                        audio=cleaned_path.read_bytes(),
                        text=ref_text,
                    )
                )

        tts_kwargs: dict[str, Any] = {
            "text": request.text,
            "references": references,
            "max_new_tokens": 2048,
            "temperature": request.extra.get("temperature", 0.7),
            "top_p": request.extra.get("top_p", 0.8),
            "repetition_penalty": request.extra.get("repetition_penalty", 1.1),
            "format": "wav",
            "streaming": False,
        }
        seed = request.extra.get("seed")
        if seed is not None:
            tts_kwargs["seed"] = int(seed)

        tts_request = ServeTTSRequest(**tts_kwargs)

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

        # Fish Speech doesn't accept a speed kwarg — post-process with
        # librosa.effects.time_stretch on the float audio array (not the bytes)
        # when the request asks for non-1.0 speed.
        if request.speed and abs(request.speed - 1.0) > 1e-3:
            import librosa

            full_audio = librosa.effects.time_stretch(full_audio, rate=request.speed)

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
        ref_path = Path(audio_path)
        if not ref_path.exists():
            raise FileNotFoundError(f"Reference audio not found: {audio_path}")

        return {
            "model_id": self.model_id,
            "reference_audio_path": audio_path,
            "cloning_method": "zero_shot",
        }
