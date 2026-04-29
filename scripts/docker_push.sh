#!/usr/bin/env bash
#
# Tag and push every OpenSpeakers worker + service image to Docker Hub.
#
# Usage:
#   scripts/docker_push.sh                 # push current VERSION + :latest
#   scripts/docker_push.sh 0.3.0           # override version tag
#   HUB_NAMESPACE=otheruser scripts/docker_push.sh 0.3.0
#   SKIP_LATEST=1 scripts/docker_push.sh   # only push the version tag
#   ONLY=backend,frontend scripts/docker_push.sh   # subset push
#
# Defaults pull the version from the repo's VERSION file (e.g. v0.2.0 -> 0.2.0).
# The Docker Hub namespace defaults to `davidamacey` per CLAUDE.md.
#
# The base image (`open_speakers-gpu-base`) and worker-orpheus (out of the
# v0.2.0 cloning fix scope) are skipped. Add them to IMAGES below if needed.
#
# IMPORTANT: this script does NOT build images. Run `docker compose build`
# (or `docker compose up -d --build <service>`) first to ensure the local
# tags are current before pushing.

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

VERSION="${1:-$(cat VERSION 2>/dev/null | sed 's/^v//' || echo "")}"
HUB="${HUB_NAMESPACE:-davidamacey}"
ONLY="${ONLY:-}"
SKIP_LATEST="${SKIP_LATEST:-0}"

if [[ -z "$VERSION" ]]; then
  echo "ERR: could not determine version. Pass it as the first argument or populate VERSION." >&2
  exit 2
fi

# Mapping: <local-image-name>:<hub-image-name>
# Order is smallest -> largest so progress is visible quickly.
ALL_IMAGES=(
  "open_speakers-frontend:openspeakers-frontend"
  "open_speakers-backend:openspeakers-backend"
  "open_speakers-worker-asr:openspeakers-worker-asr"
  "open_speakers-worker-fish:openspeakers-worker-fish"
  "open_speakers-worker-qwen3:openspeakers-worker-qwen3"
  "open_speakers-worker:openspeakers-worker"
  "open_speakers-worker-f5:openspeakers-worker-f5"
  "open_speakers-worker-dia:openspeakers-worker-dia"
  # Add to enable:
  # "open_speakers-worker-orpheus:openspeakers-worker-orpheus"
)

# Optional ONLY filter (comma-separated short names that match either side).
filter() {
  local entry="$1"
  if [[ -z "$ONLY" ]]; then return 0; fi
  IFS=',' read -ra wanted <<<"$ONLY"
  for w in "${wanted[@]}"; do
    if [[ "$entry" == *"$w"* ]]; then return 0; fi
  done
  return 1
}

# `docker info`'s "Username:" line is only set by an interactive `docker login`.
# Stored auth tokens in ~/.docker/config.json work for pushes without it, so we
# skip the precheck and let the first push surface a real "denied" error if
# auth is missing.

echo "Docker Hub namespace: $HUB"
echo "Version tag:          $VERSION"
echo "Also tag :latest:     $([[ "$SKIP_LATEST" == "1" ]] && echo no || echo yes)"
echo "Images to push:"
for entry in "${ALL_IMAGES[@]}"; do
  if filter "$entry"; then
    IFS=':' read -r local_name hub_name <<<"$entry"
    src="${local_name}:latest"
    if docker image inspect "$src" >/dev/null 2>&1; then
      size=$(docker image inspect "$src" --format '{{.Size}}' | numfmt --to=iec)
      echo "   ✓ $local_name ($size)"
    else
      echo "   ✗ $local_name (NOT BUILT — will skip)"
    fi
  fi
done
echo

start_total=$(date +%s)
pushed=0
skipped=0
failed=0

for entry in "${ALL_IMAGES[@]}"; do
  if ! filter "$entry"; then continue; fi
  IFS=':' read -r local_name hub_name <<<"$entry"
  src="${local_name}:latest"
  dst_v="${HUB}/${hub_name}:${VERSION}"
  dst_l="${HUB}/${hub_name}:latest"

  if ! docker image inspect "$src" >/dev/null 2>&1; then
    echo "[skip] $src not built"
    skipped=$((skipped + 1))
    continue
  fi

  echo
  echo "============================================================"
  echo "  $src ($(docker image inspect "$src" --format '{{.Size}}' | numfmt --to=iec))"
  echo "  -> $dst_v"
  [[ "$SKIP_LATEST" != "1" ]] && echo "  -> $dst_l"
  echo "============================================================"
  start=$(date +%s)

  if ! docker tag "$src" "$dst_v"; then
    echo "[fail] tag $src -> $dst_v"
    failed=$((failed + 1))
    continue
  fi
  if [[ "$SKIP_LATEST" != "1" ]] && ! docker tag "$src" "$dst_l"; then
    echo "[fail] tag $src -> $dst_l"
    failed=$((failed + 1))
    continue
  fi

  echo "[$(date +%T)] pushing $dst_v..."
  if ! docker push "$dst_v"; then
    echo "[fail] push $dst_v"
    failed=$((failed + 1))
    continue
  fi

  if [[ "$SKIP_LATEST" != "1" ]]; then
    echo "[$(date +%T)] pushing $dst_l..."
    if ! docker push "$dst_l"; then
      echo "[fail] push $dst_l"
      failed=$((failed + 1))
      continue
    fi
  fi

  end=$(date +%s)
  echo "  done in $((end - start))s"
  pushed=$((pushed + 1))
done

end_total=$(date +%s)
elapsed=$((end_total - start_total))
echo
echo "============================================================"
echo "  pushed:  $pushed"
echo "  skipped: $skipped"
echo "  failed:  $failed"
echo "  elapsed: $((elapsed / 60))m $((elapsed % 60))s"
echo "============================================================"

[[ "$failed" -eq 0 ]] || exit 4
