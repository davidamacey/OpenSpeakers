# OpenSpeakers

Unified TTS and voice cloning application supporting multiple open-source models
(VibeVoice, Fish Speech S2, Qwen3 TTS, Kokoro) with single-GPU hot-swap management.

## Features

- **Multiple TTS models** — switch between models via dropdown; only one is in VRAM at a time
- **Voice cloning** — upload reference audio to clone any voice
- **Model comparison** — generate the same text with multiple models side-by-side
- **Job history** — all generations stored with audio playback
- **Single GPU support** — works with 8 GB VRAM; optimized for 48 GB (A6000)

## Quick Start

```bash
# Copy environment file and edit as needed
cp .env.example .env

# Start all services (GPU required for model inference)
docker compose up

# Open frontend
open http://localhost:5173
```

## Supported Models

| Model | VRAM | Voice Cloning | Languages |
|-------|------|---------------|-----------|
| VibeVoice 0.5B | ~4 GB | Yes | 12+ |
| Fish Speech S2 | ~4 GB | Yes | 8 |
| Qwen3 TTS | ~8 GB | Limited | 50+ |
| Kokoro 82M | <1 GB | No | 10+ |

## Development

See `PLAN.md` for full architecture and implementation roadmap.
See `CLAUDE.md` for developer context and quick reference.

```bash
# Dev mode with hot reload
docker compose up

# Backend API docs
open http://localhost:8080/docs
```

## Project Structure

```
open_speakers/
├── backend/                   # FastAPI + Celery
│   ├── app/
│   │   ├── api/endpoints/     # REST API routes
│   │   ├── core/              # Config, Celery, DB
│   │   ├── db/                # SQLAlchemy models
│   │   ├── models/            # TTS model abstraction + implementations
│   │   ├── schemas/           # Pydantic schemas
│   │   └── tasks/             # Celery tasks
│   └── alembic/               # DB migrations
├── frontend/                  # SvelteKit app
│   └── src/
│       ├── routes/            # Pages: /tts, /clone, /compare, /settings
│       ├── components/        # Reusable UI components
│       └── lib/               # API clients, stores
├── configs/                   # Model configs, presets
├── docker-compose.yml         # Base services
├── docker-compose.override.yml # Dev overrides (auto-loaded)
├── docker-compose.gpu.yml     # GPU passthrough overlay
└── PLAN.md                    # Full implementation plan
```
