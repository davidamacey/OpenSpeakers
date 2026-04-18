# Changelog

All notable changes to OpenSpeakers are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-04-18

### Fixed

- **Frontend unreachable**: `docker-compose.prod.yml` mapped the frontend to internal port 3000,
  but the nginx container listens on port 80. Fixed to `${FRONTEND_PORT:-5200}:80`.
- **Workers cannot connect to Redis/Celery**: All worker containers defaulted to
  `redis://localhost:6379` for the Celery broker and result backend. Fixed by adding
  explicit `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` env vars to all worker services
  in `docker-compose.prod.yml` and by updating `config.py` to build the URLs dynamically
  from `REDIS_HOST`/`REDIS_PORT` when not explicitly set.
- **Kokoro model requests hang**: The `tts.kokoro` queue was not declared in the Celery app
  configuration (`celery.py`), causing tasks routed to that queue to be silently ignored.
  Queue is now registered alongside the other model queues.
- **HuggingFace cache path undefined in secondary workers**: `worker-fish`, `worker-qwen3`,
  `worker-f5`, `worker-orpheus`, and `worker-dia` were missing `HF_HOME` and `HOME`
  environment variables, causing inconsistent cache directory behavior. Now explicitly set
  to `/root/.cache/huggingface` and `/root`.
- **VibeVoice 0.5B crash** (`'NoneType' object is not subscriptable`): Voice .pt files were
  at `/app/demo/voices/streaming_model/` inside the worker image, but the code looked under
  `/opt/vibevoice/demo/voices/streaming_model/`. `_resolve_voice()` returned `None` and the
  model crashed in `process_input_with_cached_prompt`. Fixed the directory constant.
- **Fish Speech fails on fresh install**: `launch_thread_safe_queue()` was called with a
  HuggingFace Hub repo ID as if it were a local path — fine when the model was pre-cached,
  but crashed on first-run installs. Now calls `snapshot_download()` first to materialize
  the model locally.
- **Fish Speech decoder size mismatch**: The project shipped `fishaudio/fish-speech-1.5`,
  but the installed `fish-speech` library (v2.0.0) expects the newer `fishaudio/s2-pro`
  architecture (different DAC dimensions, different decoder filename). Updated default
  `FISH_SPEECH_MODEL_PATH` to `fishaudio/s2-pro` and added a candidate-search for the
  decoder checkpoint filename (`codec.pth` vs. `firefly-gan-vq-fsq-8x1024-21hz-generator.pth`).
- **Qwen3 TTS blocked on first-run download**: `snapshot_download(..., local_files_only=True)`
  prevented the model from being fetched on a fresh install with an empty cache. Now uses
  `local_files_only=False` for both the CustomVoice and Base (cloning) model paths.
- **Orpheus 3B gated-model 401**: The worker containers did not receive `HF_TOKEN`, so the
  gated `canopylabs/orpheus-3b-0.1-ft` repo returned 401. All 7 worker services in
  `docker-compose.prod.yml` now forward `HF_TOKEN` and `HUGGING_FACE_HUB_TOKEN` from `.env`.

### Added

- **Hardened setup script** (`setup-openspeakers.sh`): network reachability check for
  github.com / hub.docker.com / huggingface.co, 3-retry download loop for every file,
  `docker compose config` validation before `up`, 120-second backend health poll,
  `OPENSPEAKERS_UNATTENDED=1` env var for CI / scripted use, `OPENSPEAKERS_BRANCH` override
  for testing pre-release branches.
- **`HF_TOKEN` env var** in `.env.example` with documentation pointing to the HuggingFace
  settings page and the Orpheus model license page.
- **`scripts/fix-model-permissions.sh`**: standalone helper that chowns `model_cache/` to
  UID 1000 (the container user) using Docker or sudo.

### Changed

- `/test-install/` and `/openspeakers/` added to `.gitignore` so ad-hoc install-test
  directories never get committed.
- Default `FISH_SPEECH_MODEL_PATH` in both `config.py` and `.env.example` is now
  `fishaudio/s2-pro` (was `fishaudio/fish-speech-1.5`).

## [0.1.0] - 2026-04-12

### Overview

Initial public release of OpenSpeakers — a unified TTS and voice cloning application
supporting 11 open-source models with GPU hot-swap, async job queuing, real-time
streaming, and a SvelteKit UI.

### Added

#### 11 TTS Models
- **Kokoro 82M** — Fastest model (~1s), 50+ preset voices, standby mode
- **VibeVoice 0.5B** — Real-time streaming TTS, 12 built-in voices, 10 languages
- **VibeVoice 1.5B** — High-quality long-form, multi-speaker dialogue, zero-shot cloning
- **Fish Audio S2-Pro** — Multilingual (80+ languages), emotion tags, voice cloning
- **Qwen3 TTS 1.7B** — Expressive multilingual with instruct mode and voice cloning
- **Orpheus 3B** — Emotional speech with laugh/sigh/gasp tags, vLLM backend
- **F5-TTS** — Fast flow-matching (15x realtime), MIT license, reference-audio cloning
- **Chatterbox** — Expressive TTS with exaggeration/CFG controls, voice cloning
- **CosyVoice 2.0** — Ultra-low latency (150ms), voice design via text description
- **Parler TTS Mini** — Generate any voice from a text description, no reference audio
- **Dia 1.6B** — Multi-speaker dialogue with [S1]/[S2] tags and nonverbal sounds

#### GPU Hot-Swap Architecture
- ModelManager singleton with threading.Lock for GPU serialization
- Automatic model unloading between tasks (gc.collect + torch.cuda.empty_cache)
- 60-second idle timer auto-unloads non-standby models
- Kokoro standby mode — stays loaded permanently for instant responses
- Ollama-style keep_alive TTL per model (-1 = indefinite, 0 = clear, N = seconds)

#### Worker Architecture
- 7 dedicated Celery worker containers with model-specific queues
- QUEUE_MAP routing — single source of truth for model-to-queue mapping
- Shared GPU base image (torch 2.10+cu128) for all secondary workers
- nvidia runtime on all containers for reliable GPU access
- Startup validation warns about unrouted or stale QUEUE_MAP entries

#### API Endpoints
- `POST /api/tts/generate` — Submit TTS job (async, returns job_id)
- `GET /api/tts/jobs/{id}` — Poll job status
- `GET /api/tts/jobs/{id}/audio` — Download generated audio
- `GET /api/tts/jobs` — List jobs with pagination, filtering, search
- `DELETE /api/tts/jobs/{id}` — Cancel pending/running job (revokes Celery task)
- `POST /api/tts/batch` — Submit up to 100 lines as a batch
- `GET /api/tts/batches/{id}` — Batch status with aggregate counts
- `GET /api/tts/batches/{id}/zip` — Download all completed audio as ZIP
- `POST /api/voices` — Upload reference audio for voice cloning
- `GET /api/voices` — List voice profiles
- `GET /api/voices/builtin/{model_id}` — List preset voices per model
- `PATCH /api/voices/{id}` — Update voice profile name/description/tags
- `DELETE /api/voices/{id}` — Delete voice profile and files
- `GET /api/models` — List all models with capabilities and status
- `POST /api/models/{id}/load` — Pre-warm model into GPU VRAM
- `DELETE /api/models/{id}/load` — Force-unload model
- `POST /v1/audio/speech` — OpenAI-compatible endpoint (tts-1 → Kokoro, tts-1-hd → Orpheus)
- `GET /health` — Docker health check
- `GET /api/system/info` — GPU stats, disk usage, registered models

#### WebSocket Endpoints
- `/ws/jobs/{id}` — Real-time job progress (queued, loading, generating, audio_chunk, complete)
- `/ws/gpu` — Live GPU stats stream (1s interval)

#### Frontend (SvelteKit 2 + Svelte 5)
- **TTS Page** — Model selector with help text, voice picker, speed/pitch/language controls
- **Dialogue Editor** — Structured multi-speaker turn editor for Dia and VibeVoice 1.5B
- **Batch Page** — Dynamic add/remove text entries, per-job progress, ZIP download
- **Compare Page** — Side-by-side generation across up to 4 models
- **Clone Page** — Upload reference audio, manage voice profiles
- **History Page** — Full job history with search, filter, pagination, audio playback
- **Models Page** — Model catalog with help text, capability badges, VRAM bars, filters
- **Settings Page** — Live GPU stats via WebSocket, storage paths, system info
- **About Page** — Model descriptions and HuggingFace links
- Dark mode default with theme toggle
- Mobile responsive sidebar
- Real-time streaming audio playback (Web Audio API) for VibeVoice 0.5B
- Per-model parameter panels with emotion tag quick-insert
- Keyboard shortcuts modal (press ?)
- Toast notification system

#### Infrastructure
- PostgreSQL for job history, voice profiles, batch tracking
- Redis for Celery broker and WebSocket pub/sub
- Alembic migrations (auto-run on backend startup)
- pynvml GPU stats in API container (no torch dependency)
- Path traversal guard on batch ZIP downloads
- Extension whitelist on voice profile uploads
- CORS configuration via environment variable
- Pre-commit hooks: ruff, bandit, shellcheck, conventional commits

#### Testing
- 18 fast API smoke tests
- Kokoro end-to-end generation test
- Full-matrix parametrized test for all 11 models (TEST_ALL_MODELS=1)

[0.1.0]: https://github.com/davidamacey/OpenSpeakers/releases/tag/v0.1.0
