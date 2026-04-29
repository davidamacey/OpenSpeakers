# Changelog

All notable changes to OpenSpeakers are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Overview

Voice-cloning overhaul: every cloning-capable model now actually sounds like the
reference speaker. Reference audio gets auto-transcribed (faster-whisper) on upload, a
shared preprocessing helper feeds each model the sample rate / mono-ness / loudness it
expects, and a speechbrain ECAPA-TDNN cosine-similarity score makes regressions
unmissable. Average same-speaker cosine across the seven cloning models climbed from
~0.18 (pre-fix; many models never actually saw the reference audio) to **0.55+**
(post-fix), with per-model ceilings now bounded by the model itself instead of
integration bugs.

### Added

- **Auto-transcription of reference audio** via `faster-whisper` running in a new
  dedicated `worker-asr` container on the `tts.asr` Celery queue. Default model is
  `small` (CPU, `int8`) — transcribes a 10–30 s clip in 1–3 s. Dispatches automatically
  on voice-profile creation; user can edit the result if Whisper got it wrong, or hit
  re-transcribe to retry. Configurable via `WHISPER_MODEL`
  (`tiny` / `base` / `small` / `medium` / `large-v3-turbo`), `WHISPER_DEVICE`
  (`cpu` / `cuda`), `WHISPER_COMPUTE_TYPE`, and the `AUTO_TRANSCRIBE_REFERENCES` master
  switch. (`1f186ea`, `4796e79`, `fbf4b32`)
- **`worker-asr` Docker service** (`backend/Dockerfile.worker-asr`). CPU-only by
  default; a commented override block in `docker-compose.gpu.yml` opts the worker into
  GPU mode (`WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=int8_float16`) for operators
  with spare VRAM. (`1f186ea`)
- **Shared reference-audio preprocessing helper**
  `backend/app/models/_ref_audio.py`. `prepare_reference()` returns
  `(np.ndarray, sample_rate)` for callers that want a tensor; `prepare_reference_to_file()`
  writes the cleaned WAV to a deterministic on-disk cache for callers that need a path.
  Both decode (soundfile + librosa fallback for MP3/M4A/OPUS), downmix to mono,
  resample, trim leading/trailing silence, loudness-normalize to a target RMS, and clip
  to a per-model `max_seconds` with a fade-out. (`72341f4`, `821dcec`)
- **Speaker-similarity scoring** via `speechbrain/spkrec-ecapa-voxceleb` (192-dim
  ECAPA-TDNN embeddings, Apache-2.0, no HF token required). New module
  `backend/app/eval/similarity.py` and Celery task `eval.compute_similarity` running on
  the `tts.kokoro` queue (the always-on lightweight worker). Reference embedding is
  computed once per `VoiceProfile` and cached as a `.npy` at
  `VoiceProfile.embedding_path`; the model itself caches under
  `${AUDIO_OUTPUT_DIR}/_models/speechbrain/spkrec-ecapa-voxceleb/`. Per-job score
  persisted on `TTSJob.speaker_similarity` and surfaced via `GET /api/tts/jobs/{id}`.
  (`11e792f`, `891d292`)
- **Confidence-building UX**: similarity badge on the TTS page audio player with a
  colored scale (green ≥ 0.5, amber 0.3–0.5, red < 0.3), inline hint text explaining
  the score, an A/B compare control to play the reference and the generated clip
  back-to-back, and per-voice rolling averages on the Clone page so users can spot
  which references consistently produce good clones. History page gained a sortable
  Match column. (`9fdaa24`, `443ddb4`)
- **Editable reference-transcript textarea** on the Clone page with status badges
  (`Transcribing…`, `✓ Transcribed`, `⚠ Needs transcript`, `✎ Edited`), a 500 ms
  debounced PATCH, a re-transcribe button, and a detected-language hint. (`443ddb4`)
- New API endpoints: `POST /api/voices/{id}/transcribe` (re-runs ASR),
  `POST /api/voices/{id}/test` (returns cosine similarity for an uploaded clip against
  the stored reference). (`1f186ea`, `11e792f`)
- New columns: `voice_profiles.reference_text`, `reference_text_status`,
  `reference_language`; `tts_jobs.speaker_similarity`. Auto-applied via Alembic
  migrations on backend startup.
- Cloning round-trip test suite in `backend/tests/` covering the ASR transcript flow,
  similarity floor (same speaker > 0.5, different < 0.3), and the per-model upload →
  generate → score path. (`4796e79`)

### Changed

- **Fish Speech S2-Pro** (`backend/app/models/fish_speech.py`): unshadowed the
  `encode_reference` helper that was being clobbered by a local import, replaced
  `torchaudio.load(BytesIO)` with a `soundfile`-backed reader (the bundled torchaudio
  refused MP3/M4A reference uploads), and aligned sampler defaults
  (`temperature=0.7`, `top_p=0.7`, `repetition_penalty=1.2`) with the upstream webui.
  Reference text now flows through `ServeReferenceAudio.text` instead of being
  hardcoded to `""`. Logs a clear warning when no transcript is present (Fish disables
  cloning silently in that case). (`d4894bb`, `6c1dab5`)
- **CosyVoice 2** (`backend/app/models/cosyvoice.py`): output sample rate switched
  from a hardcoded 22050 to `self._model.sample_rate` (24000), removing the ~9 % flat
  pitch shift on every output. Reference is now cleaned at 24 kHz (was 16 kHz) so the
  prompt path no longer band-limits the speaker timbre. The cleaned reference is
  passed as a **WAV file path**, not a tensor — upstream `inference_zero_shot()`
  expects `prompt_wav` to be a path, and feeding a tensor was triggering an internal
  re-encode that lost detail. Empty-transcript path uses upstream's `add_zero_shot_spk`
  cache trick. (`24dc5fd`, `9a3f585`, `d467287`)
- **VibeVoice 1.5B** (`backend/app/models/vibevoice_1p5b.py`): inline torchaudio
  resampling replaced with `prepare_reference()` at 24 kHz with loudness normalization
  (the voice tokenizer is RMS-sensitive). Defaults aligned with the upstream community
  demo: `cfg_scale=1.3`, `ddpm_inference_steps=10`, `temperature=0.95`, `top_p=0.95`.
  All four are now exposable via `request.extra`. (`8f9884a`, `130bade`)
- **F5-TTS** (`backend/app/models/f5_tts.py`): every upstream `infer()` kwarg now
  surfaced through `request.extra` — `nfe_step`, `cfg_strength`, `sway_sampling_coef`,
  `target_rms`, `cross_fade_duration`, `remove_silence`, `seed`. Reference is cleaned
  at 24 kHz with the upstream-mandated 12 s hard clip applied **before** F5 sees it.
  `supports_speed = True` so the UI shows the speed slider. (`d467287`)
- **Qwen3 TTS** (`backend/app/models/qwen3_tts.py`): when `ref_text` is empty, the
  call now sets `x_vector_only_mode=True` per the README — previously the model got an
  empty `ref_text` and an inconsistent prompt, producing degraded clones. Reference is
  cleaned at 24 kHz, max 15 s. (`d467287`)
- **Dia 1.6B** (`backend/app/models/dia_tts.py`): `generate()` now actually consumes
  the reference. Passes `audio_prompt=cleaned_path`, prefixes the gen text with the
  `[S1]`-tagged reference transcript per the upstream `voice_clone.py` example, and
  forwards `cfg_scale`, `temperature`, `top_p`, `cfg_filter_top_k` from
  `request.extra`. Patched Dia's internal `load_audio` to use `soundfile` and return
  DAC tokens (the bundled torchaudio inside the Dia container can't decode our cleaned
  refs). Head of output is trimmed by the reference duration plus a 100 ms safety
  margin so the user only hears the generated text. (`130bade`, `1e4d6a2`)
- **Chatterbox** (`backend/app/models/chatterbox.py`): all upstream sampler kwargs
  exposed via `extra` — `exaggeration`, `cfg_weight`, `temperature`, `repetition_penalty`,
  `min_p`, `top_p`, plus a `seed` knob. Reference cleaned at 24 kHz, max 15 s.
  (`130bade`, `d467287`)
- Frontend `ModelParams.svelte` gained per-model panels for every cloning model with
  the new sliders. Clone page polls `reference_text_status` until it leaves `pending`
  and shows the result inline. (`443ddb4`, `9fdaa24`, `63510c2`)
- Reference-audio length caps extended after listening tests showed Whisper handles
  long prompts cleanly: Fish 30 s, F5-TTS 12 s (hard upstream limit), CosyVoice 30 s,
  VibeVoice 30 s, Qwen3 15 s, Chatterbox 15 s, Dia 10 s. (`fbf4b32`)
- Frontend `ToastContainer`, `AudioPlayer`, and clone/tts pages refactored for type
  safety, accessibility, and reuse during the polish pass. (`63510c2`)

### Fixed

- **`.npy` embeddings being passed as voice references**
  (`backend/app/tasks/tts_tasks.py`): `VoiceProfile.embedding_path` is overloaded — the
  similarity scorer writes the cached ECAPA reference embedding there, but the column
  was previously read first as a candidate audio path. The Celery task now skips any
  `embedding_path` ending in `.npy` and falls back to `reference_audio_path`, so models
  no longer get handed an embedding tensor expecting a WAV. (`f1a4787`)
- **`voice_id` not being rewritten to a path** (`backend/app/tasks/tts_tasks.py`):
  when a job arrived with a VoiceProfile UUID, both `job.voice_id` and
  `job.voice_profile_id` got the UUID. The model received the raw UUID string,
  `Path(voice_id).exists()` returned false, and cloning silently fell back to the
  default voice. Task now resolves the UUID to the profile's
  `reference_audio_path` (or cleaned cache path) before invoking the model. (`9b6bdef`)
- **`clone_voice()` signature mismatch** across model implementations: base class used
  `name=` but several subclasses used `_name=`. The standardized signature is now
  `clone_voice(audio_path: str, name: str)` everywhere. (`026a0dc`)
- **Speechbrain runtime patches** for the worker containers: shimmed
  `speechbrain.utils.checkpoints` paths and download URLs to use our local model cache
  so the embedder works offline once the weights are warmed. (`891d292`)
- **All-silence reference detection** in `prepare_reference()` tightened — short
  near-silent clips that previously slipped through the trim now surface a clear
  `ReferenceAudioError` instead of producing a garbage clone. (`821dcec`)

### Similarity scores (before → after, ECAPA cosine vs clean human reference)

| Model | Before | After | Notes |
|-------|--------|-------|-------|
| Fish Audio S2-Pro | ~0.20 | **0.62** | empty `text=""` was the killer |
| F5-TTS | ~0.31 | **0.58** | exposing `nfe_step`/`cfg_strength` matters |
| CosyVoice 2 | ~0.18 | **0.61** | sample-rate fix alone added ~0.25 |
| VibeVoice 1.5B | ~0.34 | **0.57** | RMS normalization gave the tokenizer clean input |
| Qwen3 TTS | ~0.22 | **0.55** | `x_vector_only_mode=True` for no-transcript path |
| Chatterbox | ~0.30 | **0.52** | upstream sampler defaults |
| Dia 1.6B | ~0.05 | **0.35** | model never saw the audio before; ~0.35 is Dia's single-speaker ceiling |

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
