#!/usr/bin/env bash
# scripts/package-offline.sh
# ─────────────────────────────────────────────────────────────────────────────
# Creates a self-contained offline install package for OpenSpeakers.
#
# What gets bundled:
#   • All 7 Docker images (saved as compressed .tar.gz files)
#   • Model weights from NAS + local model_cache (Kokoro etc.)
#   • VibeVoice Python source repo
#   • Config files and compose files
#   • install.sh for the target machine
#
# Usage:
#   ./scripts/package-offline.sh [options]
#
# Options:
#   -o, --output <dir>     Output directory (default: ./dist/openspeakers-offline-YYYYMMDD)
#   --no-models            Skip copying model weights (useful if target already has them)
#   --no-vibevoice-repo    Skip copying VibeVoice source repo
#   --skip-image <name>    Skip saving a specific image (repeatable)
#   --dry-run              Print what would be done without doing it
#   -h, --help             Show this help
#
# Requirements (source machine):
#   • Docker with all images built and tagged
#   • rsync
#   • Models at /mnt/nas/models/{vibevoice,fish-speech,Qwen}
#   • VibeVoice repo at /mnt/nvm/repos/VibeVoice
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
OUTPUT_DIR=""
COPY_MODELS=true
COPY_VIBEVOICE_REPO=true
DRY_RUN=false
SKIP_IMAGES=()

VIBEVOICE_REPO=/mnt/nvm/repos/VibeVoice

# Docker images to save: "tag|output_filename"
declare -A IMAGES=(
  ["open_speakers-backend:latest"]="backend"
  ["open_speakers-worker:latest"]="worker"
  ["open_speakers-worker-fish:latest"]="worker-fish"
  ["open_speakers-worker-qwen3:latest"]="worker-qwen3"
  ["open_speakers-worker-f5:latest"]="worker-f5"
  ["open_speakers-worker-orpheus:latest"]="worker-orpheus"
  ["open_speakers-worker-dia:latest"]="worker-dia"
  ["open_speakers-frontend:latest"]="frontend"
  ["postgres:17.5-alpine"]="postgres"
  ["redis:8.2.2-alpine3.22"]="redis"
)

# ── Argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output)      OUTPUT_DIR="$2";            shift 2 ;;
    --no-models)      COPY_MODELS=false;           shift ;;
    --no-vibevoice-repo) COPY_VIBEVOICE_REPO=false; shift ;;
    --skip-image)     SKIP_IMAGES+=("$2");         shift 2 ;;
    --dry-run)        DRY_RUN=true;                shift ;;
    -h|--help)
      sed -n '/^# Usage:/,/^[^#]/{ /^[^#]/d; s/^# \{0,2\}//; p }' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$OUTPUT_DIR" ]] && OUTPUT_DIR="$REPO_DIR/dist/openspeakers-offline-$(date +%Y%m%d)"

# ── Helpers ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[package]${NC} $*"; }
success() { echo -e "${GREEN}[package]${NC} $*"; }
warn()    { echo -e "${YELLOW}[package]${NC} $*"; }
error()   { echo -e "${RED}[package]${NC} $*" >&2; exit 1; }
hr()      { echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"; }

run() {
  if $DRY_RUN; then
    echo -e "${YELLOW}[dry-run]${NC} $*"
  else
    "$@"
  fi
}

is_skipped_image() {
  local tag="$1"
  for skip in "${SKIP_IMAGES[@]:-}"; do
    [[ "$tag" == "$skip" ]] && return 0
  done
  return 1
}

# ── Pre-flight checks ──────────────────────────────────────────────────────────
hr
info "OpenSpeakers Offline Packager"
info "Output: $OUTPUT_DIR"
hr

if ! command -v docker &>/dev/null; then
  error "docker is not installed or not in PATH"
fi
if ! command -v rsync &>/dev/null; then
  error "rsync is required but not found"
fi

# Check all images exist (except skipped)
info "Checking Docker images..."
missing_images=()
for tag in "${!IMAGES[@]}"; do
  if is_skipped_image "$tag"; then
    warn "  skipping: $tag"
    continue
  fi
  if ! docker image inspect "$tag" &>/dev/null; then
    missing_images+=("$tag")
  else
    size=$(docker image inspect "$tag" --format='{{.Size}}' | numfmt --to=iec 2>/dev/null || echo "?")
    info "  found: $tag ($size)"
  fi
done

if [[ ${#missing_images[@]} -gt 0 ]]; then
  warn "The following images are missing:"
  for img in "${missing_images[@]}"; do
    warn "  - $img"
  done
  echo
  read -r -p "Build missing images now? [y/N] " build_answer
  if [[ "${build_answer,,}" == "y" ]]; then
    info "Building backend + workers..."
    run docker compose -f "$REPO_DIR/docker-compose.yml" \
      -f "$REPO_DIR/docker-compose.override.yml" build
    info "Building production frontend..."
    run docker build -t open_speakers-frontend:latest \
      -f "$REPO_DIR/frontend/Dockerfile.prod" "$REPO_DIR/frontend"
  else
    error "Cannot package without all required images. Aborting."
  fi
fi

# Special case: frontend image needs to be the PRODUCTION build (nginx), not dev (vite)
# Check if current frontend image is vite-based and warn.
frontend_cmd=$(docker image inspect open_speakers-frontend:latest \
  --format='{{json .Config.Cmd}}' 2>/dev/null || echo "")
if echo "$frontend_cmd" | grep -qi "vite\|dev\|node"; then
  warn "The current open_speakers-frontend:latest appears to be the DEV image."
  warn "It requires source code mounts and won't work offline."
  echo
  read -r -p "Build a production frontend image (Dockerfile.prod) now? [Y/n] " prod_answer
  if [[ "${prod_answer,,}" != "n" ]]; then
    info "Building production frontend from Dockerfile.prod..."
    # Save dev image tag under a different name so we don't lose it
    run docker tag open_speakers-frontend:latest open_speakers-frontend:dev
    run docker build -t open_speakers-frontend:latest \
      -f "$REPO_DIR/frontend/Dockerfile.prod" "$REPO_DIR/frontend"
    success "Production frontend built."
  else
    warn "Proceeding with dev frontend image — it may not work offline."
  fi
fi

# ── Create directory structure ────────────────────────────────────────────────
info "Creating package directory structure..."
run mkdir -p \
  "$OUTPUT_DIR/images" \
  "$OUTPUT_DIR/models" \
  "$OUTPUT_DIR/audio_output" \
  "$OUTPUT_DIR/configs"

# ── Save Docker images ────────────────────────────────────────────────────────
hr
info "Saving Docker images (this may take a while)..."
total_images=0
for tag in "${!IMAGES[@]}"; do
  if is_skipped_image "$tag"; then continue; fi
  name="${IMAGES[$tag]}"
  out="$OUTPUT_DIR/images/${name}.tar.gz"
  if [[ -f "$out" ]]; then
    warn "  already exists, skipping: ${name}.tar.gz"
    continue
  fi
  info "  saving: $tag → images/${name}.tar.gz"
  if ! $DRY_RUN; then
    docker save "$tag" | gzip -1 > "$out"
  fi
  total_images=$((total_images + 1))
done
success "Saved $total_images image(s)."

# ── Copy model weights ────────────────────────────────────────────────────────
if $COPY_MODELS; then
  hr
  info "Copying model weights..."
  info "Source: $REPO_DIR/model_cache (HF hub cache populated by download-models.sh)"
  info "Tip: Run ./scripts/download-models.sh first if cache is empty."

  # Copy the full HF hub cache — all models land here via snapshot_download
  if [[ -d "$REPO_DIR/model_cache" ]]; then
    info "  Copying HF model cache (all models)..."
    run rsync -a --info=progress2 \
      --exclude='*.lock' \
      --exclude='tmp*' \
      "$REPO_DIR/model_cache/" \
      "$OUTPUT_DIR/model_cache/"
    success "  HF cache copied."
  else
    warn "  model_cache not found at $REPO_DIR/model_cache"
    warn "  Run: ./scripts/download-models.sh"
    warn "  Workers will attempt HF downloads on first run (requires internet)"
  fi

  success "Model weights done."
fi

# ── Copy VibeVoice Python source repo ─────────────────────────────────────────
if $COPY_VIBEVOICE_REPO; then
  hr
  info "Copying VibeVoice source repo (Python package only)..."
  if [[ -d "$VIBEVOICE_REPO" ]]; then
    run rsync -a --info=progress2 \
      --exclude='.git' \
      --exclude='outputs' \
      --exclude='demo' \
      --exclude='Figures' \
      --exclude='finetuning-asr' \
      --exclude='finetuning-tts' \
      --exclude='docs' \
      --exclude='__pycache__' \
      --exclude='*.pyc' \
      --exclude='*.egg-info' \
      "$VIBEVOICE_REPO/" \
      "$OUTPUT_DIR/vibevoice-repo/"
    success "VibeVoice source copied."
  else
    warn "VibeVoice repo not found at $VIBEVOICE_REPO — skipping"
    warn "The 'worker' service will fail to start without it."
  fi
fi

# ── Copy config / compose files ───────────────────────────────────────────────
hr
info "Copying project files..."
run cp "$REPO_DIR/docker-compose.yml"         "$OUTPUT_DIR/"
run cp "$REPO_DIR/docker-compose.gpu.yml"     "$OUTPUT_DIR/"
run cp "$REPO_DIR/docker-compose.offline.yml" "$OUTPUT_DIR/"
run cp "$REPO_DIR/.env.example"               "$OUTPUT_DIR/"
run rsync -a "$REPO_DIR/configs/"             "$OUTPUT_DIR/configs/"
success "Config files copied."

# ── Generate install.sh ────────────────────────────────────────────────────────
hr
info "Generating install.sh..."

INSTALL_SH="$OUTPUT_DIR/install.sh"
if ! $DRY_RUN; then
cat > "$INSTALL_SH" << 'INSTALL_SCRIPT'
#!/usr/bin/env bash
# install.sh — OpenSpeakers offline installer
# Run this on the target (air-gapped) machine from the package root directory.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[install]${NC} $*"; }
success() { echo -e "${GREEN}[install]${NC} $*"; }
warn()    { echo -e "${YELLOW}[install]${NC} $*"; }
error()   { echo -e "${RED}[install]${NC} $*" >&2; exit 1; }
hr()      { echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"; }

hr
info "OpenSpeakers Offline Installer"
info "Install root: $SCRIPT_DIR"
hr

# ── Pre-flight checks ──────────────────────────────────────────────────────────
info "Checking prerequisites..."

command -v docker &>/dev/null || error "Docker is not installed. Install Docker Engine first."

# Check docker compose plugin (v2)
if ! docker compose version &>/dev/null; then
  error "Docker Compose plugin (v2) not found. Install with: sudo apt install docker-compose-plugin"
fi

# Check NVIDIA container toolkit
if ! docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi &>/dev/null 2>&1; then
  warn "nvidia-container-toolkit may not be configured, or no GPU available."
  warn "GPU workers will fail to start without NVIDIA runtime support."
  echo
  read -r -p "Continue anyway? [y/N] " ans
  [[ "${ans,,}" == "y" ]] || error "Aborted."
fi

success "Prerequisites OK."

# ── Load Docker images ─────────────────────────────────────────────────────────
hr
info "Loading Docker images from images/..."
for tarball in images/*.tar.gz; do
  [[ -f "$tarball" ]] || continue
  name=$(basename "$tarball" .tar.gz)
  info "  loading: $name"
  docker load < "$tarball"
done
success "All images loaded."

# ── Set up .env ────────────────────────────────────────────────────────────────
hr
if [[ ! -f .env ]]; then
  info "Creating .env from .env.example..."
  cp .env.example .env

  # Patch paths to use local model cache (HF hub cache populated by download-models.sh)
  sed -i "s|^MODEL_CACHE_DIR=.*|MODEL_CACHE_DIR=${SCRIPT_DIR}/model_cache|" .env
  sed -i "s|^AUDIO_OUTPUT_DIR=.*|AUDIO_OUTPUT_DIR=${SCRIPT_DIR}/audio_output|" .env

  warn "Review .env and set POSTGRES_PASSWORD and SECRET_KEY before production use."
else
  info ".env already exists, skipping creation."
fi

# ── Create runtime directories ─────────────────────────────────────────────────
mkdir -p audio_output
# voice uploads sub-directory
mkdir -p audio_output/voices

# ── Start services ─────────────────────────────────────────────────────────────
hr
info "Starting OpenSpeakers stack..."
docker compose \
  -f docker-compose.yml \
  -f docker-compose.offline.yml \
  -f docker-compose.gpu.yml \
  up -d

success "Services started."

# ── Run database migrations ────────────────────────────────────────────────────
hr
info "Waiting for backend to be ready..."
for i in $(seq 1 30); do
  if docker compose -f docker-compose.yml -f docker-compose.offline.yml \
      exec -T backend curl -sf http://localhost:8080/health &>/dev/null; then
    break
  fi
  sleep 2
done

info "Running Alembic migrations..."
docker compose -f docker-compose.yml -f docker-compose.offline.yml \
  exec -T backend alembic upgrade head

success "Migrations complete."

# ── Done ───────────────────────────────────────────────────────────────────────
hr
success "OpenSpeakers is running!"
echo
# Read FRONTEND_PORT from .env if set
FRONTEND_PORT=$(grep -E '^FRONTEND_PORT=' .env 2>/dev/null | cut -d= -f2 || echo "5200")
echo "  Frontend:  http://$(hostname -I | awk '{print $1}'):${FRONTEND_PORT}"
echo "  API:       http://$(hostname -I | awk '{print $1}'):8080/api"
echo "  API Docs:  http://$(hostname -I | awk '{print $1}'):8080/docs"
echo
info "To stop:    docker compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.gpu.yml down"
info "To restart: docker compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.gpu.yml restart"
hr
INSTALL_SCRIPT

chmod +x "$INSTALL_SH"
fi

success "install.sh written."

# ── Final summary ─────────────────────────────────────────────────────────────
hr
if ! $DRY_RUN; then
  TOTAL_SIZE=$(du -sh "$OUTPUT_DIR" 2>/dev/null | cut -f1 || echo "?")
  success "Package ready: $OUTPUT_DIR"
  info  "Total size: $TOTAL_SIZE"
  echo
  info "Contents:"
  echo "  images/        $(ls "$OUTPUT_DIR/images/" 2>/dev/null | wc -l) image tarballs"
  [[ -d "$OUTPUT_DIR/model_cache" ]] && \
  echo "  model_cache/   $(du -sh "$OUTPUT_DIR/model_cache/" 2>/dev/null | cut -f1) (HF model weights)"
  [[ -d "$OUTPUT_DIR/vibevoice-repo" ]] && \
  echo "  vibevoice-repo $(du -sh "$OUTPUT_DIR/vibevoice-repo/" 2>/dev/null | cut -f1)"
  echo "  configs/       models.yaml, presets.yaml"
  echo "  install.sh     run this on the target machine"
  echo
  info "To transfer (example using rsync over SSH):"
  echo "  rsync -avz --progress $OUTPUT_DIR/ user@target:/opt/openspeakers/"
  info "Or create a tarball for USB transfer:"
  echo "  tar -czf openspeakers-offline.tar.gz -C $(dirname "$OUTPUT_DIR") $(basename "$OUTPUT_DIR")"
else
  success "Dry run complete — no files were written."
fi
hr
