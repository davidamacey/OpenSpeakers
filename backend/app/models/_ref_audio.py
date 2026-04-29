"""Shared reference-audio preprocessing for voice-cloning models.

Voice-cloning models (Fish Speech, F5-TTS, CosyVoice, VibeVoice 1.5B, Qwen3 TTS,
Chatterbox, Dia) all expect a clean reference clip in a model-appropriate format:
mono, a specific sample rate, free of leading/trailing silence, loudness-normalized,
and clipped to a sensible duration. Raw user uploads rarely satisfy all of these
constraints, so we centralise the preprocessing here.

The pipeline is:

  decode -> mono -> resample -> trim silence -> normalize loudness -> length-clip

Two entry points:

* ``prepare_reference`` returns ``(np.ndarray, sample_rate)`` for callers that want
  an in-memory tensor (VibeVoice, CosyVoice).
* ``prepare_reference_to_file`` writes the cleaned WAV to a deterministic on-disk
  cache and returns the path. Models whose upstream API takes a file path
  (Fish Speech, F5-TTS, Chatterbox, Dia) use this form.

Both raise :class:`ReferenceAudioError` on bad input (corrupt, all-silence, too
short after trim, or non-finite samples).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


class ReferenceAudioError(RuntimeError):
    """Raised when reference audio cannot be prepared (corrupt, silent, too short)."""


# Threshold (linear RMS) below which a stereo channel is considered "dead".
# Anything weaker than this is well below ambient noise on a quiet recording.
_DEAD_CHANNEL_RMS = 1e-4

# Loudness floor for the RMS gain calculation; prevents division by zero.
_RMS_FLOOR = 1e-6

# Silence trimming threshold in dB below the peak (librosa convention).
_TRIM_TOP_DB = 30

# Length of the cosine fade-out applied at a clip boundary, in seconds.
_FADE_OUT_SECONDS = 0.05

# Anti-clipping safety margin — keep peak below this after gain.
_PEAK_LIMIT = 0.99


def _decode(path: Path) -> tuple[np.ndarray, int]:
    """Decode ``path`` to a (samples, channels) array. Falls back to librosa for
    formats libsndfile rejects (MP3, M4A, OPUS, WEBM, ...)."""
    import soundfile as sf

    try:
        audio, sr = sf.read(str(path), always_2d=False)
        return audio, int(sr)
    except (RuntimeError, sf.LibsndfileError) as primary_err:
        logger.debug("soundfile failed for %s (%s); falling back to librosa", path, primary_err)
        try:
            import librosa

            audio, sr = librosa.load(str(path), sr=None, mono=False)
            # librosa returns (channels, samples) for multi-channel; transpose to match
            # soundfile's (samples, channels) convention.
            if audio.ndim == 2:
                audio = audio.T
            return audio, int(sr)
        except Exception as fallback_err:  # noqa: BLE001 — surface a useful message
            raise ReferenceAudioError(
                f"could not decode reference audio {path!s}: {fallback_err}"
            ) from fallback_err


def _to_mono(audio: np.ndarray) -> np.ndarray:
    """Collapse multi-channel audio to mono.

    If one channel is essentially silent (RMS < ``_DEAD_CHANNEL_RMS``) but another
    isn't, we use the louder channel only — averaging would halve the amplitude
    of recordings made with a single-active-mic stereo input.
    """
    if audio.ndim == 1:
        return audio
    if audio.shape[-1] == 1:
        return audio.reshape(-1)

    # Per-channel RMS along the time axis (axis 0).
    channel_rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2, axis=0))
    loudest_idx = int(np.argmax(channel_rms))
    loudest_rms = float(channel_rms[loudest_idx])
    quietest_rms = float(np.min(channel_rms))

    if loudest_rms > _DEAD_CHANNEL_RMS and quietest_rms < _DEAD_CHANNEL_RMS:
        logger.info(
            "reference audio has a silent channel (rms=%.2e); using channel %d only",
            quietest_rms,
            loudest_idx,
        )
        return audio[:, loudest_idx]

    return audio.mean(axis=-1)


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample ``audio`` from ``orig_sr`` to ``target_sr`` using torchaudio."""
    if orig_sr == target_sr:
        return audio
    if orig_sr < 16_000:
        logger.warning(
            "reference audio source rate %d Hz is low; upsampling to %d Hz may sound thin",
            orig_sr,
            target_sr,
        )
    import torch
    import torchaudio.functional as F  # noqa: N812 — match torchaudio convention

    tensor = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
    resampled = F.resample(tensor, orig_sr, target_sr).squeeze(0).numpy()
    return resampled


def _trim_silence(audio: np.ndarray) -> np.ndarray:
    """Trim leading and trailing silence using librosa's energy-based detector."""
    import librosa

    trimmed, _ = librosa.effects.trim(audio, top_db=_TRIM_TOP_DB)
    return trimmed


def _normalize_loudness(audio: np.ndarray, target_rms: float) -> np.ndarray:
    """Scale ``audio`` to the requested RMS, capping the gain to avoid clipping."""
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    gain = target_rms / max(rms, _RMS_FLOOR)
    peak = float(np.max(np.abs(audio))) * gain
    if peak > _PEAK_LIMIT:
        gain *= _PEAK_LIMIT / peak
    return (audio * gain).astype(np.float32)


def _length_clip(audio: np.ndarray, max_samples: int, sr: int) -> np.ndarray:
    """Clip ``audio`` to ``max_samples`` and apply a cosine fade-out at the cut."""
    if len(audio) <= max_samples:
        return audio

    logger.info(
        "reference audio is %.1fs; clipping to %.1fs for this model",
        len(audio) / sr,
        max_samples / sr,
    )
    clipped = audio[:max_samples].copy()
    fade_n = min(int(_FADE_OUT_SECONDS * sr), len(clipped))
    if fade_n > 1:
        # Half-cosine from 1 -> 0 across the last fade_n samples.
        window = 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fade_n))).astype(np.float32)
        clipped[-fade_n:] *= window
    return clipped


def prepare_reference(
    path: str | Path,
    target_sr: int,
    *,
    max_seconds: float | None = None,
    min_seconds: float = 1.0,
    trim_silence: bool = True,
    normalize_loudness: bool = True,
    target_rms: float = 0.1,
) -> tuple[np.ndarray, int]:
    """Load a reference audio clip and return a clean float32 array at ``target_sr``.

    Pipeline: decode -> mono -> resample -> trim silence -> normalize loudness ->
    length-clip with fade-out.

    Args:
        path: Path to the reference audio file.
        target_sr: Sample rate the output should be at (model-specific).
        max_seconds: If set, clip the output to this duration (with a cosine fade
            on the cut). If ``None``, no length clipping is applied.
        min_seconds: Minimum acceptable duration after silence trim. Below this we
            assume the input is effectively silent and raise
            :class:`ReferenceAudioError`.
        trim_silence: If ``True``, strip leading and trailing silence.
        normalize_loudness: If ``True``, scale RMS to ``target_rms`` (capped to
            avoid clipping).
        target_rms: RMS target when ``normalize_loudness`` is on. Default 0.1
            matches the F5-TTS upstream default.

    Returns:
        ``(audio, sample_rate)`` where ``audio`` is a 1-D float32 array in
        roughly [-1, 1] and ``sample_rate == target_sr``.

    Raises:
        ReferenceAudioError: If the file cannot be decoded, decodes to nothing,
            is silent or too short after trim, or contains non-finite samples.
    """
    src = Path(path)
    if not src.exists():
        raise ReferenceAudioError(f"reference audio not found: {src}")

    audio, orig_sr = _decode(src)
    if audio.size == 0:
        raise ReferenceAudioError(f"reference audio decoded to zero samples: {src}")

    audio = _to_mono(audio)
    audio = audio.astype(np.float32, copy=False)
    # Inputs occasionally come scaled outside [-1, 1] (poorly authored WAV/float
    # conversions); clip before downstream processing so RMS/peak math is sane.
    audio = np.clip(audio, -1.0, 1.0)

    audio = _resample(audio, orig_sr, target_sr)

    if trim_silence:
        audio = _trim_silence(audio)

    duration = len(audio) / target_sr
    if duration < min_seconds:
        raise ReferenceAudioError(
            f"reference audio is silent or too short after trim ({duration:.2f}s < {min_seconds}s)"
        )

    if normalize_loudness:
        audio = _normalize_loudness(audio, target_rms)

    if max_seconds is not None:
        audio = _length_clip(audio, int(max_seconds * target_sr), target_sr)

    if not np.all(np.isfinite(audio)):
        raise ReferenceAudioError("non-finite samples in prepared reference audio")

    return audio.astype(np.float32, copy=False), target_sr


def _cache_dir() -> Path:
    """Resolve the on-disk cache directory and create it if needed."""
    cache_dir = Path(settings.AUDIO_OUTPUT_DIR) / "voices" / "_clean"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_key(
    path: Path,
    target_sr: int,
    max_seconds: float | None,
    min_seconds: float,
    trim_silence: bool,
    normalize_loudness: bool,
    target_rms: float,
) -> str:
    """Stable 16-char hash over the source mtime and the preprocessing params."""
    abs_path = str(path.resolve())
    mtime = path.stat().st_mtime
    payload = (
        f"{abs_path}|{mtime}|{target_sr}|{max_seconds}|{trim_silence}"
        f"|{normalize_loudness}|{target_rms}|{min_seconds}"
    )
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def prepare_reference_to_file(
    path: str | Path,
    target_sr: int,
    *,
    max_seconds: float | None = None,
    min_seconds: float = 1.0,
    trim_silence: bool = True,
    normalize_loudness: bool = True,
    target_rms: float = 0.1,
) -> Path:
    """Same as :func:`prepare_reference` but writes the cleaned WAV to a cache.

    Cache layout::

        ${AUDIO_OUTPUT_DIR}/voices/_clean/{sha1[:16]}.wav

    The hash includes the source file's absolute path + mtime + every
    preprocessing parameter, so re-uploading the same audio under the same
    profile invalidates the cache automatically. Subsequent calls with matching
    (path, params, mtime) return the cached path without re-processing.

    Returns:
        Path to the cached cleaned WAV file (16-bit PCM at ``target_sr``).
    """
    src = Path(path)
    if not src.exists():
        raise ReferenceAudioError(f"reference audio not found: {src}")

    key = _cache_key(
        src,
        target_sr,
        max_seconds,
        min_seconds,
        trim_silence,
        normalize_loudness,
        target_rms,
    )
    cache_path = _cache_dir() / f"{key}.wav"
    if cache_path.exists():
        return cache_path

    audio, sr = prepare_reference(
        src,
        target_sr,
        max_seconds=max_seconds,
        min_seconds=min_seconds,
        trim_silence=trim_silence,
        normalize_loudness=normalize_loudness,
        target_rms=target_rms,
    )

    import soundfile as sf

    sf.write(str(cache_path), audio, sr, subtype="PCM_16")
    return cache_path
