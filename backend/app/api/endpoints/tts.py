"""TTS generation endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.models import JobStatus, TTSJob
from app.schemas.tts import (
    GenerateRequest,
    GenerateResponse,
    JobListResponse,
    JobResponse,
)
from app.tasks.tts_tasks import generate_tts

router = APIRouter(prefix="/tts", tags=["tts"])

# Models that run on dedicated worker queues instead of the default "tts" queue
QUEUE_MAP: dict[str, str] = {
    "fish-speech-s2": "tts.fish-speech",
    "qwen3-tts": "tts.qwen3",
}


@router.post("/generate", response_model=GenerateResponse, status_code=202)
def create_tts_job(
    request: GenerateRequest, db: Session = Depends(get_db)
) -> GenerateResponse:
    """Submit a TTS generation request.

    Returns immediately with a job_id. Poll /tts/jobs/{job_id} for status.
    """
    # Create job record
    job = TTSJob(
        model_id=request.model_id,
        text=request.text,
        voice_id=request.voice_id,
        voice_profile_id=uuid.UUID(request.voice_id)
        if _is_uuid(request.voice_id)
        else None,
        parameters={
            "speed": request.speed,
            "pitch": request.pitch,
            "language": request.language,
            "extra": request.extra,
        },
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Dispatch to Celery worker (model-specific queue routing)
    queue = QUEUE_MAP.get(request.model_id, "tts")
    generate_tts.apply_async(args=[str(job.id)], queue=queue)

    return GenerateResponse(job_id=job.id, status=JobStatus.PENDING)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobResponse:
    """Get the status and result of a TTS job."""
    job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@router.get("/jobs/{job_id}/audio")
def get_job_audio(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Download the generated audio file for a completed job."""
    job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETE:
        raise HTTPException(
            status_code=409, detail=f"Job is {job.status.value}, not complete"
        )
    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        path=job.output_path,
        media_type="audio/wav",
        filename=f"tts_{job_id}.wav",
    )


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    model_id: str | None = Query(None),
    status: JobStatus | None = Query(None),
    db: Session = Depends(get_db),
) -> JobListResponse:
    """List recent TTS jobs, newest first."""
    q = db.query(TTSJob)
    if model_id:
        q = q.filter(TTSJob.model_id == model_id)
    if status:
        q = q.filter(TTSJob.status == status)

    total = q.count()
    jobs = (
        q.order_by(TTSJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


def _is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
