# CLAUDE.md — OpenSpeakers

## Project Overview

OpenSpeakers is a unified TTS and voice cloning application supporting multiple open-source
models (VibeVoice, Fish Speech S2, Qwen3 TTS, Kokoro, etc.) with hot-swap GPU management.

See `PLAN.md` for the full implementation plan and model details.

## Architecture

- **Frontend**: SvelteKit + TypeScript + Tailwind CSS (port 5173 dev)
- **Backend**: FastAPI + SQLAlchemy 2.0 + Alembic (port 8080)
- **Queue**: Celery + Redis (concurrency=1 for single-GPU serialization)
- **Database**: PostgreSQL (job history, voice profiles)
- **Models**: Hot-swapped on single GPU via `ModelManager` singleton

## Key Design: Model Hot-Swap

`backend/app/models/manager.py` — `ModelManager` is a singleton that:
1. Tracks `current_model_id` (which model is in GPU VRAM)
2. On `load_model(id)`: unloads current model + `torch.cuda.empty_cache()`, then loads new
3. All GPU access is serialized via `threading.Lock` (Celery worker runs concurrency=1)
4. Only the Celery worker loads models; the FastAPI backend never loads ML models

## Model Abstraction

All TTS models implement `TTSModelBase` (`backend/app/models/base.py`):
- `load(device)` / `unload()` — GPU lifecycle
- `generate(request: GenerateRequest) -> GenerateResult` — core TTS
- `clone_voice(audio_path, name) -> dict` — optional voice cloning

To add a new model:
1. Create `backend/app/models/<name>.py` implementing `TTSModelBase`
2. Register in `ModelManager._register_defaults()`
3. Add config entry to `configs/models.yaml`

## Development Commands

```bash
# Start everything (dev mode)
docker compose up

# Backend with hot reload only
docker compose up postgres redis backend

# Run Alembic migrations
docker compose exec backend alembic upgrade head

# Access backend shell
docker compose exec backend bash

# Run tests
docker compose exec backend pytest tests/ -v

# Frontend type check
cd frontend && npm run check
```

## Important File Locations

| Path | Purpose |
|------|---------|
| `backend/app/models/manager.py` | Model hot-swap singleton |
| `backend/app/models/base.py` | Abstract base class for all TTS models |
| `backend/app/models/vibevoice.py` | VibeVoice implementation |
| `backend/app/models/fish_speech.py` | Fish Speech S2 implementation |
| `backend/app/tasks/tts_tasks.py` | Celery tasks (generation, cloning) |
| `backend/app/db/models.py` | SQLAlchemy ORM models |
| `backend/alembic/versions/` | DB migration files |
| `configs/models.yaml` | Model registry configuration |
| `frontend/src/routes/tts/+page.svelte` | Main TTS generation page |
| `frontend/src/lib/api/tts.ts` | API client for TTS |
| `audio_output/` | Generated audio files (dev, mounted as volume) |

## Environment Variables (`.env`)

Key variables — see `.env.example` for full list:
- `GPU_DEVICE_ID` — which GPU to use (default: 0)
- `MODEL_CACHE_DIR` — where HuggingFace models are cached
- `AUDIO_OUTPUT_DIR` — where generated audio is stored
- `DATABASE_URL` — PostgreSQL connection string
- `CELERY_BROKER_URL` — Redis URL

## Service URLs (dev)

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8080/api |
| API Docs | http://localhost:8080/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

## Current Status (Phase 1)

- Backend scaffold: functional
- Model manager: implemented with VibeVoice + Fish Speech stubs
- API endpoints: TTS generate, job status, model list, voice profiles
- Celery worker: configured with single-GPU concurrency
- Frontend scaffold: TTS page, voice cloning page, comparison page, settings
- Docker Compose: full stack with GPU passthrough overlay
- Alembic migrations: initial schema

**Next steps**:
1. `docker compose build` — build images
2. Download VibeVoice model: `microsoft/VibeVoice-Realtime-0.5B`
3. Test end-to-end: POST /api/tts/generate → poll /api/tts/jobs/{id} → GET audio

## Adding New Models (Quick Reference)

```python
# backend/app/models/my_model.py
from app.models.base import TTSModelBase, GenerateRequest, GenerateResult

class MyModel(TTSModelBase):
    model_id = "my-model"
    model_name = "My TTS Model"
    description = "..."
    supports_voice_cloning = False

    def load(self, device: str = "cuda") -> None:
        self._model = ...  # load from HuggingFace
        self._loaded = True

    def unload(self) -> None:
        del self._model
        self._loaded = False

    def generate(self, request: GenerateRequest) -> GenerateResult:
        audio = self._model.tts(request.text)
        return GenerateResult(audio_bytes=audio, sample_rate=24000, duration_seconds=...)

# Then register in manager.py _register_defaults():
from app.models.my_model import MyModel
self._registry["my-model"] = MyModel
```
