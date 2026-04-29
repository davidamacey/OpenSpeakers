"""Tests for speaker-similarity scoring (Phase 5).

The fast tests use mocked embeddings — they don't load the speechbrain model.
The slow integration test (``test_speechbrain_real_inference``) is gated by the
``RUN_SPEECHBRAIN_TESTS=1`` env var so CI stays quick.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from app.eval import similarity as sim


def _normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return (v / norm).astype(np.float32) if norm > 0 else v.astype(np.float32)


def test_cosine_same_vector_is_one() -> None:
    vec = _normalize(np.array([0.5, 0.3, -0.2, 0.8, 0.1], dtype=np.float32))
    assert sim.cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-6)


def test_cosine_orthogonal_is_zero() -> None:
    a = _normalize(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
    b = _normalize(np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32))
    assert sim.cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_cosine_opposite_is_minus_one() -> None:
    a = _normalize(np.array([0.5, 0.3, -0.2, 0.8, 0.1], dtype=np.float32))
    b = -a
    assert sim.cosine_similarity(a, b) == pytest.approx(-1.0, abs=1e-6)


def test_cosine_clips_to_range() -> None:
    # Identical vectors with tiny perturbation — should still be very close to 1.
    a = _normalize(np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32))
    b = _normalize(np.array([0.5001, 0.5, 0.5, 0.5], dtype=np.float32))
    score = sim.cosine_similarity(a, b)
    assert -1.0 <= score <= 1.0
    assert score > 0.99


def test_cosine_zero_vector_returns_zero() -> None:
    zero = np.zeros(8, dtype=np.float32)
    nonzero = _normalize(np.ones(8, dtype=np.float32))
    assert sim.cosine_similarity(zero, nonzero) == 0.0


def test_cosine_shape_mismatch_raises() -> None:
    a = np.ones(4, dtype=np.float32)
    b = np.ones(5, dtype=np.float32)
    with pytest.raises(sim.SimilarityError):
        sim.cosine_similarity(a, b)


def test_reference_similarity_with_mocked_embedder(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """End-to-end with mocked ``speaker_embedding`` — verifies wiring + cosine math."""
    # Create two distinct fake embeddings keyed by path.
    embeddings = {
        str(tmp_path / "ref.wav"): _normalize(np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)),
        str(tmp_path / "gen.wav"): _normalize(np.array([1.1, 2.1, 3.1, 4.1], dtype=np.float32)),
    }

    # The two paths are touched so any future check that they exist passes.
    for p in embeddings:
        with open(p, "wb") as fh:
            fh.write(b"\x00")

    def fake_embed(path):  # noqa: ANN001 - test stub
        return embeddings[str(path)]

    monkeypatch.setattr(sim, "speaker_embedding", fake_embed)

    score = sim.reference_similarity(tmp_path / "ref.wav", tmp_path / "gen.wav")
    # The two near-parallel vectors should produce a very high cosine.
    assert 0.99 < score <= 1.0


def test_reference_similarity_propagates_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_path):  # noqa: ANN001 - test stub
        raise RuntimeError("decode error")

    monkeypatch.setattr(sim, "speaker_embedding", boom)
    with pytest.raises(sim.SimilarityError):
        sim.reference_similarity("a.wav", "b.wav")


@pytest.mark.skipif(
    os.environ.get("RUN_SPEECHBRAIN_TESTS") != "1",
    reason="set RUN_SPEECHBRAIN_TESTS=1 to exercise real speechbrain inference",
)
def test_speechbrain_real_inference(tmp_path) -> None:
    """Generate a sine wave, run real ECAPA-TDNN, expect a 192-dim normalized vector."""
    import soundfile as sf

    sr = 16000
    duration = 3.0
    t = np.arange(int(sr * duration), dtype=np.float32) / sr
    audio = 0.2 * np.sin(2 * np.pi * 220.0 * t)
    path = tmp_path / "sine.wav"
    sf.write(str(path), audio, sr)

    emb = sim.speaker_embedding(path)
    assert emb.dtype == np.float32
    assert emb.ndim == 1
    assert emb.shape[0] == 192
    # L2-normalized.
    assert np.linalg.norm(emb) == pytest.approx(1.0, abs=1e-3)
