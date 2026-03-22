from __future__ import annotations

import logging

from celery import Celery
from kombu import Queue

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "open_speakers",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.tts_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Keep results for 24 hours
    result_expires=86400,
    # Worker settings
    worker_prefetch_multiplier=1,  # Don't prefetch — one task at a time (GPU)
    task_acks_late=True,  # Ack after completion for reliability
    task_reject_on_worker_lost=True,
    # Queues
    task_queues=[
        Queue("tts"),
        Queue("tts.fish-speech"),
        Queue("tts.qwen3"),
    ],
    # Default routes (overridden at dispatch time for model-specific routing)
    task_routes={
        "app.tasks.tts_tasks.generate_tts": {"queue": "tts"},
        "app.tasks.tts_tasks.clone_voice": {"queue": "tts"},
    },
    task_queues_max_priority=10,
    task_default_queue="tts",
    task_default_priority=5,
)
