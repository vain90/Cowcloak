#!/usr/bin/env bash
set -euo pipefail

MAILCOW_DIR="${MAILCOW_DIR:-/tmp/mailcow-dockerized}"
REPORT_DIR="${REPORT_DIR:-/tmp/mailcow-feasibility}"
MAILCOW_HOSTNAME="${MAILCOW_HOSTNAME:-mail.mailcow-ci.test}"
MAILCOW_HTTP_PORT="${MAILCOW_HTTP_PORT:-8080}"
MAILCOW_API_KEY="${MAILCOW_API_KEY:-cowcloak-ci-feasibility}"

mkdir -p "$REPORT_DIR"

record_resources() {
  local target="$1"
  {
    echo "=== Compose status ==="
    docker compose ps --all
    echo
    echo "=== Container resource snapshot ==="
    docker stats --no-stream
    echo
    echo "=== Filesystems ==="
    df -h
    echo
    echo "=== Docker disk usage ==="
    docker system df
  } | tee "$target"
}

cleanup() {
  local exit_code=$?
  set +e

  if [[ -d "$MAILCOW_DIR" ]]; then
    cd "$MAILCOW_DIR" || true
    record_resources "$REPORT_DIR/resources-final.txt"

    if (( exit_code != 0 )); then
      {
        echo "=== Unbound inspect ==="
        docker inspect mailcowdockerized-unbound-mailcow-1 --format '{{json .State.Health}}'
        echo
        echo "=== Unbound logs ==="
        docker compose logs --no-color --tail=200 unbound-mailcow
      } | tee "$REPORT_DIR/unbound-failure.txt"
      docker compose logs --no-color --tail=300 > "$REPORT_DIR/mailcow.log" 2>&1
    fi

    docker compose down -v --remove-orphans
  fi

  exit "$exit_code"
}
trap cleanup EXIT

{
  echo "=== Runner ==="
  uname -a
  echo
  echo "=== CPU ==="
  nproc
  lscpu
  echo
  echo "=== Memory ==="
  free -h
  echo
  echo "=== Filesystems ==="
  df -h
  echo
  echo "=== Docker ==="
  docker version
  echo
  docker compose version
} | tee "$REPORT_DIR/runner-before.txt"

git clone --depth 1 --branch master \
  https://github.com/mailcow/mailcow-dockerized.git \
  "$MAILCOW_DIR"
git -C "$MAILCOW_DIR" rev-parse HEAD | tee "$REPORT_DIR/mailcow-commit.txt"

cd "$MAILCOW_DIR"
if [[ ! -L .env ]]; then
  ln -s mailcow.conf .env
fi

export MAILCOW_HOSTNAME
export MAILCOW_TZ=Etc/UTC
export SKIP_CLAMD=y
export FORCE=y
./generate_config.sh --dev

set_conf() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" mailcow.conf; then
    sed -i "s|^${key}=.*|${key}=${value}|" mailcow.conf
  else
    printf '%s=%s\n' "$key" "$value" >> mailcow.conf
  fi
}

# Keep the disposable instance local to the runner and skip services that are
# irrelevant to Cowcloak's API-contract tests.
set_conf HTTP_PORT "$MAILCOW_HTTP_PORT"
set_conf HTTP_BIND 127.0.0.1
set_conf HTTPS_PORT 8443
set_conf HTTPS_BIND 127.0.0.1
set_conf HTTP_REDIRECT n
set_conf SKIP_LETS_ENCRYPT y
set_conf AUTODISCOVER_SAN n
set_conf SKIP_CLAMD y
set_conf SKIP_OLEFY y
set_conf SKIP_FTS y
set_conf USE_WATCHDOG n

# Mailcow's normal Unbound health probe checks public ICMP and DNS egress.
# GitHub-hosted runners do not provide those paths reliably, while the local
# Mailcow API contract under test does not depend on that external probe.
set_conf SKIP_UNBOUND_HEALTHCHECK y

set_conf API_KEY "$MAILCOW_API_KEY"
set_conf API_ALLOW_FROM "127.0.0.1,172.22.1.0/24"

echo "127.0.0.1 $MAILCOW_HOSTNAME" | sudo tee -a /etc/hosts

{
  echo "MAILCOW_HOSTNAME=$(grep '^MAILCOW_HOSTNAME=' mailcow.conf | cut -d= -f2-)"
  echo "HTTP_BIND=$(grep '^HTTP_BIND=' mailcow.conf | cut -d= -f2-)"
  echo "HTTP_PORT=$(grep '^HTTP_PORT=' mailcow.conf | cut -d= -f2-)"
  echo "SKIP_CLAMD=$(grep '^SKIP_CLAMD=' mailcow.conf | cut -d= -f2-)"
  echo "SKIP_OLEFY=$(grep '^SKIP_OLEFY=' mailcow.conf | cut -d= -f2-)"
  echo "SKIP_FTS=$(grep '^SKIP_FTS=' mailcow.conf | cut -d= -f2-)"
  echo "SKIP_UNBOUND_HEALTHCHECK=$(grep '^SKIP_UNBOUND_HEALTHCHECK=' mailcow.conf | cut -d= -f2-)"
  echo "ENABLE_IPV6=$(grep '^ENABLE_IPV6=' mailcow.conf | cut -d= -f2-)"
  echo "API_ALLOW_FROM=$(grep '^API_ALLOW_FROM=' mailcow.conf | cut -d= -f2-)"
} | tee "$REPORT_DIR/mailcow-config-summary.txt"

docker compose pull 2>&1 | tee "$REPORT_DIR/docker-pull.txt"
{
  echo "=== Filesystems after image pull ==="
  df -h
  echo
  echo "=== Docker disk usage after image pull ==="
  docker system df
} | tee "$REPORT_DIR/resources-after-pull.txt"

docker compose up -d
docker compose ps --all | tee "$REPORT_DIR/compose-after-start.txt"

web_url="http://${MAILCOW_HOSTNAME}:${MAILCOW_HTTP_PORT}/"
web_ready=false
for attempt in $(seq 1 120); do
  if curl --noproxy '*' --fail --silent --show-error \
    --resolve "${MAILCOW_HOSTNAME}:${MAILCOW_HTTP_PORT}:127.0.0.1" \
    "$web_url" >/dev/null; then
    echo "Mailcow web UI became reachable after $((attempt * 5)) seconds."
    web_ready=true
    break
  fi
  sleep 5
done

if [[ "$web_ready" != true ]]; then
  echo "Mailcow web UI did not become reachable within 10 minutes." >&2
  exit 1
fi

api_url="http://${MAILCOW_HOSTNAME}:${MAILCOW_HTTP_PORT}/api/v1/get/domain/all"
api_response="$REPORT_DIR/api-domains.json"
api_ready=false

# The UI may answer slightly before php-fpm has finished the first-start DB
# initialization that persists API credentials, so retry the actual API contract.
for attempt in $(seq 1 24); do
  http_status="$(curl --noproxy '*' --silent --show-error \
    --resolve "${MAILCOW_HOSTNAME}:${MAILCOW_HTTP_PORT}:127.0.0.1" \
    -H "X-API-Key: ${MAILCOW_API_KEY}" \
    -H "Accept: application/json" \
    -o "$api_response" \
    -w '%{http_code}' \
    "$api_url" || true)"

  if [[ "$http_status" == "200" ]] && jq -e 'type == "array"' "$api_response" >/dev/null 2>&1; then
    echo "Mailcow API returned a JSON array successfully on attempt $attempt."
    api_ready=true
    break
  fi

  printf 'Mailcow API attempt %d returned HTTP %s: ' "$attempt" "${http_status:-curl-error}"
  head -c 400 "$api_response" 2>/dev/null || true
  echo
  sleep 5
done

if [[ "$api_ready" != true ]]; then
  echo "Mailcow API did not become ready within 2 minutes." >&2
  exit 1
fi

record_resources "$REPORT_DIR/resources-success.txt"
echo "Mailcow feasibility probe passed."
