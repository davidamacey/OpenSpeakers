"""WebSocket endpoint for real-time TTS job progress.

Architecture:
  1. Client submits POST /api/tts/generate → gets job_id
  2. Client immediately connects to ws://<host>/ws/jobs/<job_id>
  3. FastAPI WS handler subscribes to Redis pub/sub channel "job:<job_id>"
  4. Celery worker publishes progress events to that channel
  5. WS handler forwards events to the client in real time
  6. On complete/error the WS closes cleanly

Progress event schema (JSON):
  { "type": "progress",  "step": "model_loading", "percent": 45, "eta_seconds": 12 }
  { "type": "progress",  "step": "generating",    "percent": 72, "eta_seconds": 3  }
  { "type": "complete",  "job_id": "...", "audio_url": "/api/tts/jobs/.../audio", "duration": 4.2 }
  { "type": "error",     "message": "..." }
  { "type": "status",    "status": "running", "detail": "Loading VibeVoice 0.5B..." }
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from app.core.config import settings
from app.db.models import JobStatus, TTSJob

logger = logging.getLogger(__name__)

ws_router = APIRouter()

_REDIS_URL = settings.CELERY_BROKER_URL  # same Redis as Celery


def job_channel(job_id: str) -> str:
    return f"job:{job_id}"


@ws_router.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(websocket: WebSocket, job_id: str) -> None:
    """Stream real-time progress updates for a TTS job."""
    await websocket.accept()

    # Validate job_id
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        await websocket.send_json({"type": "error", "message": "Invalid job ID"})
        await websocket.close(code=1008)
        return

    # Check if job is already complete (no need to subscribe)
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == job_uuid).first()
        if not job:
            await websocket.send_json({"type": "error", "message": "Job not found"})
            await websocket.close(code=1008)
            return

        if job.status == JobStatus.COMPLETE:
            audio_url = f"/api/tts/jobs/{job_id}/audio"
            await websocket.send_json(
                {
                    "type": "complete",
                    "job_id": job_id,
                    "audio_url": audio_url,
                    "duration": job.duration_seconds,
                }
            )
            await websocket.close()
            return

        if job.status == JobStatus.FAILED:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": job.error_message or "Job failed",
                }
            )
            await websocket.close()
            return
    finally:
        db.close()

    # Subscribe to Redis pub/sub channel
    redis_client: aioredis.Redis | None = None
    pubsub = None
    try:
        redis_client = aioredis.from_url(_REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(job_channel(job_id))

        # Send initial status so the user sees something immediately
        await websocket.send_json(
            {
                "type": "status",
                "status": "pending",
                "detail": "Job queued, waiting for worker…",
            }
        )

        # Listen for messages until complete/error or WS disconnect
        timeout_seconds = 300  # 5 minutes max
        elapsed = 0
        poll_interval = 0.2

        while elapsed < timeout_seconds:
            if websocket.client_state != WebSocketState.CONNECTED:
                break

            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=poll_interval
            )
            if message and message["type"] == "message":
                data = message["data"]
                try:
                    event = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    continue

                await websocket.send_json(event)

                # Close after terminal events
                if event.get("type") in ("complete", "error"):
                    break
            else:
                elapsed += poll_interval
                await asyncio.sleep(0)

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected for job %s", job_id)
    except Exception:
        logger.exception("WebSocket error for job %s", job_id)
        try:
            await websocket.send_json(
                {"type": "error", "message": "Internal server error"}
            )
        except Exception:
            pass
    finally:
        if pubsub:
            await pubsub.unsubscribe(job_channel(job_id))
            await pubsub.close()
        if redis_client:
            await redis_client.aclose()
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()


async def publish_progress(
    redis_url: str,
    job_id: str,
    event: dict,
) -> None:
    """Publish a progress event from a Celery worker.

    This is called from the synchronous Celery task using asyncio.run().
    """
    import asyncio

    async def _publish():
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            await client.publish(job_channel(job_id), json.dumps(event))
        finally:
            await client.aclose()

    asyncio.run(_publish())


def publish_progress_sync(job_id: str, event: dict) -> None:
    """Synchronous wrapper — call this from Celery tasks."""
    import asyncio

    async def _inner():
        client = aioredis.from_url(_REDIS_URL, decode_responses=True)
        try:
            await client.publish(job_channel(job_id), json.dumps(event))
        finally:
            await client.aclose()

    try:
        asyncio.run(_inner())
    except Exception:
        logger.exception("Failed to publish progress for job %s", job_id)
