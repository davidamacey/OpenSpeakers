"""Model listing and status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.manager import ModelManager
from app.schemas.models import ModelInfo

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelInfo])
def list_models() -> list[ModelInfo]:
    """List all registered TTS models and their current status."""
    manager = ModelManager.get_instance()
    return [ModelInfo(**m) for m in manager.list_models()]


@router.get("/{model_id}", response_model=ModelInfo)
def get_model(model_id: str) -> ModelInfo:
    """Get info and status for a specific model."""
    manager = ModelManager.get_instance()
    if model_id not in manager.registered_ids:
        raise HTTPException(status_code=404, detail=f"Model {model_id!r} not found")
    return ModelInfo(**manager.get_status(model_id))
