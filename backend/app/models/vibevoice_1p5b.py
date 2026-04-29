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
import re
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
    supports_dialogue = True
    dialogue_format = "vibevoice"
    help_text = (
        "High-quality long-form TTS. Multi-speaker dialogue via 'Speaker 0:' / 'Speaker 1:' "
        "prefixes. Zero-shot voice cloning. 10 languages. Slower generation (~12 GB VRAM)."
    )

    SAMPLE_RATE = 24_000

    def __init__(self) -> None:
        self._model = None
        self._processor = None
        self._device: str = "cuda"

    def load(self, device: str = "cuda") -> None:
        import torch
        import torch._dynamo  # noqa: F401 — pre-import to prevent double CacheArtifact registration in PyTorch 2.6+

        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available — falling back to CPU for VibeVoice 1.5B")
            device = "cpu"
        from vibevoice import VibeVoiceForConditionalGenerationInference
        from vibevoice.processor import VibeVoiceProcessor

        self._device = device
        model_path = settings.VIBEVOICE_1P5B_MODEL_PATH
        logger.info("Loading VibeVoice 1.5B from %s on %s", model_path, device)

        self._processor = VibeVoiceProcessor.from_pretrained(model_path)

        # Determine dtype and attention implementation based on device
        if device == "cuda":
            load_dtype = torch.bfloat16
            attn_impl = "flash_attention_2"
        else:
            load_dtype = torch.float32
            attn_impl = "sdpa"

        try:
            self._model = VibeVoiceForConditionalGenerationInference.from_pretrained_hf(
                model_path,
                device=device,
                torch_dtype=load_dtype,
                attn_implementation=attn_impl,
            )
        except Exception:
            if attn_impl == "flash_attention_2":
                logger.warning(
                    "flash_attention_2 failed, falling back to sdpa "
                    "(may have slightly lower audio quality)"
                )
                self._model = VibeVoiceForConditionalGenerationInference.from_pretrained_hf(
                    model_path,
                    device=device,
                    torch_dtype=load_dtype,
                    attn_implementation="sdpa",
                )
            else:
                raise

        self._model.eval()
        self._model.set_ddpm_inference_steps(num_steps=20)
        self._loaded = True
        logger.info("VibeVoice 1.5B loaded (%.1f GB VRAM estimate)", self.vram_gb_estimate)

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
        # Only add prefix if the text doesn't already have one
        if re.search(r"Speaker\s*\d+\s*:", request.text):
            text = request.text
        else:
            speaker_id = request.extra.get("speaker_id", 0)
            text = f"Speaker {speaker_id}: {request.text}"

        # Prepare voice samples for cloning if a voice profile is set
        voice_samples = self._load_voice_samples(request.voice_id)

        # Build processor inputs (move tensors individually for robustness)
        proc_kwargs: dict = {"text": text, "return_tensors": "pt"}
        if voice_samples:
            proc_kwargs["voice_samples"] = voice_samples
        raw_inputs = self._processor(**proc_kwargs)
        inputs = {k: v.to(self._device) if hasattr(v, "to") else v for k, v in raw_inputs.items()}

        # Read tunable params from extras (clamp to safe ranges)
        cfg_scale = float(request.extra.get("cfg_scale", 3.0))
        cfg_scale = max(0.1, min(cfg_scale, 10.0))
        ddpm_steps = int(request.extra.get("ddpm_steps", 20))
        ddpm_steps = max(1, min(ddpm_steps, 50))
        self._model.set_ddpm_inference_steps(num_steps=ddpm_steps)

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

    def clone_voice(self, audio_path: str, _name: str) -> dict:
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
        """Load reference audio as voice_samples list for the processor.

        Uses the shared ``prepare_reference`` helper which handles mono conversion,
        resample to 24 kHz, silence trim, loudness normalization, and a 30 s clip.
        Loudness normalization is the biggest win here — VibeVoice's voice
        tokenizer is sensitive to RMS.
        """
        if voice_id is None:
            return None

        from app.models._ref_audio import prepare_reference

        ref_path = Path(voice_id)
        if not ref_path.exists():
            logger.warning("Voice reference %r not found, using default voice", voice_id)
            return None

        # Lets ReferenceAudioError propagate (e.g. clip < 3 s after trim) so the
        # user gets a clear error instead of a cryptic shape error downstream.
        arr, _sr = prepare_reference(
            ref_path,
            self.SAMPLE_RATE,
            max_seconds=30,
            min_seconds=3.0,
        )
        return [arr]
