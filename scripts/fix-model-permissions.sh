#!/bin/bash
# Fix model cache directory permissions for OpenSpeakers.
#
# The main worker and kokoro worker run as UID 1000 (appuser) inside the
# container. The host model_cache/huggingface and model_cache/torch directories
# must be owned by UID 1000 or be world-writable, otherwise the workers cannot
# download or read model weights.
#
# Usage:
#   ./scripts/fix-model-permissions.sh
#
# Run this if you see "Permission denied" errors in worker logs.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${GREEN}OpenSpeakers Model Cache Permission Fixer${NC}"
echo "============================================"
echo ""

# Read MODEL_CACHE_DIR from .env if present
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    MODEL_CACHE_DIR=$(grep 'MODEL_CACHE_DIR' "$PROJECT_ROOT/.env" | grep -v '^#' | cut -d'#' -f1 | cut -d'=' -f2 | tr -d ' "' | head -1)
fi
MODEL_CACHE_DIR="${MODEL_CACHE_DIR:-$PROJECT_ROOT/model_cache}"
echo -e "${YELLOW}Model cache directory: ${MODEL_CACHE_DIR}${NC}"
echo ""

if [[ ! -d "$MODEL_CACHE_DIR" ]]; then
    echo "Model cache directory does not exist yet — nothing to fix."
    exit 0
fi

fix_via_docker() {
    echo "Fixing permissions via Docker (no sudo needed)..."
    docker run --rm \
        -v "$MODEL_CACHE_DIR:/mc" \
        busybox:latest \
        sh -c "chown -R 1000:1000 /mc && find /mc -type d -exec chmod 755 {} \;"
}

fix_via_sudo() {
    echo "Fixing permissions via sudo..."
    sudo chown -R 1000:1000 "$MODEL_CACHE_DIR"
    sudo find "$MODEL_CACHE_DIR" -type d -exec chmod 755 {} \;
}

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    if fix_via_docker; then
        echo -e "${GREEN}✓ Permissions fixed via Docker.${NC}"
        exit 0
    fi
fi

echo -e "${YELLOW}Docker unavailable, trying sudo...${NC}"
if fix_via_sudo; then
    echo -e "${GREEN}✓ Permissions fixed via sudo.${NC}"
    exit 0
fi

echo -e "${RED}Could not fix permissions automatically.${NC}"
echo "Run manually:"
echo "  sudo chown -R 1000:1000 $MODEL_CACHE_DIR"
exit 1
