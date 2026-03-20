# OpenSpeakers — Implementation Plan

## Overview

OpenSpeakers is a unified TTS (text-to-speech) and voice cloning application that runs
multiple open-source models on a single GPU with hot-swap capability. It follows the same
architecture as OpenTranscribe (Svelte frontend + FastAPI backend + Celery + Redis + PostgreSQL).

---

## Architecture

### Core Design Principles

1. **Single GPU, multiple models** — only one TTS model is loaded in GPU VRAM at a time.
   Hot-swapping means the current model is unloaded (and CUDA cache cleared) before loading
   the next. On an A6000 (48 GB) multiple lighter models could coexist, but we default to
   one-at-a-time for broadest hardware support (8–12 GB typical GPU).

2. **Model abstraction layer** — all TTS models implement `TTSModelBase`. Adding a new model
   is a matter of writing one class and registering it.

3. **Async job queue** — generation is dispatched to a Celery worker so the API returns
   immediately with a `job_id`. The frontend polls or connects via WebSocket for progress.

4. **Voice profiles** — cloned voices are stored as embeddings/reference audio and can be
   reused across generation requests.

### Services

```
┌─────────────────┐       ┌──────────────────┐
│   SvelteKit UI  │──────▶│  FastAPI Backend  │
│   (port 5173)   │◀──────│   (port 8080)     │
└─────────────────┘       └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │  Redis (broker)   │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │  Celery Worker    │
                          │  (concurrency=1)  │
                          │  Model Manager    │
                          └────────┬─────────┘
                                   │
                     ┌─────────────┼──────────────┐
                     │             │              │
              ┌──────▼───┐  ┌──────▼───┐  ┌──────▼───┐
              │VibeVoice │  │Fish Speech│  │ Qwen3 TTS│
              │  (loaded)│  │ (unloaded)│  │ (unloaded)│
              └──────────┘  └──────────┘  └──────────┘
```

### Model Hot-Swap Flow

```
Request: generate with fish-speech-s2
  │
  ├─ ModelManager.load_model("fish-speech-s2")
  │     ├─ current_model_id == "vibevoice"?  → unload + torch.cuda.empty_cache()
  │     └─ load FishSpeechModel to GPU
  │
  └─ model.generate(text, voice_config)
        └─ returns audio bytes
```

---

## Database Schema

### `tts_jobs`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| model_id | VARCHAR | Which model was used |
| text | TEXT | Input text |
| voice_profile_id | UUID FK | Voice profile used (nullable) |
| parameters | JSONB | Speed, pitch, language, etc. |
| status | ENUM | pending/running/complete/failed |
| error_message | TEXT | Error if failed |
| output_path | VARCHAR | Path to generated audio file |
| duration_seconds | FLOAT | Duration of generated audio |
| processing_time_ms | INT | Time taken to generate |
| created_at | TIMESTAMP | When job was created |
| completed_at | TIMESTAMP | When job finished |

### `voice_profiles`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR | Display name |
| model_id | VARCHAR | Which model this voice is for |
| reference_audio_path | VARCHAR | Path to reference audio |
| embedding_path | VARCHAR | Path to voice embedding (model-specific) |
| metadata | JSONB | Model-specific metadata |
| created_at | TIMESTAMP | Creation time |

### `model_configs`
| Column | Type | Description |
|--------|------|-------------|
| model_id | VARCHAR PK | Model identifier |
| enabled | BOOLEAN | Whether model is available |
| hf_repo | VARCHAR | HuggingFace repo ID |
| custom_config | JSONB | Override config |

---

## API Endpoints

### TTS
- `POST /api/tts/generate` — Submit TTS job → returns `{job_id}`
- `GET /api/tts/jobs/{job_id}` — Poll job status
- `GET /api/tts/jobs/{job_id}/audio` — Download generated audio
- `GET /api/tts/jobs` — List recent jobs (paginated)

### Models
- `GET /api/models` — List all registered models with status
- `GET /api/models/{model_id}` — Get model details
- `GET /api/models/{model_id}/status` — Loaded/unloaded/loading status

### Voices
- `GET /api/voices` — List saved voice profiles
- `POST /api/voices` — Create voice profile (upload reference audio)
- `DELETE /api/voices/{voice_id}` — Delete voice profile

### System
- `GET /health` — Health check
- `GET /api/system/info` — GPU info, model cache stats

---

## Frontend Pages

### 1. TTS Page (`/tts`)
- Model dropdown with status indicators (loaded/available)
- Text area (multi-line input)
- Voice selector (built-in voices + saved cloned voices)
- Parameter controls: speed (0.5–2.0), pitch (-12 to +12), language
- "Generate" button with loading state
- Audio player with waveform visualization
- Download button
- Job history panel (last 10 jobs)

### 2. Voice Cloning Page (`/clone`)
- Reference audio upload (WAV/MP3/FLAC, max 30 sec)
- Model selector (only models that support cloning)
- Voice name input
- Preview generation with cloned voice
- Saved voices gallery

### 3. Comparison Page (`/compare`)
- Text input (shared)
- Multi-model selector (pick 2–4 models)
- "Generate All" button
- Side-by-side audio players per model
- Quality rating (thumbs up/down for each)
- Export comparison as ZIP

### 4. Settings Page (`/settings`)
- GPU Configuration: device ID, VRAM limit
- Model Management: download/delete models, show VRAM usage
- Output: default format (WAV/MP3/OGG), sample rate
- Default parameters: speed, pitch, language

---

## Implementation Phases

### Phase 1 — Foundation (Current)
**Goal**: Two models working end-to-end with hot-swap.

- [x] Project scaffold: backend + frontend + Docker Compose
- [x] Model abstraction layer (`TTSModelBase`)
- [x] Model manager (hot-swap, singleton)
- [x] VibeVoice implementation (microsoft/VibeVoice-Realtime-0.5B)
- [x] Fish Speech S2 stub (fishaudio/fish-speech-1.5)
- [x] Celery worker with single-GPU concurrency
- [x] FastAPI endpoints: generate, job status, model list
- [x] PostgreSQL schema + Alembic migrations
- [x] SvelteKit frontend: TTS page + audio player
- [ ] Docker build and smoke test
- [ ] Model download verification

### Phase 2 — More Models
**Goal**: Qwen3 TTS and additional models.

- [ ] Qwen3 TTS implementation (Qwen/Qwen3-TTS)
- [ ] Kokoro TTS implementation (hexgrad/Kokoro-82M)
- [ ] StyleTTS2 implementation
- [ ] Model config YAML for easy model registration
- [ ] Model download management UI
- [ ] VRAM usage tracking per model

### Phase 3 — Voice Cloning
**Goal**: Full voice cloning UI and storage.

- [ ] Fish Speech S2 voice cloning (full implementation)
- [ ] VibeVoice voice cloning (reference speaker support)
- [ ] Voice Cloning page
- [ ] Voice profile persistence (PostgreSQL + file storage)
- [ ] Comparison page with multi-model side-by-side
- [ ] Voice quality rating system

### Phase 4 — Polish
**Goal**: Production-ready with presets and streaming.

- [ ] Streaming TTS output (chunked audio as it generates)
- [ ] WebSocket progress for long generations
- [ ] Preset system (save parameter combinations)
- [ ] Batch generation (multiple texts at once)
- [ ] Export comparison as ZIP
- [ ] API key authentication (optional, for multi-user)
- [ ] MinIO for audio file storage (instead of local disk)
- [ ] Flower monitoring dashboard
- [ ] Docker Hub publish: `davidamacey/OpenSpeakers`

---

## Model Details

### VibeVoice (Phase 1)
- **Repo**: `microsoft/VibeVoice-Realtime-0.5B`
- **Type**: End-to-end speech LM with diffusion TTS head
- **VRAM**: ~4–6 GB
- **Languages**: EN, DE, FR, ES, IT, PT, NL, PL, JP, KR, ZH
- **Voice cloning**: Yes (reference speaker embedding via .pt voice files)
- **Streaming**: Yes
- **Notes**: David has a forked repo at `/mnt/nvm/repos/VibeVoice`

### Fish Speech S2 (Phase 1 stub → Phase 3 full)
- **Repo**: `fishaudio/fish-speech-1.5`
- **Type**: VQGAN + LLM + HiFiGAN vocoder
- **VRAM**: ~4–6 GB
- **Languages**: EN, ZH, JP, KR, FR, DE, AR, ES
- **Voice cloning**: Yes (3–10 second reference clips)
- **Streaming**: Yes (chunked)

### Qwen3 TTS (Phase 2)
- **Repo**: `Qwen/Qwen3-TTS` (or similar)
- **Type**: LLM-based TTS
- **VRAM**: ~8–16 GB (depends on model size)
- **Languages**: 50+
- **Voice cloning**: Limited (via prompting)

### Kokoro (Phase 2)
- **Repo**: `hexgrad/Kokoro-82M`
- **Type**: StyleTTS2-derived, very small
- **VRAM**: < 1 GB
- **Languages**: EN, FR, ES, JA, ZH, KO, HI, PT, IT, ...
- **Voice cloning**: No (uses preset voices)
- **Notes**: Fast inference, good for testing hot-swap

---

## Development Workflow

```bash
# Start all services (dev mode with hot reload)
docker compose up

# Backend only
docker compose up backend redis postgres

# Worker only
docker compose up worker

# Frontend dev server
cd frontend && npm run dev

# Run migrations
docker compose exec backend alembic upgrade head

# Shell into worker
docker compose exec worker bash
```

## Port Map (development)
| Service | Port |
|---------|------|
| Frontend (Vite) | 5173 |
| Backend (FastAPI) | 8080 |
| PostgreSQL | 5432 |
| Redis | 6379 |
