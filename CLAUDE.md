# CLAUDE.md — OpenSpeakers

## Project Overview

OpenSpeakers is a unified TTS and voice cloning application supporting 11 open-source
models with GPU hot-swap, async job queuing, real-time streaming, and a SvelteKit UI.

See `docs/PLAN.md` for the full implementation plan and `docs/MARKET_RESEARCH.md` for
competitor analysis.

## Architecture

- **Frontend**: SvelteKit 2 + Svelte 5 runes + TypeScript + Tailwind CSS (port 5200)
- **Backend**: FastAPI + SQLAlchemy 2.0 + Alembic (port 8080)
- **Queue**: Celery + Redis (concurrency=1 per worker for GPU serialization)
- **Database**: PostgreSQL (job history, voice profiles, batch tracking)
- **Models**: Hot-swapped on GPU via `ModelManager` singleton; Kokoro stays in standby

## Key Design: Model Hot-Swap

`backend/app/models/manager.py` — `ModelManager` is a singleton that:
1. Tracks `current_model_id` (which model is in GPU VRAM)
2. On `load_model(id)`: unloads current + `torch.cuda.empty_cache()`, then loads new
3. GPU access serialized via `threading.Lock` (Celery worker concurrency=1)
4. Idle timer (60 s): auto-unloads non-standby models between tasks
5. `standby: true` models (Kokoro) stay loaded permanently
6. Only Celery workers load ML models; the FastAPI backend never touches the GPU

## Worker Architecture

Each model group runs in its own container on a dedicated Celery queue:

| Container | Queue | Models | Dockerfile |
|-----------|-------|--------|------------|
| `worker-kokoro` | `tts.kokoro` | Kokoro 82M (standby — always loaded) | `Dockerfile.worker` |
| `worker` | `tts` | VibeVoice 0.5B, VibeVoice 1.5B | `Dockerfile.worker` |
| `worker-fish` | `tts.fish-speech` | Fish Audio S2-Pro | `Dockerfile.worker-fish` |
| `worker-qwen3` | `tts.qwen3` | Qwen3 TTS | `Dockerfile.worker-qwen3` |
| `worker-orpheus` | `tts.orpheus` | Orpheus 3B | `Dockerfile.worker-orpheus` |
| `worker-dia` | `tts.dia` | Dia 1.6B | `Dockerfile.worker-dia` |
| `worker-f5` | `tts.f5-tts` | F5-TTS, Chatterbox, CosyVoice 2.0, Parler TTS Mini | `Dockerfile.worker-f5` |
| `worker-asr` | `tts.asr` | faster-whisper reference transcription | `Dockerfile.worker-asr` |

Queue routing is the single source of truth in `QUEUE_MAP` in
`backend/app/api/endpoints/tts.py`.

`worker-asr` is CPU-only by default (`WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`,
`WHISPER_MODEL=small`). A commented override block in `docker-compose.gpu.yml` opts it
into GPU mode. The task `asr.transcribe_reference` is dispatched from the voices POST
handler whenever a profile is created without a manual transcript.

All secondary workers inherit from `backend/Dockerfile.base-gpu` which provides:
- PyTorch 2.10.0+cu128 and torchaudio
- NVIDIA env vars baked in (`NVIDIA_VISIBLE_DEVICES=all`)
- Common audio/ML packages (soundfile, numpy, scipy, librosa, accelerate)

Note: flash-attn is NOT in the base image — it requires nvcc at build time which is absent
from python:3.12-slim. The main worker uses a separate base with flash-attn pre-built.

## Model Abstraction

All TTS models implement `TTSModelBase` (`backend/app/models/base.py`):

```python
class TTSModelBase:
    model_id: str
    model_name: str
    description: str
    supports_voice_cloning: bool = False
    supports_streaming: bool = False
    supports_speed: bool = False    # show speed slider in UI
    supports_pitch: bool = False    # show pitch slider in UI
    vram_gb_estimate: float = 0.0

    def load(self, device: str = "cuda") -> None: ...
    def unload(self) -> None: ...
    def generate(self, request: GenerateRequest) -> GenerateResult: ...
    def stream_generate(self, request: GenerateRequest) -> Iterator[bytes]: ...
    def clone_voice(self, audio_path: str, name: str) -> dict: ...
```

## Adding a New Model

1. Create `backend/app/models/<name>.py` implementing `TTSModelBase`
2. Register in `ModelManager._register_defaults()` in `manager.py`
3. Add config entry to `configs/models.yaml`
4. If it needs a dedicated worker: add `Dockerfile.worker-<name>` and a new service
   in `docker-compose.yml` with the appropriate queue name

```python
# backend/app/models/my_model.py
from app.models.base import TTSModelBase, GenerateRequest, GenerateResult

class MyModel(TTSModelBase):
    model_id = "my-model"
    model_name = "My TTS Model"
    description = "..."
    supports_voice_cloning = False
    supports_streaming = False
    supports_speed = False

    def load(self, device: str = "cuda") -> None:
        self._model = ...       # load weights
        self._loaded = True

    def unload(self) -> None:
        self._model = None
        self._loaded = False
        import torch; torch.cuda.empty_cache()

    def generate(self, request: GenerateRequest) -> GenerateResult:
        audio_bytes = ...
        return GenerateResult(audio_bytes=audio_bytes, sample_rate=24000,
                              duration_seconds=..., format="wav")
```

## API Endpoints

### TTS (`/api/tts/`)
- `POST /generate` — submit job
- `GET /jobs/{id}` — poll status
- `GET /jobs/{id}/audio` — stream audio
- `GET /jobs` — list with pagination + filter (`page`, `page_size`, `status`, `model_id`, `search`)
- `DELETE /jobs/{id}` — cancel (revokes Celery task via `celery_app.control.revoke`)
- `POST /batch` — submit up to 100 lines; returns `batch_id` + `job_ids[]`
- `GET /batches/{id}` — aggregate batch status
- `GET /batches/{id}/zip` — stream ZIP of all complete audio files

### Voices (`/api/voices/`)
- `GET /` — list all voice profiles
- `POST /` — create (multipart upload of reference audio)
- `GET /{id}` — get single profile
- `PATCH /{id}` — update name, description, tags
- `GET /{id}/audio` — stream reference audio file
- `DELETE /{id}` — delete profile + audio file
- `GET /builtin/{model_id}` — list preset voices (e.g. Kokoro's 50+ voices)

### Models (`/api/models/`)
- `GET /` — all models with capabilities (`supports_speed`, `supports_pitch`, etc.)
- `GET /{id}` — single model info

### System (`/api/system/`)
- `GET /health` — health check
- `GET /gpu` — GPU stats snapshot

### OpenAI Compat (`/v1/`)
- `POST /audio/speech` — OpenAI-compatible; maps `tts-1` → Kokoro, `tts-1-hd` → Orpheus 3B
- `GET /models` — OpenAI-format model list

### WebSocket (`/ws/`)
- `/ws/jobs/{id}` — events: `queued`, `loading`, `generating`, `audio_chunk`, `complete`, `failed`
- `/ws/gpu` — GPU stats stream (1 s interval)

## Development Commands

```bash
# Start all services (COMPOSE_FILE in .env auto-loads gpu+override)
docker compose up -d

# Start lightweight (no GPU workers)
docker compose up postgres redis backend frontend

# Run backend tests
docker compose exec backend pytest tests/ -v

# Generate new migration (migrations apply automatically on backend startup)
docker compose exec backend alembic revision --autogenerate -m "description"

# Frontend type check (rollup native binding requires container)
docker compose exec frontend npm run check

# Rebuild one worker
docker compose up -d --build worker-orpheus

# Tail worker logs
docker compose logs -f worker-orpheus

# Access backend shell
docker compose exec backend bash

# Smoke test all models
python3 scripts/test_all_models.py
```

## Important File Locations

| Path | Purpose |
|------|---------|
| `backend/app/models/manager.py` | ModelManager singleton (hot-swap + idle timer) |
| `backend/app/models/base.py` | TTSModelBase abstract class |
| `backend/app/models/kokoro.py` | Kokoro 82M (standby model) |
| `backend/app/models/vibevoice.py` | VibeVoice 0.5B with streaming |
| `backend/app/models/vibevoice_1p5b.py` | VibeVoice 1.5B (zero-shot cloning) |
| `backend/app/models/fish_speech.py` | Fish Audio S2-Pro |
| `backend/app/models/qwen3_tts.py` | Qwen3 TTS 1.7B |
| `backend/app/models/orpheus.py` | Orpheus 3B (vLLM backend) |
| `backend/app/models/dia_tts.py` | Dia 1.6B dialogue model |
| `backend/app/models/_ref_audio.py` | Shared reference-audio preprocessing helper |
| `backend/app/asr/whisper.py` | faster-whisper singleton wrapper |
| `backend/app/eval/similarity.py` | speechbrain ECAPA-TDNN cosine similarity |
| `backend/app/tasks/asr_tasks.py` | `asr.transcribe_reference` (queue: `tts.asr`) |
| `backend/app/tasks/eval_tasks.py` | `eval.compute_similarity` (queue: `tts.kokoro`) |
| `backend/app/tasks/tts_tasks.py` | Celery tasks (generation + streaming) |
| `backend/app/api/endpoints/tts.py` | TTS routes + QUEUE_MAP |
| `backend/app/api/endpoints/openai_compat.py` | OpenAI /v1/audio/speech |
| `backend/app/db/models.py` | SQLAlchemy ORM (TTSJob, VoiceProfile) |
| `backend/alembic/versions/` | DB migration files |
| `configs/models.yaml` | Model registry (enable/disable/configure) |
| `frontend/src/routes/tts/+page.svelte` | Main TTS page |
| `frontend/src/routes/batch/+page.svelte` | Batch generation page |
| `frontend/src/routes/history/+page.svelte` | Job history page |
| `frontend/src/components/ModelParams.svelte` | Per-model parameter controls |
| `frontend/src/components/ToastContainer.svelte` | Toast notification system |
| `frontend/src/lib/stores/toasts.ts` | Toast store (addToast, removeToast) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GPU_DEVICE_ID` | `0` | CUDA device index for all workers |
| `MODEL_CACHE_DIR` | `./model_cache` | HuggingFace cache root (mounted as volume) |
| `AUDIO_OUTPUT_DIR` | `./audio_output` | Generated audio storage |
| `DATABASE_URL` | auto | PostgreSQL connection string |
| `CELERY_BROKER_URL` | auto | Redis URL |
| `HF_TOKEN` | — | Required for gated models (Orpheus 3B) |
| `BACKEND_PORT` | `8080` | Exposed API port |
| `FRONTEND_PORT` | `5200` | Exposed UI port |
| `WHISPER_MODEL` | `small` | faster-whisper model size (`tiny`/`base`/`small`/`medium`/`large-v3-turbo`) |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` (CPU) or `int8_float16` (GPU) |
| `AUTO_TRANSCRIBE_REFERENCES` | `true` | Master kill switch for reference auto-transcription |
| `F5_TTS_AUTO_TRANSCRIBE` | `true` | When false, F5-TTS raises instead of falling back to its built-in Whisper |

## Service URLs (dev)

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5200 |
| Backend API | http://localhost:8080/api |
| API Docs (Swagger) | http://localhost:8080/docs |
| ReDoc | http://localhost:8080/redoc |
| PostgreSQL | localhost:5432 (127.0.0.1 only) |
| Redis | localhost:6379 (127.0.0.1 only) |

## Reference-audio preprocessing

`backend/app/models/_ref_audio.py` exposes two helpers — every cloning model uses one
of them:

- `prepare_reference(path, target_sr, *, max_seconds, min_seconds, trim_silence,
  normalize_loudness, target_rms) -> (np.ndarray, sr)` — when the model's API takes a
  tensor / numpy array (CosyVoice's `prompt_speech_16k`, VibeVoice's voice samples).
- `prepare_reference_to_file(path, target_sr, *, max_seconds, ...) -> Path` — when the
  model's API takes a file path (Fish Speech, F5-TTS, Chatterbox, Dia, CosyVoice's
  prompt-wav-as-path mode). Cleaned WAV is cached at
  `${AUDIO_OUTPUT_DIR}/voices/_clean/{hash}.wav` keyed on
  `(input_path_mtime, target_sr, max_seconds)`, so re-uploads invalidate automatically
  and repeat generations skip the preprocessing pass.

Both decode via soundfile with a librosa fallback (handles MP3/M4A/OPUS/AAC/WEBM),
downmix to mono, resample with `torchaudio.functional.resample`, trim silence
(`librosa.effects.trim`, top_db=30), loudness-normalize to a target RMS with a
clip-safe scaling cap, and length-clip with a 50 ms cosine fade-out. They raise
`ReferenceAudioError` on unreadable files, all-silence input, or post-trim length
below `min_seconds`.

Per-model sample rate / max length defaults (set by the calling model class):

| Model | target_sr | max_seconds |
|-------|-----------|-------------|
| Fish Speech | 44100 | 30 |
| F5-TTS | 24000 | 12 |
| CosyVoice 2 | 24000 | 30 |
| VibeVoice 1.5B | 24000 | 30 |
| Qwen3 TTS | 24000 | 15 |
| Chatterbox | 24000 | 15 |
| Dia 1.6B | 44100 | 10 |

## Speaker-similarity scoring

`backend/app/eval/similarity.py` wraps `speechbrain/spkrec-ecapa-voxceleb` (192-dim
ECAPA-TDNN embeddings, Apache-2.0). Lazy-loads the encoder on first call; cache lives
under `${AUDIO_OUTPUT_DIR}/_models/speechbrain/spkrec-ecapa-voxceleb/` so cold starts
don't re-download. Reference embeddings are computed once per `VoiceProfile` and
persisted on `VoiceProfile.embedding_path` as a `.npy` file.

The Celery task `eval.compute_similarity` runs on the **`tts.kokoro` queue** (the
always-on lightweight worker — speechbrain is small and runs on CPU there, avoiding
GPU contention with TTS workers). It is dispatched from the `generate_tts` finally
block when both: (1) the job has a `voice_profile_id`, and (2) the job completed
successfully. Result persists on `TTSJob.speaker_similarity` as a float in [-1, 1].
Heuristic colour bands in the UI: green ≥ 0.5, amber 0.3–0.5, red < 0.3.

## Voice-id resolution gotchas (in `tts_tasks.py`)

Two bugs that bit us during the cloning overhaul; both live around `voice_id` /
`voice_profile_id` resolution at the top of `generate_tts`:

1. **`.npy` embeddings being passed as voice references.**
   `VoiceProfile.embedding_path` is overloaded — the similarity scorer caches its
   ECAPA reference embedding there as a `.npy`. The model code expects a path to a
   reference *audio* file. The Celery task must explicitly skip any `embedding_path`
   ending in `.npy` and fall back to `reference_audio_path`. See the comment block in
   `backend/app/tasks/tts_tasks.py` around the `voice_artifact` resolution.
2. **UUID not being rewritten to a path.** When the API submits a job with a
   `VoiceProfile` UUID, both `job.voice_id` and `job.voice_profile_id` get the UUID.
   The model receives a raw UUID string, `Path(voice_id).exists()` returns false, and
   cloning silently falls back to the default voice. The task **must** resolve the
   UUID to the profile's `reference_audio_path` (or cleaned cache path) before
   invoking the model.

If either of these regress, the symptom is a "successful" generation that sounds
nothing like the reference and a similarity score below 0.2.

## DB Schema Notes

`TTSJob` columns of note:
- `celery_task_id` — set at task start; used by cancel endpoint to revoke
- `batch_id` — UUID grouping jobs created by a single batch request
- `status` — enum: `pending`, `running`, `complete`, `failed`, `cancelled`

`VoiceProfile` columns of note:
- `description` — optional free-text description
- `tags` — JSON array of string tags
- `reference_audio_path` — path to uploaded reference audio file
- `reference_text` — auto-transcribed (or manually edited) reference transcript
- `reference_text_status` — `pending` / `ready` / `failed` / `manual`
- `reference_language` — language code Whisper detected
- `embedding_path` — `.npy` path of the cached ECAPA reference embedding (do **not**
  pass to TTS models as `voice_id` — see "Voice-id resolution gotchas" above)

`TTSJob.speaker_similarity` — float in [-1, 1], cosine similarity between the cleaned
reference and the generated audio (populated by `eval.compute_similarity`).

## Known Limitations / Deferred

- **Qwen3 streaming**: `non_streaming_mode=False` exists but docs say it only "simulates"
  streaming text input — not true PCM streaming. Currently forced to `non_streaming_mode=True`.
- **flash-attn in base image**: requires nvcc at build time (not in python:3.12-slim). Main
  worker uses a separate base image with flash-attn pre-built. Secondary workers use sdpa fallback.
