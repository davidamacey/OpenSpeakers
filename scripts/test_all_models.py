#!/usr/bin/env python3
"""Comprehensive TTS model test script for OpenSpeakers.

Tests every registered model by submitting a TTS generation job,
polling for completion, and verifying the audio output is accessible.

Usage:
    python3 /tmp/test_all_models.py
    python3 /tmp/test_all_models.py --models kokoro,vibevoice
    python3 /tmp/test_all_models.py --timeout 300
"""
from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from argparse import ArgumentParser
from dataclasses import dataclass, field
from pathlib import Path

# Pin all GPU work to slot 0 (RTX A6000). Every cloning model is expected to
# run on this device; the user's GPU 1 is reserved for OpenTranscribe and
# slot 2 is reserved for vLLM. Setdefault means callers can still override
# explicitly via the environment.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

# ── Configuration ───────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8080/api"
DEFAULT_TIMEOUT = 300  # 5 minutes per model (includes hot-swap load time)
POLL_INTERVAL = 3  # seconds between status polls
TEST_TEXT = "Hello, this is a comprehensive test of the text to speech system."

# Queue routing — mirrors backend/app/api/endpoints/tts.py QUEUE_MAP
QUEUE_MAP: dict[str, str] = {
    "fish-speech-s2": "tts.fish-speech",
    "qwen3-tts": "tts.qwen3",
    "orpheus-3b": "tts.orpheus",
    "f5-tts": "tts.f5-tts",
    "chatterbox": "tts.f5-tts",
    "cosyvoice-2": "tts.f5-tts",
    "parler-tts": "tts.f5-tts",
    "dia-1b": "tts.dia",
    "kokoro": "tts.kokoro",
}

# Workers and which queues they consume
WORKER_QUEUES: dict[str, str] = {
    "worker": "tts",
    "worker-kokoro": "tts.kokoro",
    "worker-fish": "tts.fish-speech",
    "worker-qwen3": "tts.qwen3",
    "worker-orpheus": "tts.orpheus",
    "worker-dia": "tts.dia",
    "worker-f5": "tts.f5-tts",
}

# Per-model test text overrides (e.g. dialogue models need [S1]/[S2] format)
MODEL_TEST_TEXT: dict[str, str] = {
    "dia-1b": "[S1] Hello, this is speaker one testing the dialogue system. [S2] And this is speaker two responding.",
}


@dataclass
class TestResult:
    model_id: str
    model_name: str
    status: str = "not_tested"  # pass, fail, timeout, skipped, no_worker
    error_message: str = ""
    duration_seconds: float = 0.0
    processing_time_ms: int = 0
    audio_accessible: bool = False
    wall_time_seconds: float = 0.0
    queue: str = ""
    notes: list[str] = field(default_factory=list)


def api_get(path: str) -> dict | list:
    """GET request to API, returns parsed JSON."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_post(path: str, data: dict) -> dict:
    """POST request to API with JSON body, returns parsed JSON."""
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_head(path: str) -> int:
    """HEAD request, returns HTTP status code."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def fetch_models() -> list[dict]:
    """Fetch all registered models from the API."""
    return api_get("/models")


def submit_job(model_id: str) -> str:
    """Submit a TTS job, return job_id."""
    text = MODEL_TEST_TEXT.get(model_id, TEST_TEXT)
    payload = {
        "model_id": model_id,
        "text": text,
        "language": "en",
    }
    resp = api_post("/tts/generate", payload)
    return resp["job_id"]


def poll_job(job_id: str, timeout: int) -> dict:
    """Poll job status until terminal state or timeout."""
    start = time.monotonic()
    last_status = ""
    while True:
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            return {"status": "timeout", "elapsed": elapsed}

        try:
            job = api_get(f"/tts/jobs/{job_id}")
        except Exception as e:
            print(f"    [!] Poll error: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        status = job.get("status", "unknown")
        if status != last_status:
            print(f"    [{elapsed:5.1f}s] Status: {status}")
            last_status = status

        if status in ("complete", "failed", "cancelled"):
            job["elapsed"] = elapsed
            return job

        time.sleep(POLL_INTERVAL)


def check_audio(job_id: str) -> bool:
    """Verify the audio file is accessible via GET (use HEAD-like approach)."""
    try:
        # Use GET but only read a small amount
        url = f"{BASE_URL}/tts/jobs/{job_id}/audio"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            # Read just the first 100 bytes to confirm it's audio
            header = resp.read(100)
            # WAV files start with RIFF
            if header[:4] == b"RIFF":
                return True
            # Could be MP3 or OGG
            if len(header) > 0:
                return True
            return False
    except Exception:
        return False


def test_model(model_info: dict, timeout: int) -> TestResult:
    """Run a full test cycle for one model."""
    model_id = model_info["id"]
    model_name = model_info.get("name", model_id)
    queue = QUEUE_MAP.get(model_id, "tts")

    result = TestResult(
        model_id=model_id,
        model_name=model_name,
        queue=queue,
    )

    # Check if a worker exists for this queue
    has_worker = any(q == queue for q in WORKER_QUEUES.values())
    if not has_worker:
        result.status = "no_worker"
        result.error_message = f"No worker consuming queue '{queue}'"
        result.notes.append(f"Queue '{queue}' has no running worker")
        return result

    print(f"\n{'='*60}")
    print(f"Testing: {model_name} ({model_id})")
    print(f"  Queue: {queue}")
    print(f"  VRAM estimate: {model_info.get('vram_gb_estimate', '?')} GB")
    print(f"  Streaming: {model_info.get('supports_streaming', False)}")
    print(f"  Voice cloning: {model_info.get('supports_voice_cloning', False)}")
    print(f"{'='*60}")

    wall_start = time.monotonic()

    # Submit job
    try:
        print(f"  Submitting TTS job...")
        job_id = submit_job(model_id)
        print(f"  Job ID: {job_id}")
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        result.status = "fail"
        result.error_message = f"HTTP {e.code} on submit: {body}"
        result.wall_time_seconds = time.monotonic() - wall_start
        print(f"  [FAIL] Submit failed: HTTP {e.code}: {body}")
        return result
    except Exception as e:
        result.status = "fail"
        result.error_message = f"Submit error: {e}"
        result.wall_time_seconds = time.monotonic() - wall_start
        print(f"  [FAIL] Submit error: {e}")
        return result

    # Poll for completion
    print(f"  Polling for completion (timeout={timeout}s)...")
    job = poll_job(job_id, timeout)
    result.wall_time_seconds = time.monotonic() - wall_start

    status = job.get("status", "unknown")

    if status == "timeout":
        result.status = "timeout"
        result.error_message = f"Timed out after {timeout}s"
        print(f"  [TIMEOUT] Job did not complete within {timeout}s")
        return result

    if status == "complete":
        result.status = "pass"
        result.duration_seconds = job.get("duration_seconds") or 0.0
        result.processing_time_ms = job.get("processing_time_ms") or 0

        # Verify audio accessibility
        print(f"  Verifying audio file...")
        result.audio_accessible = check_audio(job_id)
        if result.audio_accessible:
            print(f"  [PASS] Audio verified (duration={result.duration_seconds:.1f}s, "
                  f"processing={result.processing_time_ms}ms)")
        else:
            result.status = "fail"
            result.error_message = "Job completed but audio file not accessible"
            result.notes.append("Audio file missing or unreadable")
            print(f"  [FAIL] Audio file not accessible")
    elif status == "failed":
        result.status = "fail"
        result.error_message = job.get("error_message", "Unknown error")
        print(f"  [FAIL] {result.error_message}")
    elif status == "cancelled":
        result.status = "fail"
        result.error_message = "Job was cancelled"
        print(f"  [FAIL] Job was cancelled")
    else:
        result.status = "fail"
        result.error_message = f"Unexpected status: {status}"
        print(f"  [FAIL] Unexpected status: {status}")

    return result


def print_summary(results: list[TestResult]) -> None:
    """Print a formatted summary table."""
    print(f"\n\n{'#'*70}")
    print(f"#  TEST SUMMARY")
    print(f"{'#'*70}\n")

    # Header
    print(f"{'Model':<25} {'Status':<12} {'Queue':<20} {'Duration':<10} {'Process':<12} {'Audio':<7} {'Wall':<8}")
    print(f"{'-'*25} {'-'*12} {'-'*20} {'-'*10} {'-'*12} {'-'*7} {'-'*8}")

    passed = 0
    failed = 0
    timed_out = 0
    no_worker = 0

    for r in results:
        if r.status == "pass":
            icon = "[PASS]"
            passed += 1
        elif r.status == "fail":
            icon = "[FAIL]"
            failed += 1
        elif r.status == "timeout":
            icon = "[TIME]"
            timed_out += 1
        elif r.status == "no_worker":
            icon = "[NOWR]"
            no_worker += 1
        else:
            icon = "[????]"

        dur = f"{r.duration_seconds:.1f}s" if r.duration_seconds else "-"
        proc = f"{r.processing_time_ms}ms" if r.processing_time_ms else "-"
        audio = "OK" if r.audio_accessible else "-"
        wall = f"{r.wall_time_seconds:.1f}s" if r.wall_time_seconds else "-"

        print(f"{r.model_name:<25} {icon:<12} {r.queue:<20} {dur:<10} {proc:<12} {audio:<7} {wall:<8}")

    print(f"\n{'='*70}")
    print(f"Total: {len(results)} models | "
          f"Passed: {passed} | Failed: {failed} | Timeout: {timed_out} | No Worker: {no_worker}")
    print(f"{'='*70}")

    # Detailed failure report
    failures = [r for r in results if r.status in ("fail", "timeout", "no_worker")]
    if failures:
        print(f"\n\n{'='*70}")
        print(f"FAILURE DETAILS")
        print(f"{'='*70}")
        for r in failures:
            print(f"\n  {r.model_name} ({r.model_id})")
            print(f"    Status: {r.status}")
            print(f"    Queue:  {r.queue}")
            if r.error_message:
                # Truncate very long error messages
                msg = r.error_message
                if len(msg) > 500:
                    msg = msg[:500] + "..."
                print(f"    Error:  {msg}")
            for note in r.notes:
                print(f"    Note:   {note}")


# ── Cloning round-trip mode ─────────────────────────────────────────────────
#
# `--cloning` exercises every cloning-capable model end-to-end:
#   1) Generate one Kokoro reference clip with a known transcript.
#   2) Upload it as a VoiceProfile under each cloning model with the known
#      transcript pre-filled (so we don't depend on faster-whisper).
#   3) Submit a TTS job using that profile, poll to completion, fetch audio.
#   4) Compute speaker similarity between the Kokoro reference and the
#      cloned output via `scripts/eval_speaker_similarity.py` (or the
#      in-process module if importable).
#   5) PASS iff similarity >= CLONING_SIMILARITY_THRESHOLD.

CLONING_REFERENCE_PATH = Path("/tmp/openspeakers_ref.wav")
CLONING_REFERENCE_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "This is a test of the voice cloning system."
)
CLONING_GEN_TEXT = "Hello, this is a quick test of cloning."
CLONING_SIMILARITY_THRESHOLD = 0.4

# Cloning-capable target models. Kokoro is the *source* for the reference
# clip, not a clone target. Orpheus and Parler do not support cloning.
CLONING_MODELS: list[str] = [
    "fish-speech-s2",
    "vibevoice-1.5b",
    "qwen3-tts",
    "f5-tts",
    "chatterbox",
    "cosyvoice-2",
    "dia-1b",
]

# Some cloning models need their text in a special format (Dia uses [S1]/[S2]).
CLONING_TEXT_OVERRIDE: dict[str, str] = {
    "dia-1b": "[S1] Hello, this is a quick test of cloning.",
}


@dataclass
class CloningResult:
    model_id: str
    status: str = "not_tested"  # pass, fail, skipped
    similarity: float | None = None
    duration_seconds: float = 0.0
    error_message: str = ""
    voice_id: str | None = None


def api_post_multipart(path: str, *, data: dict, files: dict) -> dict:
    """POST a multipart/form-data request via the stdlib (no requests dependency).

    ``files`` is ``{name: (filename, bytes, content_type)}`` mirroring requests.
    """
    boundary = f"----openspeakers{uuid.uuid4().hex}"
    body_parts: list[bytes] = []
    for k, v in data.items():
        body_parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
                f"{v}\r\n"
            ).encode()
        )
    for field_name, (filename, content, ctype) in files.items():
        body_parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n"
            ).encode()
        )
        body_parts.append(content)
        body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(body_parts)

    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def api_delete(path: str) -> int:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def download_audio(job_id: str, dest: Path) -> None:
    """Stream the generated audio to ``dest``."""
    url = f"{BASE_URL}/tts/jobs/{job_id}/audio"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)


def submit_clone_job(model_id: str, voice_id: str) -> str:
    """Submit a TTS job using a voice profile, return the job_id."""
    text = CLONING_TEXT_OVERRIDE.get(model_id, CLONING_GEN_TEXT)
    payload = {
        "model_id": model_id,
        "text": text,
        "language": "en",
        "voice_profile_id": voice_id,
    }
    return api_post("/tts/generate", payload)["job_id"]


def generate_kokoro_reference(timeout: int) -> Path:
    """Use Kokoro to synthesize the known reference text, save WAV to disk."""
    print(f"\n  Generating Kokoro reference clip → {CLONING_REFERENCE_PATH}")
    payload = {
        "model_id": "kokoro",
        "text": CLONING_REFERENCE_TEXT,
        "language": "en",
    }
    job_id = api_post("/tts/generate", payload)["job_id"]
    job = poll_job(job_id, timeout)
    if job.get("status") != "complete":
        raise RuntimeError(
            f"Kokoro reference generation failed: status={job.get('status')} "
            f"err={job.get('error_message')}"
        )
    download_audio(job_id, CLONING_REFERENCE_PATH)
    size = CLONING_REFERENCE_PATH.stat().st_size
    print(f"  Reference WAV written: {size} bytes")
    return CLONING_REFERENCE_PATH


def upload_reference_as_voice(model_id: str, ref_path: Path, name: str) -> str:
    """POST /api/voices with the reference WAV + the known transcript.

    Pre-filling ``reference_text`` skips the ASR worker, which we can't
    assume is running.
    """
    ctype = mimetypes.guess_type(str(ref_path))[0] or "audio/wav"
    with ref_path.open("rb") as fh:
        content = fh.read()
    body = api_post_multipart(
        "/voices",
        data={
            "name": name,
            "model_id": model_id,
            "reference_text": CLONING_REFERENCE_TEXT,
        },
        files={"reference_audio": (ref_path.name, content, ctype)},
    )
    return body["id"]


def compute_similarity(ref: Path, gen: Path) -> float:
    """Compute speaker similarity. Prefer the in-process module; fall back
    to ``scripts/eval_speaker_similarity.py`` so this works whether we're
    running on the host or inside a container."""
    try:
        from app.eval.similarity import reference_similarity  # type: ignore

        return float(reference_similarity(str(ref), str(gen)))
    except ImportError:
        pass

    script = Path(__file__).parent / "eval_speaker_similarity.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(ref), str(gen)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"eval_speaker_similarity.py failed: {proc.stderr.strip() or proc.stdout!r}"
        )
    return float(proc.stdout.strip().splitlines()[-1])


def run_cloning_test(
    model_id: str, ref_path: Path, timeout: int, keep: bool
) -> CloningResult:
    result = CloningResult(model_id=model_id)
    print(f"\n{'='*60}")
    print(f"Cloning test: {model_id}")
    print(f"{'='*60}")

    # 1) Upload the Kokoro reference as a voice profile under this model.
    try:
        voice_id = upload_reference_as_voice(
            model_id, ref_path, name=f"clonetest-{model_id}-{uuid.uuid4().hex[:8]}"
        )
        result.voice_id = voice_id
        print(f"  Voice profile created: {voice_id}")
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        result.status = "fail"
        result.error_message = f"voice upload HTTP {e.code}: {body}"
        print(f"  [FAIL] {result.error_message}")
        return result
    except Exception as e:
        result.status = "fail"
        result.error_message = f"voice upload error: {e}"
        print(f"  [FAIL] {result.error_message}")
        return result

    # Brief pause so clone_voice has a moment to populate extra_info — most
    # models rely on it. Not strictly required; the worker will block on
    # the lock anyway.
    time.sleep(2)

    # 2) Submit a generation job using the cloned voice.
    try:
        job_id = submit_clone_job(model_id, voice_id)
        print(f"  Cloning job submitted: {job_id}")
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        result.status = "fail"
        result.error_message = f"job submit HTTP {e.code}: {body}"
        print(f"  [FAIL] {result.error_message}")
        if not keep:
            api_delete(f"/voices/{voice_id}")
        return result

    job = poll_job(job_id, timeout)
    status = job.get("status")
    if status != "complete":
        result.status = "fail"
        result.error_message = (
            f"job ended in {status}: {job.get('error_message') or '(no msg)'}"
        )
        print(f"  [FAIL] {result.error_message}")
        if not keep:
            api_delete(f"/voices/{voice_id}")
        return result
    result.duration_seconds = float(job.get("duration_seconds") or 0.0)

    # 3) Download the audio and score it against the reference.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        gen_path = Path(tf.name)
    try:
        download_audio(job_id, gen_path)
        print(f"  Generated audio: {gen_path} ({gen_path.stat().st_size} bytes)")

        try:
            score = compute_similarity(ref_path, gen_path)
        except Exception as e:
            result.status = "fail"
            result.error_message = f"similarity scoring failed: {e}"
            print(f"  [FAIL] {result.error_message}")
            return result

        result.similarity = score
        if score >= CLONING_SIMILARITY_THRESHOLD:
            result.status = "pass"
            print(f"  [PASS] similarity={score:.3f} (>= {CLONING_SIMILARITY_THRESHOLD})")
        else:
            result.status = "fail"
            result.error_message = (
                f"similarity {score:.3f} below threshold "
                f"{CLONING_SIMILARITY_THRESHOLD}"
            )
            print(f"  [FAIL] {result.error_message}")
    finally:
        gen_path.unlink(missing_ok=True)
        if not keep and result.voice_id:
            api_delete(f"/voices/{result.voice_id}")

    return result


def print_cloning_summary(results: list[CloningResult]) -> None:
    print(f"\n\n{'#'*70}")
    print("#  CLONING SUMMARY")
    print(f"{'#'*70}\n")
    print(f"{'Model':<20} {'Duration':<12} {'Similarity':<12} {'Result':<8}")
    print(f"{'-'*20} {'-'*12} {'-'*12} {'-'*8}")
    for r in results:
        sim_str = f"{r.similarity:.3f}" if r.similarity is not None else "-"
        dur = f"{r.duration_seconds:.1f}s" if r.duration_seconds else "-"
        verdict = "PASS" if r.status == "pass" else "FAIL"
        print(f"{r.model_id:<20} {dur:<12} {sim_str:<12} {verdict:<8}")
        if r.status != "pass" and r.error_message:
            print(f"    -> {r.error_message}")
    passed = sum(1 for r in results if r.status == "pass")
    total = len(results)
    print(f"\n{passed}/{total} cloning models passed "
          f"(threshold: similarity >= {CLONING_SIMILARITY_THRESHOLD}).")


def run_cloning_suite(args) -> int:
    """Drive the cloning round-trip for every cloning-capable model.

    Returns process exit code (0 = all pass, 1 = any fail).
    """
    print("OpenSpeakers Cloning Round-Trip Suite")
    print(f"{'='*40}")
    print(f"API Base: {BASE_URL}")
    print(f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '?')}")
    print(f"Reference text: {CLONING_REFERENCE_TEXT!r}")
    print(f"Generation text: {CLONING_GEN_TEXT!r}")
    print(f"Threshold: similarity >= {CLONING_SIMILARITY_THRESHOLD}")

    # Determine target list (allow filtering via --models / --skip).
    targets = list(CLONING_MODELS)
    if args.models:
        wanted = set(args.models.split(","))
        targets = [m for m in targets if m in wanted]
    if args.skip:
        skip = set(args.skip.split(","))
        targets = [m for m in targets if m not in skip]
    if not targets:
        print("No cloning models selected after filtering.")
        return 0
    print(f"Cloning targets: {targets}")

    # Generate the Kokoro reference once.
    try:
        ref_path = generate_kokoro_reference(args.timeout)
    except Exception as e:
        print(f"FATAL: cannot generate Kokoro reference clip: {e}")
        return 1

    results: list[CloningResult] = []
    for i, model_id in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] ", end="")
        results.append(run_cloning_test(model_id, ref_path, args.timeout, args.keep))
        if i < len(targets):
            print("\n  Waiting 5s before next model...")
            time.sleep(5)

    print_cloning_summary(results)
    return 0 if all(r.status == "pass" for r in results) else 1


def main() -> None:
    parser = ArgumentParser(description="Test all OpenSpeakers TTS models")
    parser.add_argument("--models", type=str, default="",
                        help="Comma-separated list of model IDs to test (default: all)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Timeout per model in seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--skip", type=str, default="",
                        help="Comma-separated list of model IDs to skip")
    parser.add_argument("--cloning", action="store_true",
                        help="Run cloning round-trip tests across all cloning-capable models "
                             "with speaker-similarity assertions (>= "
                             f"{CLONING_SIMILARITY_THRESHOLD}).")
    parser.add_argument("--keep", action="store_true",
                        help="In --cloning mode, skip cleanup of generated voice profiles.")
    args = parser.parse_args()

    if args.cloning:
        sys.exit(run_cloning_suite(args))

    print(f"OpenSpeakers TTS Model Test Suite")
    print(f"{'='*40}")
    print(f"API Base: {BASE_URL}")
    print(f"Timeout per model: {args.timeout}s")
    print(f"Test text: {TEST_TEXT!r}")

    # Fetch models
    print(f"\nFetching registered models...")
    try:
        models = fetch_models()
    except Exception as e:
        print(f"FATAL: Cannot reach API at {BASE_URL}: {e}")
        sys.exit(1)

    print(f"Found {len(models)} registered models:")
    for m in models:
        queue = QUEUE_MAP.get(m["id"], "tts")
        has_worker = any(q == queue for q in WORKER_QUEUES.values())
        worker_status = "has worker" if has_worker else "NO WORKER"
        print(f"  - {m['name']:25s} ({m['id']:20s}) queue={queue:20s} [{worker_status}]")

    # Filter models if requested
    if args.models:
        selected = set(args.models.split(","))
        models = [m for m in models if m["id"] in selected]
        print(f"\nFiltered to {len(models)} models: {[m['id'] for m in models]}")

    if args.skip:
        skip_set = set(args.skip.split(","))
        models = [m for m in models if m["id"] not in skip_set]
        print(f"\nAfter skipping: {len(models)} models")

    # Test each model sequentially
    results: list[TestResult] = []
    total = len(models)

    for i, model_info in enumerate(models, 1):
        print(f"\n[{i}/{total}] ", end="")
        result = test_model(model_info, args.timeout)
        results.append(result)

        # Brief pause between models to let GPU settle
        if i < total:
            print(f"\n  Waiting 5s before next model...")
            time.sleep(5)

    print_summary(results)

    # Exit code: 0 if all pass, 1 if any fail
    any_fail = any(r.status in ("fail", "timeout") for r in results)
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
