#!/bin/bash
# OpenSpeakers Setup Script
#
# Handles everything needed for a fresh installation:
#   - Network connectivity check
#   - Pre-flight checks (Docker, GPU, NVIDIA Container Toolkit)
#   - Enables Docker to start on boot
#   - Downloads compose files from GitHub (with retry)
#   - Generates .env with secure random secrets
#   - Creates model_cache and audio_output directories with correct permissions
#   - Validates Docker Compose configuration
#   - Pulls images and starts services
#   - Waits for backend health check
#
# Usage (one-liner from a new machine):
#   curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main/setup-openspeakers.sh | bash
#
# Or clone and run locally:
#   git clone https://github.com/davidamacey/OpenSpeakers.git
#   cd OpenSpeakers
#   bash setup-openspeakers.sh
#
# Environment variables:
#   OPENSPEAKERS_DIR        Install directory (default: ./openspeakers)
#   OPENSPEAKERS_UNATTENDED When non-empty, skip all interactive prompts
#   OPENSPEAKERS_BRANCH     Git branch to download files from (default: main)

set -e

REPO_BRANCH="${OPENSPEAKERS_BRANCH:-main}"
REPO="https://raw.githubusercontent.com/davidamacey/OpenSpeakers/${REPO_BRANCH}"
DIR="${OPENSPEAKERS_DIR:-openspeakers}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠  $1${NC}"; }
print_error()   { echo -e "${RED}✗ $1${NC}"; }
print_info()    { echo -e "${CYAN}→ $1${NC}"; }
print_header()  {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

is_unattended() { [[ -n "${OPENSPEAKERS_UNATTENDED:-}" ]]; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║       OpenSpeakers Setup             ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Network check ─────────────────────────────────────────────────────────────

print_header "Checking network connectivity"

check_network() {
    local hosts=("github.com" "hub.docker.com" "huggingface.co")
    local ok=true
    for host in "${hosts[@]}"; do
        if curl -fsSL --max-time 5 "https://$host" &>/dev/null; then
            print_success "Reachable: $host"
        else
            print_warning "Cannot reach: $host"
            ok=false
        fi
    done
    if [[ "$ok" == false ]]; then
        print_error "Some hosts are unreachable. Setup may fail. Check your internet connection."
        if ! is_unattended; then
            read -r -p "Continue anyway? (y/N): " ans </dev/tty
            [[ "$ans" =~ ^[Yy] ]] || exit 1
        fi
    fi
}

check_network

# ── Pre-flight: Docker ─────────────────────────────────────────────────────────

print_header "Checking Docker"

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

# ── Pre-flight: NVIDIA ─────────────────────────────────────────────────────────

print_header "Checking hardware"

GPU_NAME=""
if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null 2>&1; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    GPU_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
    print_success "GPU detected: $GPU_NAME (${GPU_VRAM}MB VRAM)"
else
    print_warning "NVIDIA GPU not detected — GPU-based models will not work."
    echo "  Install NVIDIA Container Toolkit:"
    echo "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
fi

# ── Create install directory ───────────────────────────────────────────────────

print_header "Creating install directory"

print_info "Directory: $(pwd)/$DIR"
mkdir -p "$DIR"
cd "$DIR"

# ── Download files (with retry) ────────────────────────────────────────────────

print_header "Downloading compose and config files"

download_file() {
    local url="$1"
    local dest="$2"
    local max_retries=3
    local retry=0

    while [[ $retry -lt $max_retries ]]; do
        if curl -fsSL -o "$dest" "$url"; then
            # Basic validity check — file must not be empty
            if [[ -s "$dest" ]]; then
                return 0
            fi
            print_warning "Downloaded file appears empty, retrying..."
        else
            print_warning "Download attempt $((retry + 1)) failed for $dest"
        fi
        retry=$((retry + 1))
        if [[ $retry -lt $max_retries ]]; then
            echo "  Retrying in 5 seconds..."
            sleep 5
        fi
    done
    print_error "Failed to download $dest after $max_retries attempts"
    return 1
}

download_file "$REPO/docker-compose.prod.yml" docker-compose.prod.yml
download_file "$REPO/docker-compose.gpu.yml"  docker-compose.gpu.yml
download_file "$REPO/.env.example"            .env.example
mkdir -p scripts
download_file "$REPO/scripts/fix-model-permissions.sh" scripts/fix-model-permissions.sh
chmod +x scripts/fix-model-permissions.sh
print_success "Files downloaded"

# ── Generate .env ──────────────────────────────────────────────────────────────

print_header "Configuring environment"

if [[ -f .env ]]; then
    print_warning ".env already exists — skipping generation (delete it to regenerate)"
else
    print_info "Generating .env with secure random secrets..."
    cp .env.example .env

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

# ── Create data directories ────────────────────────────────────────────────────

print_header "Creating data directories"

mkdir -p audio_output model_cache/huggingface model_cache/torch

# Workers run as UID 1000 (appuser); host dirs must be owned by UID 1000
if [[ "$(id -u)" -eq 0 ]]; then
    chown -R 1000:1000 model_cache
    chmod -R 755 model_cache
    print_success "model_cache ownership set to UID 1000 (running as root)"
else
    if chown -R 1000:1000 model_cache 2>/dev/null; then
        chmod -R 755 model_cache
        print_success "model_cache ownership set to UID 1000"
    elif command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        print_info "Fixing model_cache ownership via Docker..."
        docker run --rm -v "$(pwd)/model_cache:/mc" busybox:latest \
            sh -c "chown -R 1000:1000 /mc && find /mc -type d -exec chmod 755 {} \;"
        print_success "model_cache ownership fixed via Docker"
    else
        chmod -R a+rwx model_cache
        print_warning "model_cache set to world-writable (Docker unavailable for chown)"
        echo "  For stricter permissions run: sudo chown -R 1000:1000 model_cache"
    fi
fi

if [[ -w model_cache/huggingface ]]; then
    print_success "model_cache/huggingface is writable"
else
    print_warning "model_cache/huggingface may not be writable — run: ./scripts/fix-model-permissions.sh"
fi

# ── Validate Docker Compose config ─────────────────────────────────────────────

print_header "Validating configuration"

compose_error=$(docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml config 2>&1)
exit_code=$?

if [[ $exit_code -eq 0 ]]; then
    print_success "Docker Compose configuration valid"
else
    print_error "Docker Compose configuration validation failed"
    echo "$compose_error" | head -20
    echo ""
    if ! is_unattended; then
        read -r -p "Continue anyway? (y/N): " ans </dev/tty
        [[ "$ans" =~ ^[Yy] ]] || exit 1
    fi
fi

# ── Pull images ────────────────────────────────────────────────────────────────

print_header "Pulling Docker images"

print_info "Pulling images from Docker Hub (this may take a while on first run)..."
if docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml pull; then
    print_success "Images pulled"
else
    print_warning "Failed to pull some images — will use cached versions if available"
fi

# ── Start services ─────────────────────────────────────────────────────────────

print_header "Starting OpenSpeakers"

docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d

# ── Wait for backend health ────────────────────────────────────────────────────

BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-5200}"

print_info "Waiting for backend to become ready..."
max_wait=120
elapsed=0
while [[ $elapsed -lt $max_wait ]]; do
    if curl -fsSL --max-time 3 "http://localhost:${BACKEND_PORT}/health" &>/dev/null; then
        print_success "Backend is ready"
        break
    fi
    sleep 5
    elapsed=$((elapsed + 5))
done

if [[ $elapsed -ge $max_wait ]]; then
    print_warning "Backend did not respond within ${max_wait}s — it may still be starting"
    echo "  Check logs: docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml logs -f backend"
fi

# ── Summary ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║    🎉  OpenSpeakers is running!                  ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                                  ║${NC}"
echo -e "${GREEN}║  📋 Hardware                                     ║${NC}"
if [[ -n "$GPU_NAME" ]]; then
echo -e "${GREEN}║    GPU: ${GPU_NAME:0:40}  ║${NC}"
else
echo -e "${GREEN}║    GPU: Not detected (CPU-only mode)             ║${NC}"
fi
echo -e "${GREEN}║                                                  ║${NC}"
echo -e "${GREEN}║  🌐 Service URLs                                 ║${NC}"
echo -e "${GREEN}║    UI:   http://localhost:${FRONTEND_PORT}              ║${NC}"
echo -e "${GREEN}║    API:  http://localhost:${BACKEND_PORT}               ║${NC}"
echo -e "${GREEN}║    Docs: http://localhost:${BACKEND_PORT}/docs          ║${NC}"
echo -e "${GREEN}║                                                  ║${NC}"
echo -e "${GREEN}║  📁 Install directory: $(pwd)${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
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
