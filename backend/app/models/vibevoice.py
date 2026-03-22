"""VibeVoice TTS model implementation.

Model: microsoft/VibeVoice-Realtime-0.5B
  - End-to-end speech LM with diffusion TTS head
  - Supports real-time streaming synthesis
  - Voice cloning via reference speaker cached-prompt .pt files

Reference: /mnt/nvm/repos/VibeVoice/demo/realtime_model_inference_from_file.py
"""

from __future__ import annotations

import copy
import io
import logging
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.models.base import GenerateRequest, GenerateResult, TTSModelBase

logger = logging.getLogger(__name__)

# Built-in voices shipped with VibeVoice (streaming_model .pt files)
# Keys are user-facing slugs, values are .pt filename stems
BUILTIN_VOICES: dict[str, str] = {
    "en-Carter": "en-Carter_man",
    "en-Davis": "en-Davis_man",
    "en-Emma": "en-Emma_woman",
    "en-Frank": "en-Frank_man",
    "en-Grace": "en-Grace_woman",
    "en-Mike": "en-Mike_man",
    "de-Spk0": "de-Spk0_man",
    "de-Spk1": "de-Spk1_woman",
    "fr-Spk0": "fr-Spk0_man",
    "fr-Spk1": "fr-Spk1_woman",
    "es-Spk0": "sp-Spk0_woman",
    "es-Spk1": "sp-Spk1_man",
}

DEFAULT_VOICE = "en-Emma"

# Path to the VibeVoice repo (mounted as a Docker volume)
VIBEVOICE_VOICES_DIR = Path("/opt/vibevoice/demo/voices/streaming_model")


class VibeVoiceModel(TTSModelBase):
    model_id = "vibevoice"
    model_name = "VibeVoice 0.5B"
    description = "Microsoft VibeVoice real-time streaming TTS with 12 built-in voices"
    supports_voice_cloning = False
    supports_streaming = True
    supported_languages = [
        "en",
        "de",
        "fr",
        "es",
        "it",
        "pt",
        "nl",
        "pl",
        "ja",
        "ko",
        "zh",
        "in",
    ]
    hf_repo = "microsoft/VibeVoice-Realtime-0.5B"
    vram_gb_estimate = 4.5

    def __init__(self) -> None:
        self._model = None
        self._processor = None
        self._device: str = "cuda"

    def load(self, device: str = "cuda") -> None:
        import torch
        from vibevoice.modular.modeling_vibevoice_streaming_inference import (
            VibeVoiceStreamingForConditionalGenerationInference,
        )
        from vibevoice.processor.vibevoice_streaming_processor import (
            VibeVoiceStreamingProcessor,
        )

        self._device = device
        model_path = settings.VIBEVOICE_MODEL_PATH
        logger.info("Loading VibeVoice from %s on %s", model_path, device)

        self._processor = VibeVoiceStreamingProcessor.from_pretrained(model_path)

        # Determine dtype and attention implementation based on device
        if device == "cuda":
            load_dtype = torch.bfloat16
            attn_impl = "flash_attention_2"
        else:
            load_dtype = torch.float32
            attn_impl = "sdpa"

        try:
            self._model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                device_map=device,
                attn_implementation=attn_impl,
            )
        except Exception:
            if attn_impl == "flash_attention_2":
                logger.warning(
                    "flash_attention_2 failed, falling back to sdpa "
                    "(may have slightly lower audio quality)"
                )
                self._model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                    model_path,
                    torch_dtype=load_dtype,
                    device_map=device,
                    attn_implementation="sdpa",
                )
            else:
                raise

        self._model.eval()
        self._model.set_ddpm_inference_steps(num_steps=5)
        self._loaded = True
        logger.info("VibeVoice loaded (%.1f GB VRAM estimate)", self.vram_gb_estimate)

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
            raise RuntimeError("VibeVoice model is not loaded")

        # Resolve voice preset (cached prompt .pt file)
        cached_prompt = self._resolve_voice(request.voice_id)

        # Prepare inputs using the processor
        inputs = self._processor.process_input_with_cached_prompt(
            text=request.text,
            cached_prompt=cached_prompt,
            padding=True,
            return_tensors="pt",
            return_attention_mask=True,
        )

        # Move tensors to target device
        for k, v in inputs.items():
            if torch.is_tensor(v):
                inputs[k] = v.to(self._device)

        # Read tunable params from extras (clamp to safe ranges)
        cfg_scale = float(request.extra.get("cfg_scale", 1.5))
        cfg_scale = max(0.1, min(cfg_scale, 10.0))
        ddpm_steps = int(request.extra.get("ddpm_steps", 5))
        ddpm_steps = max(1, min(ddpm_steps, 50))
        self._model.set_ddpm_inference_steps(num_steps=ddpm_steps)

        # Generate audio
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=None,
                cfg_scale=cfg_scale,
                tokenizer=self._processor.tokenizer,
                generation_config={"do_sample": False},
                verbose=False,
                all_prefilled_outputs=(
                    copy.deepcopy(cached_prompt) if cached_prompt is not None else None
                ),
            )

        if not outputs.speech_outputs or outputs.speech_outputs[0] is None:
            raise RuntimeError("VibeVoice generated no audio output")

        # Extract audio from model output
        audio_tensor = outputs.speech_outputs[0]
        sample_rate = 24000

        # Convert to numpy
        if torch.is_tensor(audio_tensor):
            audio_np = audio_tensor.cpu().float().numpy().astype(np.float32)
        else:
            audio_np = np.array(audio_tensor, dtype=np.float32)

        # Ensure 1D
        if audio_np.ndim > 1:
            audio_np = audio_np.squeeze()

        duration = len(audio_np) / sample_rate

        buf = io.BytesIO()
        sf.write(buf, audio_np, sample_rate, format="WAV")
        audio_bytes = buf.getvalue()

        return GenerateResult(
            audio_bytes=audio_bytes,
            sample_rate=sample_rate,
            duration_seconds=duration,
            format="wav",
        )

    def clone_voice(self, audio_path: str, _name: str) -> dict:
        raise NotImplementedError(
            "VibeVoice 0.5B (Realtime) does not support voice cloning. "
            "Use VibeVoice 1.5B for zero-shot voice cloning."
        )

    def _resolve_voice(self, voice_id: str | None):
        """Load and return a cached prompt dict from a .pt file, or None for default."""
        import torch

        if voice_id is None:
            voice_id = DEFAULT_VOICE

        # Built-in voice by slug
        if voice_id in BUILTIN_VOICES:
            pt_name = BUILTIN_VOICES[voice_id]
            pt_path = VIBEVOICE_VOICES_DIR / f"{pt_name}.pt"
            if pt_path.exists():
                logger.debug("Loading built-in voice %s from %s", voice_id, pt_path)
                return torch.load(pt_path, map_location=self._device, weights_only=False)
            logger.warning("Built-in voice file not found: %s", pt_path)

        # Custom voice profile: voice_id is the path to a .pt file
        pt_path = Path(voice_id)
        if pt_path.exists() and pt_path.suffix == ".pt":
            return torch.load(pt_path, map_location=self._device, weights_only=False)

        # Try to find in voices directory by name
        candidate = VIBEVOICE_VOICES_DIR / f"{voice_id}.pt"
        if candidate.exists():
            return torch.load(candidate, map_location=self._device, weights_only=False)

        logger.warning("Voice %r not found, using default voice", voice_id)
        # Try default
        default_pt = VIBEVOICE_VOICES_DIR / f"{BUILTIN_VOICES[DEFAULT_VOICE]}.pt"
        if default_pt.exists():
            return torch.load(default_pt, map_location=self._device, weights_only=False)

        return None
