"""Dia 1.6B — multi-speaker dialogue TTS with [S1]/[S2] tags.

Unique capability: dialogue generation with alternating speakers.
Supports nonverbal sounds: (laughs), (sighs), (coughs), (clears throat), (whispers)
Install: pip install dia-tts  (or from git: nari-labs/dia)
HuggingFace: nari-labs/Dia-1.6B
"""

from __future__ import annotations

import io
import logging
import wave

from app.models.base import GenerateRequest, GenerateResult, TTSModelBase

logger = logging.getLogger(__name__)

SAMPLE_RATE = 44100


class DiaTTSModel(TTSModelBase):
    model_id = "dia-1b"
    model_name = "Dia 1.6B"
    description = (
        "Nari Labs Dia 1.6B — dialogue TTS with [S1]/[S2] speaker tags and nonverbal sounds"
    )
    supports_voice_cloning = True
    supports_streaming = False
    supports_speed = False
    supported_languages = ["en"]
    hf_repo = "nari-labs/Dia-1.6B-0626"
    vram_gb_estimate = 10.0
    supports_dialogue = True
    dialogue_format = "dia"
    help_text = (
        "Multi-speaker dialogue with [S1]/[S2] tags. Supports nonverbal sounds: "
        "(laughs), (sighs), (coughs), (clears throat), (whispers). "
        "Voice cloning requires a transcript of the reference audio. "
        "Slow generation (~30s). English only. ~10 GB VRAM."
    )

    def __init__(self) -> None:
        self._model = None

    def load(self, device: str = "cuda") -> None:
        logger.info("Loading Dia 1.6B on %s", device)
        # Dia's ``load_audio`` calls ``torchaudio.load(path)`` which on
        # torchaudio 2.10 routes through TorchCodec; the worker image doesn't
        # bundle TorchCodec so the call raises ImportError and kills every
        # voice-clone job. Monkey-patch the method to use soundfile directly.
        import io as _io
        from pathlib import Path as _Path

        import soundfile as _sf
        import torch as _torch
        from dia.model import Dia

        def _load_audio_patched(self_dia, audio_path):
            """soundfile-based replacement for Dia.load_audio.

            Mirrors the upstream method exactly except it reads with soundfile
            instead of ``torchaudio.load`` (which routes to TorchCodec on
            torchaudio 2.10+). Returns DAC codebook indices via ``self._encode``,
            shape (T, C).
            """
            if self_dia.dac_model is None:
                raise RuntimeError(
                    "DAC model is required for loading audio prompts but was not loaded."
                )
            target_sr = 44100  # Dia's DEFAULT_SAMPLE_RATE
            if isinstance(audio_path, (bytes, bytearray)):
                src = _io.BytesIO(audio_path)
            elif isinstance(audio_path, str) and not _Path(audio_path).exists():
                src = _io.BytesIO(audio_path.encode("latin1"))
            else:
                src = audio_path
            wav, sr = _sf.read(src, dtype="float32", always_2d=True)
            audio = _torch.from_numpy(wav.T)  # (channels, samples)
            if sr != target_sr:
                import torchaudio.functional as _F  # noqa: N812

                audio = _F.resample(audio, sr, target_sr)
            if audio.shape[0] > 1:
                audio = audio.mean(dim=0, keepdim=True)
            return self_dia._encode(audio.to(self_dia.device))

        Dia.load_audio = _load_audio_patched

        self._model = Dia.from_pretrained("nari-labs/Dia-1.6B-0626", compute_dtype="float16")
        self._loaded = True
        logger.info("Dia 1.6B loaded")

    def unload(self) -> None:
        self._model = None
        self._loaded = False
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def generate(self, request: GenerateRequest) -> GenerateResult:
        if not self._loaded or self._model is None:
            raise RuntimeError("Dia 1.6B is not loaded")

        from pathlib import Path

        import numpy as np
        import soundfile as sf

        from app.models._ref_audio import prepare_reference_to_file

        # Cloning is requested when voice_id is a path to an existing audio file.
        voice_id = request.voice_id
        is_cloning = bool(voice_id and Path(voice_id).exists())

        # Sampler params (apply to both cloning and non-cloning paths).
        cfg_scale = float(request.extra.get("cfg_scale", 4.0))
        temperature = float(request.extra.get("temperature", 1.8))
        top_p = float(request.extra.get("top_p", 0.90))
        cfg_filter_top_k = int(request.extra.get("cfg_filter_top_k", 50))
        use_torch_compile = bool(request.extra.get("use_torch_compile", False))

        if is_cloning:
            ref_text = (request.extra.get("ref_text") or "").strip()
            if not ref_text:
                raise RuntimeError(
                    "Dia voice cloning requires a transcript of the reference audio. "
                    "Edit the voice profile and add 'reference_text'."
                )

            # Clean the reference clip and grab its actual duration so we can
            # head-trim the re-synth from the model's output later. Use a
            # cheap header read on the cached clean WAV instead of a second
            # full preprocessing pass. max_seconds=10 matches upstream's
            # "best results with 5-10s of reference audio" guidance.
            cleaned_path = prepare_reference_to_file(voice_id, SAMPLE_RATE, max_seconds=10)
            ref_info = sf.info(str(cleaned_path))
            ref_duration_s = ref_info.frames / float(ref_info.samplerate)

            # Per upstream example/voice_clone.py: prepend the transcript of the
            # reference audio (with speaker tag) before the new text, and pass
            # the reference WAV via audio_prompt=.
            prefix = ref_text if ref_text.startswith("[S") else f"[S1] {ref_text}"
            gen_text = (
                request.text if request.text.strip().startswith("[S") else f"[S1] {request.text}"
            )
            full_text = prefix + " " + gen_text

            audio = self._model.generate(
                full_text,
                audio_prompt=str(cleaned_path),
                use_torch_compile=use_torch_compile,
                verbose=False,
                cfg_scale=cfg_scale,
                temperature=temperature,
                top_p=top_p,
                cfg_filter_top_k=cfg_filter_top_k,
            )
        else:
            ref_duration_s = 0.0
            text = request.text
            if not text.strip().startswith("[S"):
                text = f"[S1] {text}"

            audio = self._model.generate(
                text,
                use_torch_compile=use_torch_compile,
                verbose=False,
                cfg_scale=cfg_scale,
                temperature=temperature,
                top_p=top_p,
                cfg_filter_top_k=cfg_filter_top_k,
            )

        if hasattr(audio, "numpy"):
            audio = audio.numpy()

        sr = SAMPLE_RATE

        # Head-trim the reference re-synth from the output for cloning requests.
        # Dia regenerates audio for the prepended reference transcript along with
        # the new text; we drop that portion plus a 100 ms safety margin and apply
        # a 50 ms cosine fade-in on the cut to avoid a click.
        if is_cloning and ref_duration_s > 0:
            # Work in float for the fade math; we'll quantize to int16 below.
            audio_f = np.asarray(audio, dtype=np.float32)
            trim_samples = int((ref_duration_s + 0.1) * sr)
            if trim_samples < len(audio_f) - int(0.5 * sr):
                fade_n = int(0.05 * sr)
                audio_f = audio_f[trim_samples:]
                if len(audio_f) > fade_n:
                    fade_in = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_n))).astype(np.float32)
                    audio_f[:fade_n] = audio_f[:fade_n] * fade_in
                audio = audio_f
            else:
                logger.warning(
                    "Dia output (%.2fs) shorter than reference (%.2fs) — returning full "
                    "output without head-trim.",
                    len(audio_f) / sr,
                    ref_duration_s,
                )
                audio = audio_f

        if audio.dtype != np.int16:
            audio = (audio * 32767).astype(np.int16)

        duration = len(audio) / sr

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(audio.tobytes())
        buf.seek(0)

        return GenerateResult(
            audio_bytes=buf.getvalue(),
            sample_rate=sr,
            duration_seconds=duration,
            format="wav",
        )

    def clone_voice(self, audio_path: str, name: str = "") -> dict:  # noqa: ARG002
        """Dia uses reference audio for voice conditioning."""
        from pathlib import Path

        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Reference audio not found: {audio_path}")
        return {"reference_audio_path": audio_path, "model": self.model_id}
