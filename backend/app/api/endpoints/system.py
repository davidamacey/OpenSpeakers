"""System health and info endpoints."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter

from app.core.config import settings
from app.models.manager import ModelManager

router = APIRouter(tags=["system"])


def _get_nvidia_smi_stats(device_id: int) -> dict:
    """Get detailed GPU stats via nvidia-smi."""
    try:
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu,power.draw,power.limit,fan.speed,memory.used,memory.total",
                "--format=csv,noheader,nounits",
                f"--id={device_id}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            return {
                "utilization_pct": int(parts[0]),
                "temperature_c": int(parts[1]),
                "power_draw_w": float(parts[2]),
                "power_limit_w": float(parts[3]),
                "fan_speed_pct": int(parts[4]) if parts[4] != "[N/A]" else None,
                "memory_used_mb": int(parts[5]),
                "memory_total_mb": int(parts[6]),
            }
    except Exception:
        pass
    return {}


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.get("/api/system/info")
def system_info() -> dict:
    manager = ModelManager.get_instance()

    gpu_info: dict = {}
    try:
        import torch

        if torch.cuda.is_available():
            device_id = settings.GPU_DEVICE_ID
            gpu_info = {
                "available": True,
                "device_id": device_id,
                "device_name": torch.cuda.get_device_name(device_id),
                "vram_total_gb": round(
                    torch.cuda.get_device_properties(device_id).total_memory / 1e9, 1
                ),
                "vram_used_gb": round(torch.cuda.memory_allocated(device_id) / 1e9, 2),
                "vram_reserved_gb": round(
                    torch.cuda.memory_reserved(device_id) / 1e9, 2
                ),
            }
            gpu_info["nvidia_smi"] = _get_nvidia_smi_stats(device_id)
        else:
            gpu_info = {"available": False}
    except ImportError:
        gpu_info = {"available": False, "note": "torch not installed in API container"}

    audio_dir = Path(settings.AUDIO_OUTPUT_DIR)
    disk_usage: dict = {}
    if audio_dir.exists():
        total, used, free = shutil.disk_usage(audio_dir)
        disk_usage = {
            "total_gb": round(total / 1e9, 1),
            "used_gb": round(used / 1e9, 1),
            "free_gb": round(free / 1e9, 1),
        }

    return {
        "current_model": manager.current_model_id,
        "registered_models": manager.registered_ids,
        "gpu": gpu_info,
        "disk": disk_usage,
        "audio_output_dir": str(audio_dir),
        "model_cache_dir": settings.MODEL_CACHE_DIR,
    }
