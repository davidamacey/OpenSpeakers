"""Unit tests for :mod:`app.models._ref_audio`.

These tests are pure: they synthesise audio with numpy, write it to ``tmp_path``
via soundfile, and exercise the helper. No DB, no Celery, no GPU. They cover the
documented edge cases from the Phase 2 plan: stereo->mono, resampling, silence
trimming, all-silence rejection, loudness normalisation safety, length clipping
with fade-out, dead-channel detection, missing files, and on-disk caching.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.core.config import settings
from app.models._ref_audio import (
    ReferenceAudioError,
    prepare_reference,
    prepare_reference_to_file,
)


def _tone(seconds: float, sr: int, freq: float = 440.0, amplitude: float = 0.3) -> np.ndarray:
    """Synthesise a mono sine wave."""
    t = np.arange(int(seconds * sr)) / sr
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _silence(seconds: float, sr: int) -> np.ndarray:
    return np.zeros(int(seconds * sr), dtype=np.float32)


def _write(path: Path, audio: np.ndarray, sr: int) -> Path:
    sf.write(str(path), audio, sr)
    return path


def test_stereo_to_mono(tmp_path: Path) -> None:
    sr = 24_000
    left = _tone(2.0, sr, freq=440.0)
    right = _tone(2.0, sr, freq=660.0)
    stereo = np.stack([left, right], axis=-1)
    src = _write(tmp_path / "stereo.wav", stereo, sr)

    audio, out_sr = prepare_reference(src, target_sr=sr, normalize_loudness=False)

    assert out_sr == sr
    assert audio.ndim == 1
    assert audio.dtype == np.float32
    assert np.all(np.isfinite(audio))


def test_resample_to_target_sr(tmp_path: Path) -> None:
    src_sr = 48_000
    target_sr = 24_000
    seconds = 2.0
    src = _write(tmp_path / "hi_sr.wav", _tone(seconds, src_sr), src_sr)

    audio, out_sr = prepare_reference(
        src,
        target_sr=target_sr,
        trim_silence=False,
        normalize_loudness=False,
    )

    assert out_sr == target_sr
    expected = int(seconds * target_sr)
    # Resampling can introduce a small filter-tail delta; allow a generous window.
    assert abs(len(audio) - expected) < 100


def test_silence_trim_removes_leading_silence(tmp_path: Path) -> None:
    sr = 24_000
    audio = np.concatenate([_silence(0.5, sr), _tone(1.0, sr)])
    src = _write(tmp_path / "leading_silence.wav", audio, sr)

    out, out_sr = prepare_reference(src, target_sr=sr, normalize_loudness=False)

    assert out_sr == sr
    duration = len(out) / sr
    assert 0.85 <= duration <= 1.15, f"trimmed duration {duration:.3f}s outside expected window"


def test_all_silence_raises(tmp_path: Path) -> None:
    sr = 24_000
    src = _write(tmp_path / "silent.wav", _silence(2.0, sr), sr)

    with pytest.raises(ReferenceAudioError):
        prepare_reference(src, target_sr=sr)


def test_loudness_normalization_no_clipping(tmp_path: Path) -> None:
    sr = 24_000
    # Low-amplitude tone; without the cap, scaling to RMS=0.1 from RMS~0.0007
    # would produce gain in the hundreds and clip badly.
    quiet = _tone(2.0, sr, amplitude=0.001)
    src = _write(tmp_path / "quiet.wav", quiet, sr)

    out, _ = prepare_reference(
        src,
        target_sr=sr,
        trim_silence=False,
        normalize_loudness=True,
        target_rms=0.1,
    )

    peak = float(np.max(np.abs(out)))
    assert peak <= 0.99 + 1e-6, f"loudness normalisation produced clipping: peak={peak}"


def test_max_seconds_clip(tmp_path: Path) -> None:
    sr = 24_000
    src = _write(tmp_path / "long.wav", _tone(20.0, sr), sr)

    out, _ = prepare_reference(
        src,
        target_sr=sr,
        max_seconds=10.0,
        trim_silence=False,
        normalize_loudness=False,
    )

    duration = len(out) / sr
    assert 9.9 <= duration <= 10.05, f"unexpected clipped duration {duration:.3f}s"
    # Last sample should be near zero from the cosine fade-out window.
    assert abs(float(out[-1])) < 0.05, f"fade-out not applied: tail sample={out[-1]:.4f}"


def test_dead_channel_picks_louder(tmp_path: Path) -> None:
    sr = 24_000
    seconds = 2.0
    left = _tone(seconds, sr, amplitude=0.3)
    right = _silence(seconds, sr)
    stereo = np.stack([left, right], axis=-1)
    src = _write(tmp_path / "dead_right.wav", stereo, sr)

    out, _ = prepare_reference(
        src,
        target_sr=sr,
        trim_silence=False,
        normalize_loudness=False,
    )

    # If we'd averaged, peak amplitude would be ~0.15 (half). Picking the louder
    # channel should preserve ~0.3.
    peak = float(np.max(np.abs(out)))
    assert peak > 0.25, f"dead-channel detection failed: peak={peak:.3f} suggests averaging"


def test_corrupt_path_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "does_not_exist.wav"
    with pytest.raises(ReferenceAudioError):
        prepare_reference(bogus, target_sr=24_000)


def test_cache_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIO_OUTPUT_DIR", str(tmp_path))

    sr = 24_000
    src = _write(tmp_path / "ref.wav", _tone(2.0, sr), sr)

    first = prepare_reference_to_file(src, target_sr=sr, max_seconds=5.0)
    assert first.exists()
    first_bytes = first.read_bytes()
    first_mtime = first.stat().st_mtime

    second = prepare_reference_to_file(src, target_sr=sr, max_seconds=5.0)
    assert second == first
    # Same args + same source mtime → cache hit, file should not be rewritten.
    assert second.stat().st_mtime == first_mtime
    assert second.read_bytes() == first_bytes
