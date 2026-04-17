#!/bin/bash
# OpenSpeakers Setup Script
#
# Handles everything needed for a fresh installation:
#   - Pre-flight checks (Docker, GPU, NVIDIA Container Toolkit)
#   - Enables Docker to start on boot
#   - Downloads compose files from GitHub
#   - Generates .env with secure random secrets
#   - Creates model_cache and audio_output directories with correct permissions
#   - Pulls images and starts services
#
# Usage (one-liner from a new machine):
#   curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main/setup-openspeakers.sh | bash
#
# Or clone and run locally:
#   git clone https://github.com/davidamacey/OpenSpeakers.git
#   cd OpenSpeakers
#   bash setup-openspeakers.sh

set -e

REPO="https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main"
DIR="${OPENSPEAKERS_DIR:-openspeakers}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠  $1${NC}"; }
print_error()   { echo -e "${RED}✗ $1${NC}"; }
print_info()    { echo -e "${CYAN}→ $1${NC}"; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║       OpenSpeakers Setup             ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Pre-flight: Docker ───────────────────────────────────────────────────────

print_info "Checking Docker..."

if ! command -v docker &>/dev/null; then
    print_error "Docker is not installed."
    echo "  Install from: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    print_error "Docker Compose v2 plugin not found."
    echo "  Install with: sudo apt install docker-compose-plugin"
    exit 1
fi

# Ensure Docker daemon is running
if ! docker info &>/dev/null 2>&1; then
    print_warning "Docker daemon is not running — attempting to start..."
    if command -v systemctl &>/dev/null; then
        sudo systemctl start docker
        sleep 3
    fi
    if ! docker info &>/dev/null 2>&1; then
        print_error "Could not start Docker. Run: sudo systemctl start docker"
        exit 1
    fi
fi
print_success "Docker $(docker --version | awk '{print $3}' | tr -d ',')"

# Enable Docker to start on boot (idempotent)
if command -v systemctl &>/dev/null; then
    if ! systemctl is-enabled docker &>/dev/null 2>&1; then
        print_info "Enabling Docker to start on boot..."
        sudo systemctl enable docker
        sudo systemctl enable docker.socket 2>/dev/null || true
        print_success "Docker enabled on boot"
    else
        print_success "Docker already enabled on boot"
    fi
fi

# Add current user to docker group if not already a member
if ! groups | grep -qw docker; then
    print_warning "Your user ($USER) is not in the 'docker' group."
    echo "  Run: sudo usermod -aG docker \$USER   (then log out and back in)"
fi

# ── Pre-flight: NVIDIA ───────────────────────────────────────────────────────

print_info "Checking NVIDIA GPU..."

if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null 2>&1; then
    gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    print_success "GPU detected: $gpu_name"
else
    print_warning "NVIDIA GPU not detected — GPU models will not work."
    echo "  Install NVIDIA Container Toolkit:"
    echo "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
fi

# ── Create install directory ─────────────────────────────────────────────────

print_info "Creating directory: $DIR"
mkdir -p "$DIR"
cd "$DIR"

# ── Download compose files ───────────────────────────────────────────────────

print_info "Downloading compose and config files..."
curl -fsSL -o docker-compose.prod.yml "$REPO/docker-compose.prod.yml"
curl -fsSL -o docker-compose.gpu.yml  "$REPO/docker-compose.gpu.yml"
curl -fsSL -o .env.example            "$REPO/.env.example"
# Also download helper scripts
mkdir -p scripts
curl -fsSL -o scripts/fix-model-permissions.sh "$REPO/scripts/fix-model-permissions.sh"
chmod +x scripts/fix-model-permissions.sh
print_success "Files downloaded"

# ── Generate .env ────────────────────────────────────────────────────────────

if [[ -f .env ]]; then
    print_warning ".env already exists — skipping generation (delete it to regenerate)"
else
    print_info "Generating .env with secure random secrets..."
    cp .env.example .env

    # Replace placeholder secret key with a real random one
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null \
                 || openssl rand -base64 48 | tr -d '\n/')
    sed -i "s|change_this_to_a_random_secret_key_in_production|${SECRET_KEY}|" .env

    print_success ".env created with random SECRET_KEY"
    echo ""
    echo "  Edit .env to configure:"
    echo "    GPU_DEVICE_ID   — which GPU to use (default: 0)"
    echo "    HF_TOKEN        — required for Orpheus 3B (gated model)"
    echo "    FRONTEND_PORT   — UI port (default: 5200)"
    echo "    BACKEND_PORT    — API port (default: 8080)"
fi

# ── Create data directories with correct permissions ─────────────────────────

print_info "Creating data directories..."
mkdir -p audio_output model_cache/huggingface model_cache/torch

# The main worker and kokoro worker run as UID 1000 (appuser) inside the
# container. The host cache dirs must be owned by UID 1000 to allow model
# downloads and reads.
if [[ "$(id -u)" -eq 0 ]]; then
    chown -R 1000:1000 model_cache
    chmod -R 755 model_cache
    print_success "model_cache ownership set to UID 1000 (running as root)"
else
    # Try chown to 1000 directly — succeeds if current user is UID 1000
    if chown -R 1000:1000 model_cache 2>/dev/null; then
        chmod -R 755 model_cache
        print_success "model_cache ownership set to UID 1000"
    else
        # Fall back to Docker (no sudo needed, runs as root inside container)
        if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
            print_info "Fixing model_cache ownership via Docker..."
            docker run --rm -v "$(pwd)/model_cache:/mc" busybox:latest \
                sh -c "chown -R 1000:1000 /mc && find /mc -type d -exec chmod 755 {} \;"
            print_success "model_cache ownership fixed via Docker"
        else
            # Last resort: world-writable
            chmod -R a+rwx model_cache
            print_warning "model_cache set to world-writable (Docker unavailable for chown)"
            echo "  For stricter permissions run: sudo chown -R 1000:1000 model_cache"
        fi
    fi
fi

# Verify write access
if [[ -w model_cache/huggingface ]]; then
    print_success "model_cache/huggingface is writable"
else
    print_warning "model_cache/huggingface may not be writable — run: ./scripts/fix-model-permissions.sh"
fi

# ── Pull images ──────────────────────────────────────────────────────────────

echo ""
print_info "Pulling Docker images from Docker Hub (this may take a while on first run)..."
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml pull

# ── Start services ───────────────────────────────────────────────────────────

echo ""
print_info "Starting OpenSpeakers..."
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d

echo ""
echo "╔══════════════════════════════════════╗"
echo "║    OpenSpeakers is running!          ║"
echo "╠══════════════════════════════════════╣"
echo "║  UI:    http://localhost:5200        ║"
echo "║  API:   http://localhost:8080        ║"
echo "║  Docs:  http://localhost:8080/docs   ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Models download automatically on first use."
echo ""
echo "Useful commands:"
echo "  Logs:    docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml logs -f"
echo "  Stop:    docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml down"
echo "  Update:  docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml pull && \\"
echo "           docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d"
echo ""
echo "If you see permission errors on model downloads, run:"
echo "  ./scripts/fix-model-permissions.sh"
