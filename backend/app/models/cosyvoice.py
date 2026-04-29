"""CosyVoice 2.0 — 150ms latency, MOS 5.53, multi-mode TTS.

Install: pip install cosyvoice2  (or clone FunAudioLLM/CosyVoice repo)
HuggingFace: FunAudioLLM/CosyVoice2-0.5B
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from app.models._ref_audio import prepare_reference_to_file
from app.models.base import GenerateRequest, GenerateResult, TTSModelBase

logger = logging.getLogger(__name__)


class CosyVoice2Model(TTSModelBase):
    model_id = "cosyvoice-2"
    model_name = "CosyVoice 2.0"
    description = "FunAudioLLM CosyVoice 2.0 — 150ms latency, MOS 5.53, zero-shot + voice design"
    supports_voice_cloning = True
    supports_streaming = False  # generate() collects all chunks; stream_generate not implemented
    supports_speed = False
    supported_languages = ["en", "zh", "ja", "ko", "fr", "de", "es", "pt", "ar", "ru"]
    hf_repo = "FunAudioLLM/CosyVoice2-0.5B"
    vram_gb_estimate = 5.0
    help_text = (
        "Ultra-low latency (150ms). Voice design via text description or reference audio. "
        "Multilingual. Zero-shot cloning. ~5 GB VRAM."
    )

    def __init__(self) -> None:
        self._model = None
        # Cache of voice_id -> bool, populated on first generation for that
        # profile when no ref_text is available. Keyed by stable id (the
        # voice_id path is effectively the profile id). Cleared on unload().
        self._zero_shot_spk_cache: dict[str, bool] = {}

    _HF_MODEL_ID = "FunAudioLLM/CosyVoice2-0.5B"

    def _resolve_model_path(self) -> str:
        """Resolve model to a local directory path (HF hub cache or explicit override).

        CosyVoice2.__init__ skips snapshot_download when os.path.exists(model_dir)
        is True, so passing the resolved local path avoids any network call.
        """
        import os

        override = os.environ.get("COSYVOICE_MODEL_PATH")
        if override and Path(override).is_dir():
            return override

        # Find the model in the HF hub cache
        try:
            from huggingface_hub import snapshot_download

            return snapshot_download(self._HF_MODEL_ID)
        except Exception:
            pass

        return self._HF_MODEL_ID

    def load(self, device: str = "cuda") -> None:
        logger.info("Loading CosyVoice 2.0 on %s", device)

        # Resolve to local HF cache path so CosyVoice2 skips its modelscope download
        # (CosyVoice2.__init__ only calls snapshot_download if the path doesn't exist)
        model_path = self._resolve_model_path()
        logger.info("CosyVoice 2.0 model path: %s", model_path)

        from cosyvoice.cli.cosyvoice import CosyVoice2

        self._model = CosyVoice2(model_path)
        self._loaded = True
        logger.info("CosyVoice 2.0 loaded from %s", model_path)

    def unload(self) -> None:
        self._model = None
        self._loaded = False
        # Cached zero-shot speakers reference state inside the model object —
        # invalidate so the next load doesn't think they're still registered.
        self._zero_shot_spk_cache.clear()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    # Bundled reference audio (from CosyVoice repo clone)
    _DEFAULT_ZERO_SHOT_REF = "/opt/cosyvoice/asset/zero_shot_prompt.wav"

    def generate(self, request: GenerateRequest) -> GenerateResult:
        if not self._loaded or self._model is None:
            raise RuntimeError("CosyVoice 2.0 is not loaded")

        import torch
        import torchaudio

        ref_audio = None
        if request.voice_id and Path(request.voice_id).exists():
            ref_audio = request.voice_id
        elif Path(self._DEFAULT_ZERO_SHOT_REF).exists():
            ref_audio = self._DEFAULT_ZERO_SHOT_REF

        if not ref_audio:
            raise RuntimeError(
                "CosyVoice 2.0 requires a reference audio file. "
                "Pass voice_id pointing to a WAV/MP3 file, or use a cloned voice profile."
            )

        ref_text = (request.extra.get("ref_text") or "").strip()
        instruct_text = request.extra.get("instruct", "")

        # Pre-clean prompt and write a cleaned WAV to disk. CosyVoice's frontend
        # internally calls load_wav(path, 24000) inside _extract_speech_feat, so
        # the prompt MUST be a path-like, not a tensor (passing a tensor here
        # produces "Invalid file: tensor(...)"). The 16 kHz target is for our
        # cleaning pass; CosyVoice resamples to 24 kHz internally.
        prompt_wav_path = str(prepare_reference_to_file(ref_audio, 16000, max_seconds=30))

        all_audio = []

        if instruct_text:
            # Voice-design mode: shape voice with a natural-language instruction.
            # The instruct path always takes the cleaned prompt directly.
            for chunk in self._model.inference_instruct2(
                request.text, instruct_text, prompt_wav_path, stream=False
            ):
                all_audio.append(chunk["tts_speech"])
        elif ref_text:
            # Zero-shot cloning with the user's reference transcript — the
            # default upstream path.
            for chunk in self._model.inference_zero_shot(
                request.text,
                prompt_text=ref_text,
                prompt_wav=prompt_wav_path,
                stream=False,
            ):
                all_audio.append(chunk["tts_speech"])
        else:
            # No transcript available: use the upstream "saved zero-shot speaker"
            # trick from cosyvoice2_example(). We register the speaker once per
            # voice_id, then call inference_zero_shot with empty text fields and
            # the cached speaker id. If add_zero_shot_spk rejects the empty
            # prompt_text, fall back to passing the prompt_wav directly.
            spk_id = str(request.voice_id or ref_audio)
            registered = False
            if not self._zero_shot_spk_cache.get(spk_id):
                try:
                    self._model.add_zero_shot_spk(
                        prompt_text="",
                        prompt_wav=prompt_wav_path,
                        zero_shot_spk_id=spk_id,
                    )
                    self._zero_shot_spk_cache[spk_id] = True
                    registered = True
                except Exception as exc:  # noqa: BLE001 — we have a fallback path
                    logger.warning(
                        "CosyVoice add_zero_shot_spk failed (%s); falling back to "
                        "direct prompt_wav with empty prompt_text.",
                        exc,
                    )
            else:
                registered = True

            if registered:
                for chunk in self._model.inference_zero_shot(
                    request.text,
                    "",
                    "",
                    zero_shot_spk_id=spk_id,
                    stream=False,
                ):
                    all_audio.append(chunk["tts_speech"])
            else:
                for chunk in self._model.inference_zero_shot(
                    request.text,
                    prompt_text="",
                    prompt_wav=prompt_wav_path,
                    stream=False,
                ):
                    all_audio.append(chunk["tts_speech"])

        audio = torch.cat(all_audio, dim=-1)
        # CosyVoice 2.0 emits at 24 kHz — read the model's own property rather
        # than hardcoding 22050 (was a ~9% pitch-shift bug).
        sr = int(self._model.sample_rate)
        duration = audio.shape[-1] / sr

        buf = io.BytesIO()
        torchaudio.save(buf, audio.cpu(), sr, format="wav")
        buf.seek(0)

        return GenerateResult(
            audio_bytes=buf.getvalue(),
            sample_rate=sr,
            duration_seconds=duration,
            format="wav",
        )

    def clone_voice(self, audio_path: str, name: str = "") -> dict:  # noqa: ARG002
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Reference audio not found: {audio_path}")
        return {"reference_audio_path": audio_path, "model": self.model_id}
