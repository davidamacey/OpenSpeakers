"""VibeVoice TTS 1.5B model implementation.

Model: microsoft/VibeVoice-1.5B
  - Long-form multi-speaker TTS (up to 90 min)
  - Zero-shot voice cloning via voice_samples parameter
  - Not real-time (batch generation)

Based on the davidamacey/VibeVoice fork which restores the TTS inference code.
Reference: /mnt/nvm/repos/VibeVoice/docs/vibevoice-1.5b-inference.md
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.models.base import GenerateRequest, GenerateResult, TTSModelBase

logger = logging.getLogger(__name__)


class VibeVoice1p5BModel(TTSModelBase):
    model_id = "vibevoice-1.5b"
    model_name = "VibeVoice TTS 1.5B"
    description = (
        "Microsoft VibeVoice 1.5B — zero-shot voice cloning, "
        "multi-speaker, long-form TTS (up to 90 min)"
    )
    supports_voice_cloning = True
    supports_streaming = False
    supported_languages = [
        "en",
        "zh",
        "de",
        "fr",
        "es",
        "it",
        "pt",
        "nl",
        "ja",
        "ko",
    ]
    hf_repo = "microsoft/VibeVoice-1.5B"
    vram_gb_estimate = 12.0

    SAMPLE_RATE = 24_000

    def __init__(self) -> None:
        self._model = None
        self._processor = None
        self._device: str = "cuda"

    def load(self, device: str = "cuda") -> None:
        import torch
        from vibevoice import VibeVoiceForConditionalGenerationInference
        from vibevoice.processor import VibeVoiceProcessor

        self._device = device
        model_path = settings.VIBEVOICE_1P5B_MODEL_PATH
        logger.info("Loading VibeVoice 1.5B from %s on %s", model_path, device)

        self._processor = VibeVoiceProcessor.from_pretrained(model_path)
        self._model = VibeVoiceForConditionalGenerationInference.from_pretrained_hf(
            model_path,
            device=device,
            torch_dtype=torch.bfloat16,
        )
        self._model.eval()
        self._model.set_ddpm_inference_steps(num_steps=20)
        self._loaded = True
        logger.info(
            "VibeVoice 1.5B loaded (%.1f GB VRAM estimate)", self.vram_gb_estimate
        )

    def unload(self) -> None:
        import torch

        del self._model
        del self._processor
        self._model = None
        self._processor = None
        self._loaded = False
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def generate(self, request: GenerateRequest) -> GenerateResult:
        import soundfile as sf
        import torch

        if not self._loaded or self._model is None:
            raise RuntimeError("VibeVoice 1.5B model is not loaded")

        # Format text as speaker-labelled (required by the 1.5B model)
        text = f"Speaker 0: {request.text}"

        # Prepare voice samples for cloning if a voice profile is set
        voice_samples = self._load_voice_samples(request.voice_id)

        # Build processor inputs
        if voice_samples:
            inputs = self._processor(
                text=text,
                voice_samples=voice_samples,
                return_tensors="pt",
            ).to(self._device)
        else:
            inputs = self._processor(
                text=text,
                return_tensors="pt",
            ).to(self._device)

        # Determine cfg_scale from extras or default
        cfg_scale = request.extra.get("cfg_scale", 3.0)

        with torch.no_grad():
            output = self._model.generate(
                **inputs,
                tokenizer=self._processor.tokenizer,
                cfg_scale=cfg_scale,
                return_speech=True,
            )

        if not output.speech_outputs or output.speech_outputs[0] is None:
            raise RuntimeError("VibeVoice 1.5B generated no audio output")

        audio_tensor = output.speech_outputs[0]

        # Convert to numpy
        if torch.is_tensor(audio_tensor):
            audio_np = audio_tensor.cpu().float().numpy().astype(np.float32)
        else:
            audio_np = np.array(audio_tensor, dtype=np.float32)

        # Ensure 1D
        if audio_np.ndim > 1:
            audio_np = audio_np.squeeze()

        duration = len(audio_np) / self.SAMPLE_RATE

        buf = io.BytesIO()
        sf.write(buf, audio_np, self.SAMPLE_RATE, format="WAV")
        audio_bytes = buf.getvalue()

        return GenerateResult(
            audio_bytes=audio_bytes,
            sample_rate=self.SAMPLE_RATE,
            duration_seconds=duration,
            format="wav",
        )

    def clone_voice(self, audio_path: str, name: str) -> dict:
        """Store reference audio path for zero-shot cloning at generate time.

        The 1.5B model does zero-shot voice cloning by passing voice_samples
        to the processor — no separate embedding step is needed. We just
        store the reference audio path.
        """
        ref_path = Path(audio_path)
        if not ref_path.exists():
            raise FileNotFoundError(f"Reference audio not found: {audio_path}")

        return {
            "model_id": self.model_id,
            "reference_audio_path": str(ref_path),
        }

    def _load_voice_samples(self, voice_id: str | None) -> list | None:
        """Load reference audio as voice_samples list for the processor."""
        if voice_id is None:
            return None

        import torchaudio

        ref_path = Path(voice_id)
        if not ref_path.exists():
            logger.warning(
                "Voice reference %r not found, using default voice", voice_id
            )
            return None

        waveform, sr = torchaudio.load(str(ref_path))
        if sr != self.SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, sr, self.SAMPLE_RATE)
        if waveform.shape[0] > 1:
            waveform = waveform.mean(0, keepdim=True)

        return [waveform.squeeze(0).numpy()]
