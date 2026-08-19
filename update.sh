#!/usr/bin/env bash
set -Eeuo pipefail

UPDATER_VERSION="0.1.1"
REPOSITORY="vain90/Cowcloak"
IMAGE="ghcr.io/vain90/cowcloak"
LATEST_RELEASE_URL="https://github.com/${REPOSITORY}/releases/latest"
RAW_BASE_URL="https://raw.githubusercontent.com/${REPOSITORY}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"
ORIGINAL_ARGS=("$@")

ASSUME_YES=false
BETA=false
CHECK_ONLY=false
FORCE=false
SKIP_SELF_UPDATE=false

usage() {
  cat <<'EOF'
Cowcloak updater

Usage:
  ./update.sh [options]

Options:
  -c, --check        Check whether an update is available
  -y, --yes          Update without asking for confirmation
  -f, --force        Pull and recreate even when the installed image is current
      --beta         Explicitly update from the unreleased edge channel
      --version      Show updater version
  -h, --help         Show this help

Without --beta, the updater always follows the latest stable Cowcloak release.
EOF
}

log() {
  printf '%s\n' "$*"
}

error() {
  printf 'Error: %s\n' "$*" >&2
}

die() {
  error "$*"
  exit 1
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

while (($#)); do
  case "$1" in
    -c|--check)
      CHECK_ONLY=true
      ;;
    -y|--yes)
      ASSUME_YES=true
      ;;
    -f|--force)
      FORCE=true
      ;;
    --beta|-beta)
      BETA=true
      ;;
    --skip-self-update)
      SKIP_SELF_UPDATE=true
      ;;
    --version)
      printf 'Cowcloak updater %s\n' "${UPDATER_VERSION}"
      exit 0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
  shift
done

need_command curl

get_latest_release_tag() {
  local final_url tag
  final_url="$(
    curl --proto '=https' --tlsv1.2 -fsSL \
      -o /dev/null \
      -w '%{url_effective}' \
      "${LATEST_RELEASE_URL}"
  )" || die "Could not determine the latest Cowcloak release"

  tag="${final_url##*/}"
  if [[ ! "${tag}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([+][0-9A-Za-z.-]+)?$ ]]; then
    die "Unexpected latest release tag: ${tag}"
  fi
  printf '%s\n' "${tag}"
}

if [[ "${BETA}" == true ]]; then
  CHANNEL="beta"
  TARGET_TAG="edge"
  TARGET_DISPLAY="edge"
  SELF_UPDATE_REF="main"
else
  CHANNEL="stable"
  TARGET_TAG="latest"
  LATEST_TAG="$(get_latest_release_tag)"
  LATEST_VERSION="${LATEST_TAG#v}"
  TARGET_DISPLAY="${LATEST_VERSION}"
  SELF_UPDATE_REF="${LATEST_TAG}"
fi

self_update() {
  local remote_url tmp_file backup_file source_label
  remote_url="${RAW_BASE_URL}/${SELF_UPDATE_REF}/update.sh"
  tmp_file="$(mktemp)"
  backup_file="${SCRIPT_PATH}.previous"
  source_label="${SELF_UPDATE_REF}"
  trap 'rm -f "${tmp_file}"' RETURN

  if ! curl --proto '=https' --tlsv1.2 -fsSL "${remote_url}" -o "${tmp_file}"; then
    log "Updater is not available from ${source_label}; keeping the local updater."
    return 0
  fi

  if ! bash -n "${tmp_file}"; then
    die "Downloaded updater from ${source_label} failed syntax validation"
  fi

  if cmp -s "${SCRIPT_PATH}" "${tmp_file}"; then
    return 0
  fi

  cp -a "${SCRIPT_PATH}" "${backup_file}"
  install -m 0755 "${tmp_file}" "${SCRIPT_PATH}"
  log "Updater refreshed from ${source_label}. Restarting..."
  exec "${SCRIPT_PATH}" --skip-self-update "${ORIGINAL_ARGS[@]}"
}

if [[ "${SKIP_SELF_UPDATE}" != true ]]; then
  self_update
fi

need_command docker
if ! docker compose version >/dev/null 2>&1; then
  die "Docker Compose v2 is required (docker compose)"
fi

cd "${SCRIPT_DIR}"

if [[ -n "${COWCLOAK_COMPOSE_FILE:-}" ]]; then
  COMPOSE_FILE="${COWCLOAK_COMPOSE_FILE}"
elif [[ -f "compose.local.yml" ]]; then
  COMPOSE_FILE="compose.local.yml"
elif [[ -f "compose.yml" ]]; then
  COMPOSE_FILE="compose.yml"
else
  die "No compose.local.yml or compose.yml found in ${SCRIPT_DIR}"
fi

[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
[[ -f ".env" ]] || die ".env not found in ${SCRIPT_DIR}"

compose() {
  COWCLOAK_TAG="${TARGET_TAG}" docker compose -f "${COMPOSE_FILE}" "$@"
}

RESOLVED_IMAGE="$(compose config --images 2>/dev/null | awk -v image="${IMAGE}:" 'index($0, image) == 1 { print; exit }')"
if [[ -z "${RESOLVED_IMAGE}" ]]; then
  die "The Cowcloak service does not use ${IMAGE}"
fi
if [[ "${RESOLVED_IMAGE}" != "${IMAGE}:${TARGET_TAG}" ]]; then
  die "The ${CHANNEL} channel requires Compose to resolve to ${IMAGE}:${TARGET_TAG}, but it resolves to ${RESOLVED_IMAGE}. Use image: ${IMAGE}:\${COWCLOAK_TAG:-latest} so update.sh can select latest or edge without editing Compose."
fi

current_container_id() {
  compose ps -q cowcloak 2>/dev/null | head -n 1
}

container_health() {
  local container_id="$1"
  docker inspect \
    --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
    "${container_id}" 2>/dev/null || true
}

container_version() {
  local container_id="$1"
  docker inspect \
    --format '{{index .Config.Labels "org.opencontainers.image.version"}}' \
    "${container_id}" 2>/dev/null || true
}

wait_for_healthy() {
  local container_id state
  for _ in $(seq 1 45); do
    container_id="$(current_container_id)"
    if [[ -n "${container_id}" ]]; then
      state="$(container_health "${container_id}")"
      case "${state}" in
        healthy)
          return 0
          ;;
        unhealthy|exited|dead)
          return 1
          ;;
        running)
          return 0
          ;;
      esac
    fi
    sleep 2
  done
  return 1
}

CURRENT_CONTAINER="$(current_container_id)"
CURRENT_VERSION=""
CURRENT_IMAGE_ID=""
CURRENT_IMAGE_REF=""

if [[ -n "${CURRENT_CONTAINER}" ]]; then
  CURRENT_VERSION="$(container_version "${CURRENT_CONTAINER}")"
  CURRENT_IMAGE_ID="$(docker inspect --format '{{.Image}}' "${CURRENT_CONTAINER}" 2>/dev/null || true)"
  CURRENT_IMAGE_REF="$(docker inspect --format '{{.Config.Image}}' "${CURRENT_CONTAINER}" 2>/dev/null || true)"
fi

CURRENT_DISPLAY="${CURRENT_VERSION:-${CURRENT_IMAGE_REF:-not running}}"

log "Cowcloak updater"
log ""
log "Channel:   ${CHANNEL}"
log "Installed: ${CURRENT_DISPLAY}"
log "Target:    ${TARGET_DISPLAY}"
log "Compose:   ${COMPOSE_FILE}"

UPDATE_AVAILABLE=true
TARGET_IMAGE_ID=""

if [[ "${BETA}" == true ]]; then
  log ""
  log "Checking ${IMAGE}:edge..."
  compose pull cowcloak
  TARGET_IMAGE_ID="$(docker image inspect "${IMAGE}:edge" --format '{{.Id}}' 2>/dev/null || true)"
  [[ -n "${TARGET_IMAGE_ID}" ]] || die "Could not inspect the downloaded edge image"

  if [[ -n "${CURRENT_IMAGE_ID}" && "${CURRENT_IMAGE_ID}" == "${TARGET_IMAGE_ID}" ]]; then
    UPDATE_AVAILABLE=false
  fi
else
  if [[ "${CURRENT_VERSION}" == "${LATEST_VERSION}" ]]; then
    UPDATE_AVAILABLE=false
  fi
fi

if [[ "${CHECK_ONLY}" == true ]]; then
  log ""
  if [[ "${UPDATE_AVAILABLE}" == true ]]; then
    log "Update available."
    exit 0
  fi
  log "No update available."
  exit 3
fi

if [[ "${UPDATE_AVAILABLE}" != true && "${FORCE}" != true ]]; then
  log ""
  if [[ "${BETA}" == true ]]; then
    log "Cowcloak is already on the current edge image."
  else
    log "Cowcloak is already on the latest stable release."
  fi
  exit 0
fi

if [[ "${ASSUME_YES}" != true ]]; then
  if [[ "${BETA}" == true ]]; then
    printf '\nUpdate Cowcloak to the current unreleased edge build? [y/N] '
  else
    printf '\nUpdate Cowcloak to %s? [y/N] ' "${LATEST_VERSION}"
  fi
  read -r response
  if [[ ! "${response}" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    log "Update cancelled."
    exit 0
  fi
fi

if [[ -n "${CURRENT_IMAGE_ID}" ]]; then
  docker tag "${CURRENT_IMAGE_ID}" "${IMAGE}:previous" >/dev/null
fi

if [[ "${BETA}" != true ]]; then
  log ""
  log "Pulling ${IMAGE}:latest..."
  compose pull cowcloak
fi

log "Starting Cowcloak from ${IMAGE}:${TARGET_TAG}..."
compose up -d --force-recreate --remove-orphans cowcloak

if wait_for_healthy; then
  UPDATED_CONTAINER="$(current_container_id)"
  UPDATED_VERSION="$(container_version "${UPDATED_CONTAINER}")"
  log "Health check: OK"
  log "Cowcloak ${UPDATED_VERSION:-${TARGET_DISPLAY}} is running."
  exit 0
fi

error "The updated Cowcloak container did not become healthy."
compose logs --tail=50 cowcloak >&2 || true

if [[ -n "${CURRENT_IMAGE_ID}" ]]; then
  log "Rolling back to the previously running image..."
  docker tag "${CURRENT_IMAGE_ID}" "${IMAGE}:${TARGET_TAG}"
  compose up -d --force-recreate --remove-orphans cowcloak
  if wait_for_healthy; then
    log "Rollback health check: OK"
    log "The previous Cowcloak image is running again."
    exit 1
  fi
fi

die "Update failed and automatic rollback was not successful"
