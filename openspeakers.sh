#!/bin/bash
# OpenSpeakers Management CLI
# Usage: ./openspeakers.sh [command] [options]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [ -f ".env" ]; then
    set -a
    # shellcheck source=.env
    source ./.env
    set +a
fi

#######################
# COLORS & LOGGING
#######################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()    { echo -e "${CYAN}[STEP]${NC} $1"; }
log_header()  { echo ""; echo -e "${BOLD}${MAGENTA}=== $1 ===${NC}"; echo ""; }

#######################
# COMPOSE FILE HELPERS
#######################

# All workers — used for stop/purge to catch everything
ALL_COMPOSE="-f docker-compose.yml -f docker-compose.override.yml -f docker-compose.gpu.yml"

# Build compose file list based on mode + GPU availability
get_compose_files() {
    local MODE="${1:-dev}"
    local GPU="${2:-false}"
    local FILES="-f docker-compose.yml"

    if [ "$MODE" = "offline" ] && [ -f "docker-compose.offline.yml" ]; then
        FILES="$FILES -f docker-compose.offline.yml"
    elif [ -f "docker-compose.override.yml" ]; then
        FILES="$FILES -f docker-compose.override.yml"
    fi

    if [ "$GPU" = "true" ] && [ -f "docker-compose.gpu.yml" ]; then
        FILES="$FILES -f docker-compose.gpu.yml"
    fi

    echo "$FILES"
}

#######################
# HARDWARE DETECTION
#######################

check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
}

check_gpu() {
    command -v nvidia-smi > /dev/null 2>&1 && nvidia-smi > /dev/null 2>&1
}

check_nvidia_docker() {
    docker info 2>/dev/null | grep -q nvidia
}

detect_hardware() {
    log_header "Detecting Hardware"

    if check_gpu; then
        GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null | head -1)
        log_success "NVIDIA GPU: $GPU_INFO"

        if check_nvidia_docker; then
            log_success "NVIDIA Container Toolkit: available"
            export GPU_ENABLED="true"
        else
            log_warn "NVIDIA Container Toolkit not found — GPU workers will not start"
            log_info "Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
            export GPU_ENABLED="false"
        fi
    else
        log_info "No NVIDIA GPU detected — running without GPU workers"
        export GPU_ENABLED="false"
    fi
}

#######################
# DIRECTORY SETUP
#######################

create_required_dirs() {
    local DIRS=(
        "model_cache/huggingface"
        "audio_output"
        "backups"
    )
    for DIR in "${DIRS[@]}"; do
        if [ ! -d "$DIR" ]; then
            mkdir -p "$DIR"
            log_info "Created: $DIR"
        fi
    done
}

#######################
# ACCESS INFO
#######################

print_access_info() {
    echo ""
    log_header "Access URLs"
    echo -e "  Frontend UI:      ${CYAN}http://localhost:${FRONTEND_PORT:-5200}${NC}"
    echo -e "  Backend API:      ${CYAN}http://localhost:${BACKEND_PORT:-8080}/api${NC}"
    echo -e "  Swagger Docs:     ${CYAN}http://localhost:${BACKEND_PORT:-8080}/docs${NC}"
    echo -e "  ReDoc:            ${CYAN}http://localhost:${BACKEND_PORT:-8080}/redoc${NC}"
    echo -e "  OpenAI Compat:    ${CYAN}http://localhost:${BACKEND_PORT:-8080}/v1/audio/speech${NC}"
    echo ""
}

#######################
# SERVICE COMMANDS
#######################

start_services() {
    local MODE="${1:-gpu}"

    log_header "Starting OpenSpeakers ($MODE mode)"
    check_docker
    detect_hardware
    create_required_dirs

    local COMPOSE_FILES
    COMPOSE_FILES=$(get_compose_files "$MODE" "$GPU_ENABLED")
    log_info "Compose files: $COMPOSE_FILES"

    case "$MODE" in
        gpu)
            if [ "$GPU_ENABLED" != "true" ]; then
                log_warn "GPU not available — falling back to dev mode (no workers)"
                COMPOSE_FILES=$(get_compose_files "dev" "false")
            fi
            log_step "Starting all services with GPU workers..."
            # shellcheck disable=SC2086
            docker compose $COMPOSE_FILES up -d
            ;;
        dev|development)
            log_step "Starting core services (no GPU workers)..."
            # shellcheck disable=SC2086
            docker compose $COMPOSE_FILES up -d
            ;;
        offline)
            log_step "Starting in offline mode..."
            # shellcheck disable=SC2086
            docker compose $COMPOSE_FILES up -d
            ;;
        build)
            log_step "Building and starting all services..."
            COMPOSE_FILES=$(get_compose_files "gpu" "$GPU_ENABLED")
            # shellcheck disable=SC2086
            docker compose $COMPOSE_FILES up -d --build
            ;;
        *)
            log_error "Unknown mode: $MODE"
            log_info "Available modes: gpu (default), dev, offline, build"
            exit 1
            ;;
    esac

    log_step "Waiting for services to be ready..."
    sleep 5
    show_status
    print_access_info
}

stop_services() {
    log_header "Stopping OpenSpeakers"
    check_docker
    # shellcheck disable=SC2086
    docker compose $ALL_COMPOSE down 2>/dev/null || docker compose down
    log_success "All services stopped"
}

restart_services() {
    local SERVICE="${1:-}"

    log_header "Restarting OpenSpeakers"
    check_docker

    if [ -n "$SERVICE" ]; then
        log_step "Restarting $SERVICE..."
        docker compose restart "$SERVICE"
        log_success "$SERVICE restarted"
    else
        docker compose restart
        log_success "All services restarted"
    fi

    show_status
}

show_status() {
    log_header "Service Status"
    docker compose ps
}

view_logs() {
    local SERVICE="${1:-}"
    local LINES="${2:-100}"

    if [ -z "$SERVICE" ]; then
        log_info "Streaming all service logs (Ctrl+C to exit)..."
        docker compose logs -f --tail="$LINES"
    else
        log_info "Streaming logs for $SERVICE (Ctrl+C to exit)..."
        docker compose logs -f --tail="$LINES" "$SERVICE"
    fi
}

#######################
# HEALTH CHECK
#######################

health_check() {
    log_header "Health Check"
    local ALL_HEALTHY=true

    _check_service() {
        local NAME="$1"
        local CHECK_CMD="$2"
        echo -n "  $NAME: "
        if eval "$CHECK_CMD" > /dev/null 2>&1; then
            echo -e "${GREEN}healthy${NC}"
        else
            echo -e "${RED}unhealthy${NC}"
            ALL_HEALTHY=false
        fi
    }

    _check_service "Backend API" \
        "docker compose exec -T backend curl -sf http://localhost:8080/health"
    _check_service "PostgreSQL" \
        "docker compose exec -T postgres pg_isready -U ${POSTGRES_USER:-openspeakers}"
    _check_service "Redis" \
        "docker compose exec -T redis redis-cli ping"

    echo ""
    echo -e "  ${BOLD}Workers:${NC}"
    local WORKERS=(worker worker-kokoro worker-fish worker-qwen3 worker-f5 worker-orpheus worker-dia)
    for W in "${WORKERS[@]}"; do
        echo -n "  $W: "
        if docker compose ps "$W" 2>/dev/null | grep -q "Up"; then
            echo -e "${GREEN}running${NC}"
        else
            echo -e "${YELLOW}not running${NC}"
        fi
    done

    echo ""
    if [ "$ALL_HEALTHY" = true ]; then
        log_success "Core services healthy"
    else
        log_warn "One or more core services are unhealthy"
    fi
}

#######################
# WORKER COMMANDS
#######################

workers_cmd() {
    local SUBCMD="${1:-status}"
    shift || true

    case "$SUBCMD" in
        status)
            log_header "Worker Status"
            local WORKERS=(worker worker-kokoro worker-fish worker-qwen3 worker-f5 worker-orpheus worker-dia)
            for W in "${WORKERS[@]}"; do
                echo -n "  $W: "
                if docker compose ps "$W" 2>/dev/null | grep -q "Up"; then
                    echo -e "${GREEN}up${NC}"
                else
                    echo -e "${YELLOW}stopped${NC}"
                fi
            done
            echo ""
            ;;
        logs)
            local WORKER="${1:-worker}"
            log_info "Streaming $WORKER logs..."
            docker compose logs -f --tail=100 "$WORKER"
            ;;
        restart)
            local WORKER="${1:-}"
            if [ -n "$WORKER" ]; then
                log_step "Restarting $WORKER..."
                docker compose restart "$WORKER"
                log_success "$WORKER restarted"
            else
                log_step "Restarting all workers..."
                local WORKERS=(worker worker-kokoro worker-fish worker-qwen3 worker-f5 worker-orpheus worker-dia)
                for W in "${WORKERS[@]}"; do
                    if docker compose ps "$W" 2>/dev/null | grep -q "Up"; then
                        docker compose restart "$W"
                        log_success "$W restarted"
                    fi
                done
            fi
            ;;
        rebuild)
            local WORKER="${1:-}"
            if [ -n "$WORKER" ]; then
                log_step "Rebuilding and restarting $WORKER..."
                local COMPOSE_FILES
                COMPOSE_FILES=$(get_compose_files "gpu" "true")
                # shellcheck disable=SC2086
                docker compose $COMPOSE_FILES up -d --build "$WORKER"
                log_success "$WORKER rebuilt"
            else
                log_error "Please specify a worker (e.g. worker, worker-kokoro, worker-fish)"
                exit 1
            fi
            ;;
        *)
            log_error "Unknown workers subcommand: $SUBCMD"
            log_info "Available: status, logs [worker], restart [worker], rebuild <worker>"
            exit 1
            ;;
    esac
}

#######################
# DATABASE COMMANDS
#######################

db_cmd() {
    local SUBCMD="${1:-}"
    shift || true

    case "$SUBCMD" in
        migrate)
            log_header "Running DB Migrations"
            docker compose exec -T backend alembic upgrade head
            log_success "Migrations complete"
            ;;
        revision)
            local MSG="${1:-auto}"
            log_header "Creating Migration"
            docker compose exec -T backend alembic revision --autogenerate -m "$MSG"
            log_success "Migration created"
            ;;
        reset)
            log_header "Resetting Database"
            log_warn "This will delete ALL job history, voice profiles, and audio output!"
            echo -n "Type 'yes' to confirm: "
            read -r confirm
            if [ "$confirm" != "yes" ]; then
                log_info "Cancelled"
                exit 0
            fi
            docker compose stop backend worker worker-kokoro worker-fish worker-qwen3 worker-f5 worker-orpheus worker-dia 2>/dev/null || true
            docker compose rm -f postgres 2>/dev/null || true
            docker volume rm open_speakers_postgres_data 2>/dev/null || true
            docker compose up -d postgres
            sleep 5
            docker compose exec -T backend alembic upgrade head
            docker compose up -d backend
            log_success "Database reset complete"
            ;;
        backup)
            log_header "Backing Up Database"
            local TIMESTAMP
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            local FILE="backups/openspeakers_${TIMESTAMP}.sql"
            mkdir -p backups
            docker compose exec -T postgres pg_dump \
                -U "${POSTGRES_USER:-openspeakers}" \
                "${POSTGRES_DB:-openspeakers}" > "$FILE"
            log_success "Backup saved: $FILE"
            ;;
        restore)
            local FILE="$1"
            if [ -z "$FILE" ]; then
                log_error "Usage: db restore <backup-file.sql>"
                exit 1
            fi
            if [ ! -f "$FILE" ]; then
                log_error "File not found: $FILE"
                exit 1
            fi
            log_header "Restoring Database"
            docker compose exec -T postgres psql \
                -U "${POSTGRES_USER:-openspeakers}" \
                "${POSTGRES_DB:-openspeakers}" < "$FILE"
            log_success "Restored from $FILE"
            ;;
        *)
            log_error "Unknown db subcommand: $SUBCMD"
            log_info "Available: migrate, revision [msg], reset, backup, restore <file>"
            exit 1
            ;;
    esac
}

#######################
# SHELL / DEV COMMANDS
#######################

open_shell() {
    local SERVICE="${1:-backend}"

    log_info "Opening shell in $SERVICE..."
    case "$SERVICE" in
        backend|worker|worker-*)
            docker compose exec "$SERVICE" /bin/bash || docker compose exec "$SERVICE" /bin/sh
            ;;
        db|postgres)
            docker compose exec postgres psql \
                -U "${POSTGRES_USER:-openspeakers}" \
                "${POSTGRES_DB:-openspeakers}"
            ;;
        redis)
            docker compose exec redis redis-cli
            ;;
        frontend)
            docker compose exec frontend /bin/sh
            ;;
        *)
            docker compose exec "$SERVICE" /bin/bash || docker compose exec "$SERVICE" /bin/sh
            ;;
    esac
}

#######################
# BUILD COMMANDS
#######################

build_containers() {
    local SERVICE="${1:-}"

    log_header "Building Containers"
    detect_hardware

    local COMPOSE_FILES
    COMPOSE_FILES=$(get_compose_files "gpu" "$GPU_ENABLED")

    if [ -n "$SERVICE" ]; then
        log_step "Rebuilding $SERVICE..."
        # shellcheck disable=SC2086
        docker compose $COMPOSE_FILES up -d --build "$SERVICE"
        log_success "$SERVICE rebuilt and restarted"
    else
        log_step "Building all containers..."
        # shellcheck disable=SC2086
        docker compose $COMPOSE_FILES build
        log_success "Build complete — run 'start' to apply"
    fi
}

#######################
# TEST COMMAND
#######################

run_tests() {
    local TARGET="${1:-models}"

    case "$TARGET" in
        models)
            log_header "Testing All Models"
            log_info "Running scripts/test_all_models.py (may take several minutes)..."
            docker compose exec -T worker python scripts/test_all_models.py
            ;;
        backend)
            log_header "Running Backend Tests"
            docker compose exec -T backend pytest tests/ -v
            ;;
        frontend)
            log_header "Running Frontend Type Check"
            docker compose exec -T frontend npm run check
            ;;
        *)
            log_error "Unknown test target: $TARGET"
            log_info "Available: models (default), backend, frontend"
            exit 1
            ;;
    esac
}

#######################
# GPU STATUS
#######################

gpu_status() {
    log_header "GPU Status"
    if check_gpu; then
        nvidia-smi
    else
        log_warn "nvidia-smi not available"
    fi
}

#######################
# CLEAN / PURGE
#######################

clean_up() {
    log_header "Cleaning Up"
    log_step "Removing stopped containers..."
    docker container prune -f
    log_step "Removing dangling images..."
    docker image prune -f
    log_success "Cleanup complete"
}

purge_all() {
    log_header "Purge All Data"
    log_warn "This will remove ALL containers, named volumes, and built images!"
    echo -n "Type 'yes' to confirm: "
    read -r confirm
    if [ "$confirm" != "yes" ]; then
        log_info "Cancelled"
        exit 0
    fi
    # shellcheck disable=SC2086
    docker compose $ALL_COMPOSE down -v --rmi all 2>/dev/null || docker compose down -v --rmi all
    log_success "Purge complete"
}

#######################
# HELP
#######################

show_help() {
    echo ""
    echo -e "${BOLD}OpenSpeakers Management CLI${NC}"
    echo "======================================="
    echo ""
    echo "Usage: ./openspeakers.sh <command> [options]"
    echo ""
    echo -e "${CYAN}Service Commands:${NC}"
    echo "  start [mode]            Start services (modes: gpu*, dev, offline, build)"
    echo "  stop                    Stop all services"
    echo "  restart [service]       Restart all services, or a specific one"
    echo "  status                  Show container status"
    echo "  logs [service]          Stream logs (all services by default)"
    echo "  health                  Health check all services"
    echo ""
    echo -e "${CYAN}Worker Commands:${NC}"
    echo "  workers status          Show status of all GPU workers"
    echo "  workers logs [worker]   Stream logs for a worker (default: worker)"
    echo "  workers restart [w]     Restart all workers, or a specific one"
    echo "  workers rebuild <w>     Rebuild and restart a specific worker"
    echo ""
    echo -e "${CYAN}Database Commands:${NC}"
    echo "  db migrate              Apply pending Alembic migrations"
    echo "  db revision [msg]       Generate a new migration"
    echo "  db reset                Drop and recreate the database (destructive)"
    echo "  db backup               Dump database to backups/"
    echo "  db restore <file>       Restore from a backup file"
    echo ""
    echo -e "${CYAN}Build Commands:${NC}"
    echo "  build [service]         Build all images, or rebuild a single service"
    echo ""
    echo -e "${CYAN}Development Commands:${NC}"
    echo "  shell [service]         Open a shell (backend, db, redis, worker-*)"
    echo "  test [target]           Run tests (models*, backend, frontend)"
    echo "  gpu                     Show nvidia-smi GPU status"
    echo ""
    echo -e "${CYAN}Maintenance Commands:${NC}"
    echo "  clean                   Remove stopped containers and dangling images"
    echo "  purge                   Remove all containers, volumes, and images"
    echo ""
    echo -e "${CYAN}Workers:${NC}"
    echo "  worker          tts queue       Kokoro, VibeVoice 0.5B, VibeVoice 1.5B"
    echo "  worker-kokoro   tts.kokoro      Kokoro (dedicated — OpenAI-compat endpoint)"
    echo "  worker-fish     tts.fish-speech Fish Audio S2-Pro"
    echo "  worker-qwen3    tts.qwen3       Qwen3 TTS 1.7B"
    echo "  worker-f5       tts.f5-tts      F5-TTS, Chatterbox, CosyVoice 2.0"
    echo "  worker-orpheus  tts.orpheus     Orpheus 3B"
    echo "  worker-dia      tts.dia         Dia 1.6B"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  ./openspeakers.sh start              # Start with GPU workers (default)"
    echo "  ./openspeakers.sh start dev          # Start core services only (no GPU)"
    echo "  ./openspeakers.sh start build        # Build images then start"
    echo "  ./openspeakers.sh logs worker-fish   # Stream Fish Speech worker logs"
    echo "  ./openspeakers.sh workers rebuild worker-orpheus"
    echo "  ./openspeakers.sh db backup"
    echo "  ./openspeakers.sh shell backend      # Open backend shell"
    echo "  ./openspeakers.sh test models        # Smoke-test all TTS models"
    echo ""
}

#######################
# MAIN
#######################

if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

COMMAND="$1"
shift

case "$COMMAND" in
    start)     start_services "$@" ;;
    stop)      stop_services ;;
    restart)   restart_services "$@" ;;
    status)    show_status ;;
    logs)      view_logs "$@" ;;
    health)    health_check ;;
    workers)   workers_cmd "$@" ;;
    db)        db_cmd "$@" ;;
    build)     build_containers "$@" ;;
    shell)     open_shell "$@" ;;
    test)      run_tests "$@" ;;
    gpu)       gpu_status ;;
    clean)     clean_up ;;
    purge)     purge_all ;;
    help|--help|-h) show_help ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac

exit 0
