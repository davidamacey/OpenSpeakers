#!/usr/bin/env bash
# OpenSpeakers — one-line installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main/scripts/install.sh | bash
#
# Requirements:
#   - Docker with Compose v2 plugin
#   - NVIDIA Container Toolkit (nvidia-docker2)
#   - NVIDIA GPU with >= 4 GB VRAM (48 GB recommended for all models)
#
set -euo pipefail

REPO="https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main"
DIR="openspeakers"

echo "╔══════════════════════════════════════╗"
echo "║       OpenSpeakers Installer         ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Pre-flight checks ───────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
  echo "ERROR: Docker is not installed. Install it from https://docs.docker.com/get-docker/"
  exit 1
fi

if ! docker compose version &>/dev/null; then
  echo "ERROR: Docker Compose v2 plugin not found. Install it with: apt install docker-compose-plugin"
  exit 1
fi

if ! docker info 2>/dev/null | grep -qi nvidia && ! command -v nvidia-smi &>/dev/null; then
  echo "WARNING: NVIDIA GPU drivers or Container Toolkit not detected."
  echo "         GPU models will not work without nvidia-docker2."
  echo "         Install from: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
  echo ""
fi

# ── Download files ──────────────────────────────────────────────────────────

echo "Creating directory: $DIR"
mkdir -p "$DIR"
cd "$DIR"

echo "Downloading compose files..."
curl -fsSL -o docker-compose.prod.yml "$REPO/docker-compose.prod.yml"
curl -fsSL -o docker-compose.gpu.yml  "$REPO/docker-compose.gpu.yml"
curl -fsSL -o .env.example             "$REPO/.env.example"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

# Create data directories
mkdir -p audio_output model_cache

# ── Start services ──────────────────────────────────────────────────────────

echo ""
echo "Pulling images (this may take a while on first run)..."
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml pull

echo ""
echo "Starting OpenSpeakers..."
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d

echo ""
echo "╔══════════════════════════════════════╗"
echo "║         OpenSpeakers is running!     ║"
echo "╠══════════════════════════════════════╣"
echo "║  UI:       http://localhost:5200     ║"
echo "║  API:      http://localhost:8080     ║"
echo "║  Docs:     http://localhost:8080/docs║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Models will download automatically on first use."
echo "Logs: docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml logs -f"
echo "Stop: docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml down"
