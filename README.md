# OpenSpeakers

```
  ___                   ____                 _
 / _ \ _ __   ___ _ __ / ___| _ __  ___  __ _| | _____ _ __ ___
| | | | '_ \ / _ \ '_ \\___ \| '_ \/ _ \/ _` | |/ / _ \ '__/ __|
| |_| | |_) |  __/ | | |___) | |_) |  __/ (_| |   <  __/ |  \__ \
 \___/| .__/ \___|_| |_|____/| .__/ \___|\__,_|_|\_\___|_|  |___/
      |_|                    |_|
```

A unified, self-hosted TTS and voice cloning application supporting 11 open-source models
with GPU hot-swap, async job queuing, real-time streaming, and a modern SvelteKit UI.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)

> Copyright © 2026 [Attevon LLC](https://attevon.com). All rights reserved.
> Released under the [GNU Affero General Public License v3.0](LICENSE).

---

## Screenshots

| | |
|:---:|:---:|
| ![Home](docs/screenshots/home.png) | ![TTS](docs/screenshots/tts.png) |
| **Home** — landing page with model gallery | **TTS** — main generation page with per-model parameters |
| ![Voice Clone](docs/screenshots/clone.png) | ![Compare](docs/screenshots/compare.png) |
| **Clone Voice** — drag-and-drop reference audio + voice library | **Compare** — run the same text through multiple models side-by-side |
| ![Batch](docs/screenshots/batch.png) | ![History](docs/screenshots/history.png) |
| **Batch** — submit up to 100 lines and download as a ZIP | **History** — searchable, filterable job history |
| ![Models](docs/screenshots/models.png) | ![Settings](docs/screenshots/settings.png) |
| **Models** — capability browser with VRAM estimates | **Settings** — live GPU stats, output format, OpenAI API config |

---

## Key Features

### Generation
- **11 working TTS models** — Kokoro 82M, VibeVoice 0.5B/1.5B, Fish Audio S2-Pro, Qwen3 TTS 1.7B, Orpheus 3B, Dia 1.6B, F5-TTS, Chatterbox, CosyVoice 2.0, Parler TTS Mini
- **GPU hot-swap** — only one model in VRAM at a time; auto-eviction with 60-second idle timer
- **Ollama-style keep_alive** — per-request `-1` (hold forever), `0` (evict now), or `N` seconds
- **Real-time audio streaming** — VibeVoice 0.5B streams PCM16 chunks via Redis pub/sub → WebSocket → Web Audio API
- **Output formats** — WAV, MP3, OGG (ffmpeg transcoding)

### Voice Cloning
- **Zero-shot cloning** — Fish Audio S2-Pro, VibeVoice 1.5B, and Qwen3 TTS clone from any 3–30 second reference clip
- **Voice profiles** — store reference audio and metadata; reuse across any generation
- **50+ built-in voices** — Kokoro's preset voice library
- **Emotion and style control** — Fish S2-Pro `[whisper]` / `[excited]` tags; Orpheus `<laugh>` / `<sigh>` / `<gasp>` tags
- **Dialogue mode** — Dia 1.6B `[S1]` / `[S2]` multi-speaker scripting with nonverbal sounds

### Job Management
- **Async job queue** — Celery + Redis; all generation is non-blocking with immediate `job_id` response
- **Job cancellation** — revoke pending or running jobs mid-flight via the API or UI
- **Batch generation** — submit up to 100 lines in a single request; download all audio as a ZIP
- **Full job history** — searchable, filterable by model / status, paginated

### API
- **OpenAI-compatible `/v1/audio/speech`** — drop-in replacement for `openai.audio.speech.create()`
- **WebSocket progress** — real-time `queued` → `loading` → `generating` → `audio_chunk` → `complete` events
- **Live GPU stats** — WebSocket stream of utilisation, temperature, and power draw
- **Swagger UI** — interactive API docs at `/docs`

### UI / UX
- **SvelteKit 2 + Svelte 5 runes** — reactive, type-safe frontend
- **WaveSurfer.js waveform** — visual audio player with keyboard seek
- **Dark mode default** — toggle persists to localStorage; FOUC prevention
- **Mobile responsive** — sidebar collapses to hamburger on narrow screens
- **Keyboard shortcuts** — press `?` for the help modal; `Ctrl+Enter` to submit; arrows to seek
- **Toast notifications** — non-blocking success/error/warning messages
- **Model browser** — capability table with VRAM estimates

---

## Supported Models

| Model | Container | Queue | VRAM | Cloning | Streaming | Status |
|-------|-----------|-------|------|---------|-----------|--------|
| **Kokoro 82M** | `worker-kokoro` | `tts.kokoro` | ~0.5 GB | — | — | ✅ Working (standby) |
| **VibeVoice 0.5B** | `worker` | `tts` | ~5 GB | — | PCM16 | ✅ Working |
| **VibeVoice 1.5B** | `worker` | `tts` | ~12 GB | Zero-shot | — | ✅ Working |
| **Fish Audio S2-Pro** | `worker-fish` | `tts.fish-speech` | ~22 GB | Zero-shot | Chunked | ✅ Working |
| **Qwen3 TTS 1.7B** | `worker-qwen3` | `tts.qwen3` | ~10 GB | Zero-shot | — | ✅ Working |
| **Orpheus 3B** | `worker-orpheus` | `tts.orpheus` | ~7 GB | — | — | ✅ Working |
| **Dia 1.6B** | `worker-dia` | `tts.dia` | ~10 GB | Via prompt | — | ✅ Working |
| **F5-TTS** | `worker-f5` | `tts.f5-tts` | ~3 GB | Zero-shot | — | ✅ Working |
| **Chatterbox** | `worker-f5` | `tts.f5-tts` | ~5 GB | Zero-shot | — | ✅ Working |
| **CosyVoice 2.0** | `worker-f5` | `tts.f5-tts` | ~5 GB | Zero-shot | — | ✅ Working |
| **Parler TTS Mini** | `worker-f5` | `tts.f5-tts` | ~3 GB | — | — | ✅ Working |

---

## Quick Start

### One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main/setup-openspeakers.sh | bash
```

The setup script handles everything on a fresh machine:
- ✅ Checks Docker, NVIDIA Container Toolkit, and GPU
- ✅ **Enables Docker to start on boot** (`systemctl enable docker`)
- ✅ Downloads compose files and generates `.env` with a secure random secret key
- ✅ Creates `model_cache` and `audio_output` directories with correct permissions for the container's UID 1000 user
- ✅ Pulls all images and starts all services

**Requirements:** Docker with Compose v2, NVIDIA GPU, [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

Once running:
- **UI:** http://localhost:5200
- **API:** http://localhost:8080
- **Docs:** http://localhost:8080/docs

Models download automatically on first use (~1–22 GB each depending on the model).

> **Permission errors after install?** Run `./scripts/fix-model-permissions.sh` — it fixes `model_cache` ownership without requiring sudo.

### Manual Install (from Docker Hub)

```bash
mkdir openspeakers && cd openspeakers
curl -fsSLO https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main/docker-compose.prod.yml
curl -fsSLO https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main/docker-compose.gpu.yml
curl -fsSLO https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main/.env.example
cp .env.example .env
# Fix model cache permissions for the appuser (UID 1000) container user
mkdir -p model_cache/huggingface model_cache/torch
docker run --rm -v "$(pwd)/model_cache:/mc" busybox chown -R 1000:1000 /mc
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d
```

### Development Setup (from source)

```bash
git clone https://github.com/davidamacey/OpenSpeakers.git
cd OpenSpeakers
cp .env.example .env
docker compose up -d --build
```

### Configuration

Edit `.env` to customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `GPU_DEVICE_ID` | `0` | Which CUDA GPU to use |
| `FRONTEND_PORT` | `5200` | UI port |
| `BACKEND_PORT` | `8080` | API port |
| `HF_TOKEN` | — | Required for gated models (Orpheus 3B) |
| `MODEL_CACHE_DIR` | `./model_cache` | Where model weights are stored |
| `AUDIO_OUTPUT_DIR` | `./audio_output` | Where generated audio is saved |

### First Use

1. Open **http://localhost:5200** — the TTS page loads automatically
2. Select a model (Kokoro is fastest for a first test), enter text, click **Generate**
3. Browse **Models** to see all 11 models with help text on speed, quality, and use cases
4. Try **Batch** to generate multiple lines at once
5. Try **Compare** to hear the same text across different models side-by-side
6. Use **Clone** to upload a reference audio clip and create a custom voice

---

## Management CLI

`openspeakers.sh` is a self-contained management script at the repo root:

```bash
./openspeakers.sh <command> [options]
```

| Command | Description |
|---------|-------------|
| `start [gpu\|dev\|offline\|build]` | Start all services (default: gpu mode) |
| `stop` | Stop all services |
| `restart [service]` | Restart all or one service |
| `status` | Show service health |
| `logs [service]` | Tail logs (all services or one) |
| `health` | Check API health endpoint |
| `workers status` | Show all worker container statuses |
| `workers logs [name]` | Tail a specific worker's logs |
| `workers restart [name]` | Restart a worker container |
| `workers rebuild [name]` | Rebuild and restart a worker |
| `db migrate` | Apply all pending Alembic migrations |
| `db revision "message"` | Generate a new Alembic migration |
| `db reset` | Drop and recreate the database |
| `db backup` | Dump PostgreSQL to a timestamped file |
| `db restore <file>` | Restore a PostgreSQL dump |
| `build [service]` | Build Docker image(s) |
| `shell [service]` | Open a bash shell in a container |
| `test [target]` | Run backend or frontend tests |
| `gpu` | Show live GPU stats (nvidia-smi) |
| `clean` | Remove stopped containers and dangling images |
| `purge` | Remove all containers, volumes, and images |

---

## API Reference

### TTS Jobs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/tts/generate` | Submit a generation job; returns `{job_id}` |
| `GET` | `/api/tts/jobs/{id}` | Get job status and metadata |
| `GET` | `/api/tts/jobs/{id}/audio` | Stream the generated audio file |
| `GET` | `/api/tts/jobs` | List jobs (`page`, `page_size`, `status`, `model_id`, `search`) |
| `DELETE` | `/api/tts/jobs/{id}` | Cancel a pending or running job |
| `POST` | `/api/tts/batch` | Submit up to 100 lines; returns `{batch_id, job_ids[]}` |
| `GET` | `/api/tts/batches/{id}` | Aggregate batch status |
| `GET` | `/api/tts/batches/{id}/zip` | Stream ZIP of all completed audio files |

#### Generate request body

```json
{
  "model_id": "kokoro",
  "text": "Hello world",
  "voice": "af_bella",
  "speed": 1.0,
  "pitch": 0,
  "format": "wav",
  "keep_alive": 60
}
```

`keep_alive` controls how long the model stays in VRAM after this request:
- `-1` — keep loaded indefinitely
- `0` — unload immediately after generation
- `N` (positive integer) — unload after N seconds of inactivity (default: 60)

### Voice Profiles

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/voices/` | List all voice profiles |
| `POST` | `/api/voices/` | Create a new profile (multipart: `name`, `model_id`, `audio`) |
| `GET` | `/api/voices/{id}` | Get a single voice profile |
| `PATCH` | `/api/voices/{id}` | Update name, description, or tags |
| `GET` | `/api/voices/{id}/audio` | Stream the reference audio file |
| `DELETE` | `/api/voices/{id}` | Delete profile and reference audio |
| `GET` | `/api/voices/builtin/{model_id}` | List built-in preset voices for a model |

### Models

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/models/` | List all models with capabilities |
| `GET` | `/api/models/{id}` | Get single model info |
| `POST` | `/api/models/{id}/load` | Pre-warm a model (optional `keep_alive`) |
| `DELETE` | `/api/models/{id}/load` | Force-unload a model from VRAM |

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/api/system/info` | GPU + disk + model registry snapshot |

### OpenAI Compatibility

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/audio/speech` | OpenAI-compatible TTS |
| `GET` | `/v1/models` | OpenAI-format model list |

Model mapping: `tts-1` → Kokoro 82M, `tts-1-hd` → Orpheus 3B

### WebSocket

| Path | Events |
|------|--------|
| `/ws/jobs/{id}` | `queued`, `loading`, `generating`, `audio_chunk`, `complete`, `failed` |
| `/ws/gpu` | GPU stats every 1 second |

---

## OpenAI Compatibility

OpenSpeakers exposes a `/v1/audio/speech` endpoint compatible with the OpenAI Python SDK
and any application that uses the OpenAI TTS API.

### Python (openai SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed",
)

# Uses Kokoro 82M (tts-1 maps to the fastest model)
audio = client.audio.speech.create(
    model="tts-1",
    voice="alloy",
    input="Hello from OpenSpeakers!",
)
audio.stream_to_file("output.wav")

# Uses Orpheus 3B (tts-1-hd maps to the highest quality model)
audio = client.audio.speech.create(
    model="tts-1-hd",
    voice="zoe",
    input="A higher quality voice.",
)
audio.stream_to_file("output_hd.wav")
```

### curl

```bash
curl http://localhost:8080/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model": "tts-1", "voice": "alloy", "input": "Hello world"}' \
  --output speech.wav
```

---

## keep_alive Usage

The `keep_alive` parameter on `/api/tts/generate` and `/api/models/{id}/load` controls
VRAM retention, similar to Ollama's model keep-alive:

```bash
# Keep the model loaded for 5 minutes after this request
curl -X POST http://localhost:8080/api/tts/generate \
  -H "Content-Type: application/json" \
  -d '{"model_id": "fish-speech", "text": "Hello", "keep_alive": 300}'

# Pre-warm a model and keep it loaded indefinitely
curl -X POST http://localhost:8080/api/models/kokoro/load \
  -H "Content-Type: application/json" \
  -d '{"keep_alive": -1}'

# Force-unload a model immediately
curl -X DELETE http://localhost:8080/api/models/orpheus/load
```

---

## Worker Architecture

Each model group runs in its own container on a dedicated Celery queue. This isolates GPU
memory, Python dependencies, and container build complexity.

| Container | Queue | Models | Dockerfile |
|-----------|-------|--------|------------|
| `worker-kokoro` | `tts.kokoro` | Kokoro 82M (standby — always loaded) | `Dockerfile.worker` |
| `worker` | `tts` | VibeVoice 0.5B (streaming), VibeVoice 1.5B | `Dockerfile.worker` |
| `worker-fish` | `tts.fish-speech` | Fish Audio S2-Pro | `Dockerfile.worker-fish` |
| `worker-qwen3` | `tts.qwen3` | Qwen3 TTS 1.7B | `Dockerfile.worker-qwen3` |
| `worker-orpheus` | `tts.orpheus` | Orpheus 3B | `Dockerfile.worker-orpheus` |
| `worker-dia` | `tts.dia` | Dia 1.6B | `Dockerfile.worker-dia` |
| `worker-f5` | `tts.f5-tts` | F5-TTS, Chatterbox, CosyVoice 2.0, Parler TTS Mini | `Dockerfile.worker-f5` |

The FastAPI backend **never touches the GPU**. Only Celery workers load ML models. Queue
routing is the single source of truth in `QUEUE_MAP` in `backend/app/api/endpoints/tts.py`.

All secondary workers inherit from `backend/Dockerfile.base-gpu` which provides:
- PyTorch 2.10.0+cu128 and torchaudio
- NVIDIA env vars (`NVIDIA_VISIBLE_DEVICES=all`, `NVIDIA_DRIVER_CAPABILITIES=compute,utility`)
- Common audio/ML packages: soundfile, numpy, scipy, librosa, accelerate

---

## Frontend Pages

| Page | Route | Description |
|------|-------|-------------|
| TTS | `/tts` | Main text-to-speech generation with streaming audio |
| Clone | `/clone` | Upload reference audio, manage voice profiles |
| Compare | `/compare` | Side-by-side multi-model comparison |
| Batch | `/batch` | Bulk generation from pasted text or `.txt` file |
| History | `/history` | Full job history with search and filter |
| Models | `/models` | Model browser with capability and VRAM reference |
| Settings | `/settings` | Output format, live GPU stats, storage paths |
| About | `/about` | Model descriptions and project links |

---

## Project Structure

```
open_speakers/
├── backend/
│   ├── Dockerfile.base-gpu          # Shared GPU base (PyTorch 2.10+cu128)
│   ├── Dockerfile.worker            # Main worker (Kokoro + VibeVoice)
│   ├── Dockerfile.worker-fish       # Fish Speech worker
│   ├── Dockerfile.worker-qwen3      # Qwen3 TTS worker
│   ├── Dockerfile.worker-orpheus    # Orpheus 3B worker (vLLM)
│   ├── Dockerfile.worker-dia        # Dia 1.6B worker
│   ├── Dockerfile.worker-f5         # F5-TTS / Chatterbox / CosyVoice worker
│   └── app/
│       ├── api/endpoints/           # REST API routes + OpenAI compat
│       ├── models/                  # TTS model implementations + ModelManager
│       ├── tasks/                   # Celery tasks (generation, streaming)
│       ├── db/                      # SQLAlchemy ORM models + Alembic
│       └── schemas/                 # Pydantic v2 schemas
├── frontend/src/
│   ├── routes/                      # SvelteKit pages: tts, clone, compare, batch, history, models, settings
│   ├── components/                  # AudioPlayer, ModelParams, ToastContainer, WaveformPreview, etc.
│   └── lib/                         # API clients, Svelte stores (toasts, theme)
├── configs/
│   └── models.yaml                  # Model registry — enable/disable models here
├── docs/
│   ├── PLAN.md                      # Feature roadmap and implementation status
│   └── MARKET_RESEARCH.md           # Competitor analysis
├── scripts/
│   ├── test_all_models.py           # Smoke-test all deployed models sequentially
│   ├── download-models.sh           # Download all model weights from HuggingFace
│   └── package-offline.sh           # Air-gapped install packaging
├── openspeakers.sh                  # Management CLI
├── docker-compose.yml               # Base service definitions
├── docker-compose.override.yml      # Dev build targets (auto-loaded)
├── docker-compose.gpu.yml           # NVIDIA GPU passthrough overlay
└── docker-compose.offline.yml       # Air-gapped / offline deployment
```

---

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `GPU_DEVICE_ID` | `0` | CUDA device index for all workers |
| `MODEL_CACHE_DIR` | `./model_cache` | HuggingFace model cache root (volume-mounted) |
| `AUDIO_OUTPUT_DIR` | `./audio_output` | Generated audio file storage |
| `POSTGRES_PASSWORD` | `openspeakers` | PostgreSQL password |
| `HF_TOKEN` | — | HuggingFace token (required for gated models: Orpheus 3B) |
| `BACKEND_PORT` | `8080` | Exposed backend API port |
| `FRONTEND_PORT` | `5200` | Exposed frontend port |
| `DATABASE_URL` | auto | Full PostgreSQL connection string (overrides individual vars) |
| `CELERY_BROKER_URL` | auto | Redis broker URL (overrides default) |

---

## Development

```bash
# Start all services (COMPOSE_FILE in .env selects gpu+override automatically)
docker compose up -d

# Or use the management CLI one-liners:
./openspeakers.sh start          # start with GPU
./openspeakers.sh start dev      # start core services only (no GPU workers)
./openspeakers.sh start build    # build images then start (first run)

# Rebuild one worker after Dockerfile changes
docker compose up -d --build worker-orpheus

# Tail worker logs
docker compose logs -f worker-dia

# Open a shell inside a container
docker compose exec backend bash

# Run backend tests
docker compose exec backend pytest tests/ -v

# Frontend type check (rollup native binding requires the container)
docker compose exec frontend npm run check

# Generate a new migration after ORM changes (migrations apply on next restart)
docker compose exec backend alembic revision --autogenerate -m "description"

# Smoke-test all deployed models sequentially
python3 scripts/test_all_models.py
```

### Service URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5200 |
| Backend API | http://localhost:8080/api |
| Swagger UI | http://localhost:8080/docs |
| ReDoc | http://localhost:8080/redoc |
| PostgreSQL | localhost:5432 (127.0.0.1 only) |
| Redis | localhost:6379 (127.0.0.1 only) |

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | SvelteKit 2, Svelte 5 runes, TypeScript, Tailwind CSS, WaveSurfer.js |
| Backend | FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 |
| Queue | Celery 5 + Redis (concurrency=1 per worker for GPU serialisation) |
| Database | PostgreSQL |
| GPU | NVIDIA CUDA 12.8, PyTorch 2.10+cu128 |

---

## Offline / Air-Gapped Installation

To install OpenSpeakers on a machine without internet access:

```bash
# ── On the SOURCE machine (with internet) ───────────────────────────────────

# 1. Download all model weights
./scripts/download-models.sh

# 2. Build images and bundle everything into a transferable package
./scripts/package-offline.sh

# 3. Transfer to the target machine
rsync -avz --progress dist/openspeakers-offline-YYYYMMDD/ user@target:/opt/openspeakers/

# ── On the TARGET machine (no internet required) ─────────────────────────────

cd /opt/openspeakers
./install.sh        # loads images, creates .env, runs docker compose up -d
```

`install.sh` will:
1. Check Docker + NVIDIA runtime prerequisites
2. Load all Docker images from `images/*.tar.gz`
3. Create `.env` from the example template
4. Start all services with `docker compose up -d`
5. Wait for backend readiness (migrations run automatically on startup)

---

## Model Downloads

To download individual models or refresh the local cache:

```bash
# Download all 11 models (~120 GB total)
./scripts/download-models.sh

# Download specific models
./scripts/download-models.sh --models kokoro,f5-tts,chatterbox

# Download to a custom cache directory
./scripts/download-models.sh --cache-dir /mnt/nas/model_cache

# For gated models (Orpheus 3B requires HF account acceptance)
HF_TOKEN=your_token ./scripts/download-models.sh --models orpheus-3b
```

Available model IDs: `kokoro`, `vibevoice`, `vibevoice-1.5b`, `fish-speech-s2`, `qwen3-tts`,
`f5-tts`, `f5-tts-vocos`, `chatterbox`, `cosyvoice-2`, `parler-tts`, `orpheus-3b`, `dia-1b`

---

## Contributing

1. Fork the repository and create a feature branch
2. Follow the existing code style: ruff for Python, Prettier + eslint for TypeScript
3. Add a model: see the "Adding a New Model" section in `CLAUDE.md` for the step-by-step guide
4. Run pre-commit hooks before pushing: `pre-commit run --all-files`
5. Use conventional commit messages: `feat(models): add Parler TTS support`
6. Open a pull request against `main`

See `CLAUDE.md` for full developer architecture notes and `docs/PLAN.md` for the feature
roadmap and completion status.
