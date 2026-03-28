#!/usr/bin/env bash
# scripts/download-models.sh
# ─────────────────────────────────────────────────────────────────────────────
# Downloads all OpenSpeakers model weights from HuggingFace Hub into the
# local model_cache directory so workers can run with HF_HUB_OFFLINE=1.
#
# Usage:
#   ./scripts/download-models.sh [options]
#
# Options:
#   --models <list>   Comma-separated model IDs to download (default: all)
#                     IDs: kokoro,vibevoice,vibevoice-1.5b,fish-speech-s2,
#                          qwen3-tts,f5-tts,chatterbox,cosyvoice-2,parler-tts,
#                          orpheus-3b,dia-1b
#   --cache-dir <dir> HF cache root (default: ./model_cache/huggingface)
#   --hf-token <tok>  HuggingFace token (or set HF_TOKEN env var)
#   --dry-run         Print what would be downloaded without downloading
#   -h, --help        Show this help
#
# Requirements:
#   • Python 3 with huggingface_hub installed:
#       pip3 install huggingface_hub --break-system-packages
#
# After this script runs, start workers with:
#   docker compose ... up -d
# Workers use HF_HUB_OFFLINE=1 by default and will find weights in the cache.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
CACHE_DIR="${REPO_DIR}/model_cache/huggingface"
HF_TOKEN="${HF_TOKEN:-}"
SELECTED_MODELS=""
DRY_RUN=false

# ── Argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --models)   SELECTED_MODELS="$2"; shift 2 ;;
    --cache-dir) CACHE_DIR="$2";      shift 2 ;;
    --hf-token) HF_TOKEN="$2";        shift 2 ;;
    --dry-run)  DRY_RUN=true;         shift ;;
    -h|--help)
      sed -n '3,/^[^#]/{ /^[^#]/d; s/^# \{0,2\}//; p }' "$0"
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── Helpers ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[download]${NC} $*"; }
success() { echo -e "${GREEN}[download]${NC} $*"; }
warn()    { echo -e "${YELLOW}[download]${NC} $*"; }
error()   { echo -e "${RED}[download]${NC} $*" >&2; exit 1; }
hr()      { echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"; }

download_hf() {
  # download_hf <repo_id> [<token_required>]
  local repo_id="$1"
  local requires_token="${2:-false}"

  if $DRY_RUN; then
    echo -e "${YELLOW}[dry-run]${NC} Would download: $repo_id"
    return
  fi

  local token_arg=""
  if [[ -n "$HF_TOKEN" ]]; then
    token_arg="--token $HF_TOKEN"
  elif [[ "$requires_token" == "true" ]]; then
    warn "  HF_TOKEN not set — $repo_id may require authentication"
    warn "  Set HF_TOKEN env var or pass --hf-token <token>"
  fi

  info "  Downloading: $repo_id"
  HF_HOME="$CACHE_DIR" python3 - "$repo_id" $token_arg <<'PYEOF'
import sys, os
from huggingface_hub import snapshot_download
args = sys.argv[1:]
repo_id = args[0]
token = None
if '--token' in args:
    token = args[args.index('--token') + 1]
path = snapshot_download(repo_id=repo_id, token=token)
print(f"  → {path}")
PYEOF
}

# ── Check Python + huggingface_hub ────────────────────────────────────────────
if ! python3 -c "import huggingface_hub" 2>/dev/null; then
  error "huggingface_hub not installed. Run: pip3 install huggingface_hub --break-system-packages"
fi

# ── Model definitions ─────────────────────────────────────────────────────────
# Format: "model_id|hf_repo_id|requires_hf_token|description"
declare -a MODELS=(
  "kokoro|hexgrad/Kokoro-82M|false|Kokoro 82M (fast, high quality, 0.5GB)"
  "vibevoice|microsoft/VibeVoice-Realtime-0.5B|false|VibeVoice 0.5B streaming (5GB)"
  "vibevoice-1.5b|microsoft/VibeVoice-1.5B|false|VibeVoice 1.5B zero-shot cloning (12GB)"
  "fish-speech-s2|fishaudio/s2-pro|false|Fish Audio S2-Pro (22GB)"
  "qwen3-tts|Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice|false|Qwen3 TTS 1.7B (10GB)"
  "f5-tts|SWivid/F5-TTS|false|F5-TTS flow matching (3GB)"
  "f5-tts-vocos|charactr/vocos-mel-24khz|false|Vocos vocoder required by F5-TTS (50MB)"
  "chatterbox|ResembleAI/chatterbox|false|Chatterbox TTS (5GB)"
  "cosyvoice-2|FunAudioLLM/CosyVoice2-0.5B|false|CosyVoice 2.0 (5GB)"
  "parler-tts|parler-tts/parler-tts-mini-v1|false|Parler TTS Mini v1 (3GB)"
  "orpheus-3b|canopylabs/orpheus-3b-0.1-ft|false|Orpheus 3B (53GB — largest model)"
  "dia-1b|nari-labs/Dia-1.6B-0626|false|Dia 1.6B dialogue (10GB)"
)

# ── Filter to selected models ──────────────────────────────────────────────────
if [[ -n "$SELECTED_MODELS" ]]; then
  IFS=',' read -ra SELECTED <<< "$SELECTED_MODELS"
else
  SELECTED=()
fi

# ── Show plan ─────────────────────────────────────────────────────────────────
hr
info "OpenSpeakers Model Downloader"
info "Cache dir: $CACHE_DIR"
[[ -n "$HF_TOKEN" ]] && info "HF token:  set" || info "HF token:  not set (gated models will fail)"
hr

if [[ -n "$SELECTED_MODELS" ]]; then
  info "Downloading selected models: $SELECTED_MODELS"
else
  info "Downloading ALL models (pass --models to select specific ones)"
fi
echo

mkdir -p "$CACHE_DIR"

# ── Download loop ──────────────────────────────────────────────────────────────
downloaded=0
skipped=0
failed=0

for entry in "${MODELS[@]}"; do
  IFS='|' read -r model_id hf_repo requires_token description <<< "$entry"

  # Skip if not in selected list (when filter is active)
  if [[ ${#SELECTED[@]} -gt 0 ]]; then
    found=false
    for sel in "${SELECTED[@]}"; do
      [[ "$sel" == "$model_id" ]] && { found=true; break; }
    done
    if ! $found; then
      continue
    fi
  fi

  info "[$model_id] $description"
  info "  repo: $hf_repo"

  if download_hf "$hf_repo" "$requires_token"; then
    success "  ✓ $model_id done"
    downloaded=$((downloaded + 1))
  else
    warn "  ✗ $model_id FAILED (see error above)"
    failed=$((failed + 1))
  fi
  echo
done

# ── Summary ───────────────────────────────────────────────────────────────────
hr
success "Download complete"
info "Downloaded: $downloaded | Skipped: $skipped | Failed: $failed"
if [[ $failed -gt 0 ]]; then
  warn "Some models failed. Re-run with --models <id> to retry specific ones."
  exit 1
fi
hr
