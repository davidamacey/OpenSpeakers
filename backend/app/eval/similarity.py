"""Speaker-similarity scoring via speechbrain ECAPA-TDNN.

Provides an objective cosine-similarity score in [-1, 1] between a reference
and a generated audio clip. The model (`speechbrain/spkrec-ecapa-voxceleb`)
runs on **CPU** to avoid contending with TTS workers on GPU 0.

Public API:
    speaker_embedding(audio_path) -> np.ndarray   # 192-dim L2-normalized
    cosine_similarity(a, b) -> float              # in [-1, 1]
    reference_similarity(ref, gen) -> float       # end-to-end

The first call lazily downloads the model (~80 MB) into
`settings.MODEL_CACHE_DIR / "speechbrain" / "spkrec-ecapa-voxceleb"`.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from app.core.config import settings

if TYPE_CHECKING:  # pragma: no cover — typing only
    import torch

logger = logging.getLogger(__name__)

# Speaker embedding model: ECAPA-TDNN trained on VoxCeleb.
# 192-dim embeddings; same-speaker cosine ≥ 0.5 is the conventional "match" threshold.
_MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
_TARGET_SR = 16000  # ECAPA-TDNN expects 16 kHz mono.
_MIN_SECONDS = 2.0  # Pad shorter clips up to this length for stable embeddings.

_model = None
_model_lock = threading.Lock()


class SimilarityError(RuntimeError):
    """Raised when speaker-similarity computation fails for any reason."""


def _savedir() -> str:
    """Where speechbrain caches its weights. Uses AUDIO_OUTPUT_DIR rather than
    MODEL_CACHE_DIR because AUDIO_OUTPUT_DIR is the volume reliably bind-mounted
    across every worker container; MODEL_CACHE_DIR may be a host-only path."""
    return str(
        Path(settings.AUDIO_OUTPUT_DIR) / "_models" / "speechbrain" / "spkrec-ecapa-voxceleb"
    )


def _get_model() -> Any:
    """Lazy-load the speechbrain EncoderClassifier singleton (CPU)."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        # speechbrain 1.0 still imports torchaudio.list_audio_backends, which
        # was removed in torchaudio 2.10. Provide a shim before the import so
        # the lookup falls back to soundfile (the same workaround Fish Speech
        # uses).
        try:
            import torchaudio

            if not hasattr(torchaudio, "list_audio_backends"):
                torchaudio.list_audio_backends = lambda: ["soundfile"]
        except ImportError:  # pragma: no cover - speechbrain import will fail next
            pass

        try:
            # Local import — speechbrain is heavy and only present in workers
            # that actually run similarity scoring (worker-kokoro per the plan).
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as exc:  # pragma: no cover - import-time path
            raise SimilarityError(
                "speechbrain is not installed in this container. Install "
                "`speechbrain` to enable speaker-similarity scoring."
            ) from exc

        savedir = _savedir()
        Path(savedir).mkdir(parents=True, exist_ok=True)
        logger.info("Loading speechbrain ECAPA-TDNN from %s (savedir=%s)", _MODEL_SOURCE, savedir)

        # Workers run with HF_HUB_OFFLINE=1 for production reproducibility, but
        # the speechbrain weights aren't pre-baked into the image. Lift the
        # restriction for the one-time download; subsequent loads hit the cache
        # under savedir and don't need network access.
        prev_offline = os.environ.pop("HF_HUB_OFFLINE", None)
        try:
            _model = EncoderClassifier.from_hparams(
                source=_MODEL_SOURCE,
                savedir=savedir,
                run_opts={"device": "cpu"},
            )
        finally:
            if prev_offline is not None:
                os.environ["HF_HUB_OFFLINE"] = prev_offline
        return _model


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm < 1e-8:
        # Degenerate (all-zero) embedding — return as-is; cosine will be 0.
        return vec.astype(np.float32, copy=False)
    return (vec / norm).astype(np.float32, copy=False)


def _load_audio_mono_16k(audio_path: str | Path) -> torch.Tensor:
    """Load audio file → mono float32 tensor at 16 kHz, padded to ≥ _MIN_SECONDS."""
    import torch
    import torchaudio

    path = str(audio_path)
    waveform, sr = torchaudio.load(path)  # shape: (channels, samples)
    if waveform.ndim != 2 or waveform.shape[1] == 0:
        raise SimilarityError(f"audio file decoded to empty waveform: {path!r}")

    # Mono: average channels.
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    # Resample to 16 kHz if needed.
    if sr != _TARGET_SR:
        waveform = torchaudio.functional.resample(waveform, orig_freq=sr, new_freq=_TARGET_SR)

    # Pad with zeros up to _MIN_SECONDS to give ECAPA enough context.
    min_samples = int(_MIN_SECONDS * _TARGET_SR)
    if waveform.shape[1] < min_samples:
        pad_amount = min_samples - waveform.shape[1]
        waveform = torch.nn.functional.pad(waveform, (0, pad_amount))

    return waveform


def speaker_embedding(audio_path: str | Path) -> np.ndarray:
    """Return a 192-dim L2-normalized speaker embedding (numpy float32).

    The audio is loaded with torchaudio, downmixed to mono, resampled to 16 kHz,
    and padded to at least 2 seconds before being passed to the ECAPA-TDNN encoder.
    """
    try:
        waveform = _load_audio_mono_16k(audio_path)
        model = _get_model()
        with _model_lock:
            # encode_batch expects (batch, samples). Our waveform is (1, samples).
            emb = model.encode_batch(waveform)
        emb_np = emb.squeeze().detach().cpu().numpy().astype(np.float32, copy=False)
        if emb_np.ndim != 1:
            emb_np = emb_np.reshape(-1)
        return _l2_normalize(emb_np)
    except SimilarityError:
        raise
    except Exception as exc:
        raise SimilarityError(
            f"failed to compute speaker embedding for {audio_path!r}: {exc}"
        ) from exc


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity in [-1, 1]. Both inputs assumed L2-normalized."""
    if a.shape != b.shape:
        raise SimilarityError(f"embedding shape mismatch: {a.shape} vs {b.shape}")
    # Even though both are normalized, guard against numerical drift.
    denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    if denom < 1e-8:
        return 0.0
    score = float(np.dot(a, b) / denom)
    # Clip to [-1, 1] to absorb tiny floating-point overshoots.
    return max(-1.0, min(1.0, score))


def reference_similarity(ref_audio: str | Path, gen_audio: str | Path) -> float:
    """End-to-end: embed both, return cosine similarity in [-1, 1].

    Pads either clip to ≥ 2 s if shorter (per Edge cases — Phase 5).
    Raises ``SimilarityError`` on any failure; callers may swallow.
    """
    try:
        ref_emb = speaker_embedding(ref_audio)
        gen_emb = speaker_embedding(gen_audio)
        return cosine_similarity(ref_emb, gen_emb)
    except SimilarityError:
        raise
    except Exception as exc:
        raise SimilarityError(f"reference_similarity failed: {exc}") from exc
