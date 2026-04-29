#!/usr/bin/env python3
"""Standalone CLI for speaker-similarity scoring.

Usage:
    python3 scripts/eval_speaker_similarity.py REF_AUDIO GEN_AUDIO

Prints a single cosine-similarity number in [-1, 1] with 4 decimals to stdout.

Two execution paths are tried, in order:

1. **In-process** — if ``app.eval.similarity`` is importable on the current
   ``PYTHONPATH`` (e.g. when running this from inside ``worker-kokoro`` after
   ``cd /app`` or with ``PYTHONPATH=/app/backend``), the score is computed
   directly. This is the fastest path.

2. **Container fallback** — if the in-process import fails, the script
   shells out to ``docker compose exec -T worker-kokoro python -m
   app.eval.cli REF GEN`` (when present) or runs the equivalent inline
   Python via ``docker compose exec``. The audio paths are copied into
   ``/tmp`` inside the container via ``docker cp`` first so the worker can
   read them without sharing a volume.

Exit codes:
    0   — similarity printed (whatever the value)
    2   — bad arguments / missing file / both paths failed
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKER_CONTAINER = "worker-kokoro"


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _try_in_process(ref: Path, gen: Path) -> float | None:
    """Compute similarity locally if the backend module is importable.

    Returns the score on success or ``None`` if the import fails (so the
    caller can fall back to the container path). Any *other* exception (e.g.
    decode error) is allowed to propagate — that's a real failure, not a
    "not installed" condition.
    """
    try:
        from app.eval.similarity import reference_similarity  # type: ignore
    except ImportError:
        return None
    return float(reference_similarity(str(ref), str(gen)))


def _try_via_docker(ref: Path, gen: Path) -> float | None:
    """Compute similarity by execing into the worker-kokoro container.

    Returns the score on success or ``None`` if Docker isn't available /
    the container isn't running.
    """
    if shutil.which("docker") is None:
        return None
    # Confirm the container is up.
    probe = subprocess.run(
        ["docker", "compose", "ps", "-q", WORKER_CONTAINER],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        return None

    container_id = probe.stdout.strip().splitlines()[0]
    # Stage the audio files inside the container so paths resolve regardless
    # of host bind mounts.
    with tempfile.TemporaryDirectory(prefix="speakersim_") as _:
        in_container_ref = f"/tmp/_sim_ref{ref.suffix or '.wav'}"
        in_container_gen = f"/tmp/_sim_gen{gen.suffix or '.wav'}"
        for src, dst in ((ref, in_container_ref), (gen, in_container_gen)):
            cp = subprocess.run(
                ["docker", "cp", str(src), f"{container_id}:{dst}"],
                capture_output=True,
                text=True,
            )
            if cp.returncode != 0:
                _err(f"docker cp failed: {cp.stderr.strip()}")
                return None

        # Run the in-container similarity computation. Print only the
        # number; we'll parse the last line of stdout below.
        snippet = (
            "from app.eval.similarity import reference_similarity; "
            f"print(reference_similarity({in_container_ref!r}, {in_container_gen!r}))"
        )
        run = subprocess.run(
            [
                "docker", "compose", "exec", "-T", WORKER_CONTAINER,
                "python", "-c", snippet,
            ],
            capture_output=True,
            text=True,
        )
        if run.returncode != 0:
            _err(f"docker compose exec failed: {run.stderr.strip()}")
            return None
        last_line = run.stdout.strip().splitlines()[-1]
        try:
            return float(last_line)
        except ValueError:
            _err(f"could not parse similarity from container output: {run.stdout!r}")
            return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compute speaker similarity (cosine in [-1, 1]) between two audio "
            "files using the speechbrain ECAPA-TDNN embedder. Tries in-process "
            "first (when the backend is importable), falls back to "
            f"`docker compose exec {WORKER_CONTAINER}` when not."
        )
    )
    parser.add_argument("ref_audio", type=Path, help="Reference audio file")
    parser.add_argument("gen_audio", type=Path, help="Generated audio file")
    args = parser.parse_args()

    for label, path in (("ref_audio", args.ref_audio), ("gen_audio", args.gen_audio)):
        if not path.exists():
            _err(f"{label} does not exist: {path}")
            return 2
        if not path.is_file():
            _err(f"{label} is not a file: {path}")
            return 2

    # Try in-process, then container, then give up.
    try:
        score = _try_in_process(args.ref_audio, args.gen_audio)
    except Exception as exc:  # decode / model errors — don't silently fall back
        _err(f"in-process similarity failed: {exc}")
        return 2

    if score is None:
        score = _try_via_docker(args.ref_audio, args.gen_audio)

    if score is None:
        _err(
            "Could not compute similarity: app.eval.similarity is not importable "
            f"and `{WORKER_CONTAINER}` is not running. Either run this from "
            "inside the worker container, or `docker compose up -d "
            f"{WORKER_CONTAINER}` first."
        )
        return 2

    print(f"{score:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
