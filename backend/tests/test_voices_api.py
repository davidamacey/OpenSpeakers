"""Tests for voice profile reference-transcript and ASR endpoints (Phase 1 / 1A).

These exercise the surface added in
``backend/app/api/endpoints/voices.py``:
- POST /api/voices  with / without ``reference_text``
- PATCH /api/voices/{id}  flipping status to ``manual`` or ``pending``
- POST /api/voices/{id}/transcribe  re-running ASR
- Validation: length cap and control-character rejection.

Style mirrors ``test_smoke.py``: FastAPI ``TestClient`` against the real
app via the session-scoped ``client`` fixture in ``conftest.py``.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

# Default model to attach the test profile to. Kokoro is always registered
# (standby model) and the upload endpoint doesn't actually validate that the
# model supports cloning — it just stores the audio + dispatches tasks.
DEFAULT_MODEL_ID = "kokoro"


@pytest.fixture
def wav_file(tmp_path: Path) -> Path:
    """Write a 2-second 440 Hz sine into a temp WAV and return its path."""
    sr = 22050
    duration = 2.0
    t = np.arange(int(sr * duration), dtype=np.float32) / sr
    audio = (0.2 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    path = tmp_path / "ref.wav"
    sf.write(str(path), audio, sr)
    return path


@pytest.fixture(autouse=True)
def _stub_celery_dispatches(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Replace Celery ``apply_async`` calls so tests don't require running workers.

    Returns a dict tracking how many times each task was dispatched so the
    individual tests can assert on it. Autouse so every test in the module
    benefits — voices.py dispatches both ``clone_voice`` and ``transcribe_reference``
    on POST/PATCH/transcribe paths.
    """
    calls: dict[str, list[Any]] = {"clone": [], "asr": []}

    from app.tasks import tts_tasks

    def _fake_clone_apply_async(*args: Any, **kwargs: Any) -> None:
        calls["clone"].append({"args": args, "kwargs": kwargs})
        return None

    monkeypatch.setattr(tts_tasks.clone_voice, "apply_async", _fake_clone_apply_async)

    # ``transcribe_reference`` is imported lazily inside the endpoint, so we
    # patch on the module rather than at the import site.
    from app.tasks import asr_tasks

    def _fake_asr_apply_async(*args: Any, **kwargs: Any) -> None:
        calls["asr"].append({"args": args, "kwargs": kwargs})
        return None

    monkeypatch.setattr(asr_tasks.transcribe_reference, "apply_async", _fake_asr_apply_async)
    return calls


def create_voice(
    client: TestClient,
    name: str,
    model_id: str,
    wav_path: Path,
    **extras: str,
) -> Any:
    """POST /api/voices/ with a multipart upload. ``extras`` add to the form."""
    with wav_path.open("rb") as fh:
        files = {"reference_audio": (wav_path.name, fh, "audio/wav")}
        data = {"name": name, "model_id": model_id, **extras}
        return client.post("/api/voices", files=files, data=data)


def _delete_voice(client: TestClient, voice_id: str) -> None:
    """Best-effort cleanup so the test DB doesn't accumulate rows."""
    with contextlib.suppress(Exception):
        client.delete(f"/api/voices/{voice_id}")


class TestCreateVoiceTranscript:
    def test_create_voice_with_manual_transcript(
        self,
        client: TestClient,
        wav_file: Path,
        _stub_celery_dispatches: dict[str, list[Any]],
    ) -> None:
        """Caller pre-fills the transcript: status should be ``manual`` and ASR not dispatched."""
        resp = create_voice(
            client,
            "manual-transcript",
            DEFAULT_MODEL_ID,
            wav_file,
            reference_text="Hello world.",
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        try:
            assert body["reference_text"] == "Hello world."
            assert body["reference_text_status"] == "manual"
            # ASR must NOT be dispatched when the user supplied the transcript.
            assert _stub_celery_dispatches["asr"] == []
            # ``clone_voice`` is always dispatched on create, regardless of transcript.
            assert len(_stub_celery_dispatches["clone"]) == 1
        finally:
            _delete_voice(client, body["id"])

    def test_create_voice_without_transcript_pending(
        self,
        client: TestClient,
        wav_file: Path,
        _stub_celery_dispatches: dict[str, list[Any]],
    ) -> None:
        """No transcript provided: response is ``pending`` and ASR is dispatched."""
        resp = create_voice(client, "auto-transcript", DEFAULT_MODEL_ID, wav_file)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        try:
            # The immediate response is the row as-just-created; ASR runs async
            # so we don't assert that it ever flips to ``ready`` here — that
            # would require a live worker-asr container.
            assert body["reference_text"] is None
            assert body["reference_text_status"] == "pending"
            # ASR should have been dispatched exactly once.
            assert len(_stub_celery_dispatches["asr"]) == 1
        finally:
            _delete_voice(client, body["id"])


class TestPatchTranscript:
    def test_patch_transcript_flips_to_manual(
        self,
        client: TestClient,
        wav_file: Path,
    ) -> None:
        """Editing a transcript via PATCH always wins — status becomes ``manual``."""
        resp = create_voice(client, "patch-test", DEFAULT_MODEL_ID, wav_file)
        assert resp.status_code == 201
        voice_id = resp.json()["id"]
        try:
            patch = client.patch(
                f"/api/voices/{voice_id}",
                json={"reference_text": "Edited."},
            )
            assert patch.status_code == 200, patch.text
            body = patch.json()
            assert body["reference_text"] == "Edited."
            assert body["reference_text_status"] == "manual"
        finally:
            _delete_voice(client, voice_id)

    def test_patch_transcript_to_empty_resets_to_pending(
        self,
        client: TestClient,
        wav_file: Path,
        _stub_celery_dispatches: dict[str, list[Any]],
    ) -> None:
        """Clearing the transcript flips status back to ``pending`` and re-dispatches ASR."""
        resp = create_voice(
            client,
            "patch-empty",
            DEFAULT_MODEL_ID,
            wav_file,
            reference_text="Initial transcript.",
        )
        assert resp.status_code == 201
        voice_id = resp.json()["id"]
        # Reset the dispatch tracker so we count only the PATCH-triggered ASR.
        _stub_celery_dispatches["asr"].clear()
        try:
            patch = client.patch(
                f"/api/voices/{voice_id}",
                json={"reference_text": ""},
            )
            assert patch.status_code == 200, patch.text
            body = patch.json()
            assert body["reference_text"] is None
            assert body["reference_text_status"] == "pending"
            # ASR re-dispatch is the documented contract.
            assert len(_stub_celery_dispatches["asr"]) == 1
        finally:
            _delete_voice(client, voice_id)


class TestTranscribeEndpoint:
    def test_post_transcribe_endpoint_resets_status(
        self,
        client: TestClient,
        wav_file: Path,
        _stub_celery_dispatches: dict[str, list[Any]],
    ) -> None:
        """POST /voices/{id}/transcribe clears text and resets status to ``pending``."""
        # Start from a ``manual`` profile so we can prove the reset.
        resp = create_voice(
            client,
            "transcribe-endpoint",
            DEFAULT_MODEL_ID,
            wav_file,
            reference_text="Some manual transcript.",
        )
        assert resp.status_code == 201
        voice_id = resp.json()["id"]
        _stub_celery_dispatches["asr"].clear()
        try:
            r = client.post(f"/api/voices/{voice_id}/transcribe")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reference_text"] is None
            assert body["reference_text_status"] == "pending"
            assert len(_stub_celery_dispatches["asr"]) == 1
        finally:
            _delete_voice(client, voice_id)


class TestTranscriptValidation:
    def test_create_voice_transcript_too_long_rejects(
        self,
        client: TestClient,
        wav_file: Path,
    ) -> None:
        """5000-char transcript exceeds the 4000-char cap → 422."""
        too_long = "a" * 5000
        resp = create_voice(
            client,
            "too-long",
            DEFAULT_MODEL_ID,
            wav_file,
            reference_text=too_long,
        )
        assert resp.status_code == 422, resp.text
        # Don't bother cleaning up — the row was never created.

    def test_create_voice_transcript_with_control_chars_rejects_or_strips(
        self,
        client: TestClient,
        wav_file: Path,
    ) -> None:
        """Embedded \\x01 control char must either be rejected (422) or stripped.

        The validator in ``app.schemas.voices._normalise_reference_text`` raises
        on disallowed control chars (anything < 0x20 except \\n / \\t), so 422
        is the expected behavior. The test accepts the alternative for
        forward-compatibility in case the validator is relaxed.
        """
        resp = create_voice(
            client,
            "ctrl-chars",
            DEFAULT_MODEL_ID,
            wav_file,
            reference_text="hello\x01world",
        )
        if resp.status_code == 422:
            return
        # Otherwise must have stripped the control char from the response.
        assert resp.status_code == 201, resp.text
        body = resp.json()
        try:
            stored = body.get("reference_text") or ""
            assert "\x01" not in stored
        finally:
            _delete_voice(client, body["id"])
