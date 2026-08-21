#!/usr/bin/env bash
set -euo pipefail

MAILCOW_DIR="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
MOOLIAS_AGENT_IMAGE="${MOOLIAS_AGENT_IMAGE:-ghcr.io/vain90/moolias:edge}"
MOOLIAS_AGENT_COOLDOWN_SECONDS="${MOOLIAS_AGENT_COOLDOWN_SECONDS:-10}"

POSTFIX_DIR="${MAILCOW_DIR}/data/conf/postfix"
POSTFIX_HOOK_DIR="${MAILCOW_DIR}/data/hooks/postfix"
POSTFIX_HOOK="${POSTFIX_HOOK_DIR}/moolias-sender-protection.sh"
NGINX_DIR="${MAILCOW_DIR}/data/conf/nginx"
AGENT_DIR="${MAILCOW_DIR}/data/conf/moolias-sender-agent"
STATE_DIR="${AGENT_DIR}/state"
POLICY_DIR="${AGENT_DIR}/postfix"
OLD_AGENT_STATE_DIR="${POSTFIX_DIR}/moolias"
EXTRA_CF="${POSTFIX_DIR}/extra.cf"
LEGACY_PCRE="${POSTFIX_DIR}/blocked_sender_login.pcre"
NGINX_CUSTOM="${NGINX_DIR}/site.moolias-sender-agent.custom"
OVERRIDE_FILE="${MAILCOW_DIR}/docker-compose.override.yml"
AGENT_ENV="${AGENT_DIR}/agent.env"

PCRE_MAP="pcre:/opt/moolias-sender-agent/blocked_sender_login.pcre"
SQL_SENDER_MAP="proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf"
BEGIN_MARKER="# BEGIN MOOLIAS SENDER PROTECTION"
END_MARKER="# END MOOLIAS SENDER PROTECTION"
OVERRIDE_MARKER="# Managed by the Moolias Mailcow Agent installer."
HOOK_MARKER="# Managed by Moolias Sender Protection."

die() {
  echo "Moolias Mailcow Agent installer: $*" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  die "run this installer as root, for example with sudo."
fi

command -v docker >/dev/null 2>&1 || die "Docker is required."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."

[[ -d "$MAILCOW_DIR" ]] || die "Mailcow directory not found: $MAILCOW_DIR"
[[ -f "${MAILCOW_DIR}/docker-compose.yml" ]] || \
  die "docker-compose.yml not found in $MAILCOW_DIR"
[[ -d "$POSTFIX_DIR" ]] || die "Mailcow Postfix configuration directory is missing."
[[ -d "$NGINX_DIR" ]] || die "Mailcow nginx configuration directory is missing."

if ! [[ "$MOOLIAS_AGENT_COOLDOWN_SECONDS" =~ ^[0-9]+$ ]] \
  || (( MOOLIAS_AGENT_COOLDOWN_SECONDS < 1 || MOOLIAS_AGENT_COOLDOWN_SECONDS > 300 )); then
  die "MOOLIAS_AGENT_COOLDOWN_SECONDS must be an integer between 1 and 300."
fi

if ! [[ "$MOOLIAS_AGENT_IMAGE" =~ ^[A-Za-z0-9._/:@-]+$ ]]; then
  die "MOOLIAS_AGENT_IMAGE contains unsupported characters."
fi

touch "$EXTRA_CF"
manage_sender_map=true
legacy_sender_map=false
if grep -Eq '^[[:space:]]*smtpd_sender_login_maps[[:space:]]*=' "$EXTRA_CF" \
  && ! grep -Fq "$BEGIN_MARKER" "$EXTRA_CF"; then
  if grep -Fq "$PCRE_MAP" "$EXTRA_CF" \
    && grep -Fq "$SQL_SENDER_MAP" "$EXTRA_CF"; then
    manage_sender_map=false
  elif grep -Fq "pcre:/opt/postfix/conf/blocked_sender_login.pcre" "$EXTRA_CF" \
    && grep -Fq "$SQL_SENDER_MAP" "$EXTRA_CF" \
    && [[ -f "$LEGACY_PCRE" ]]; then
    legacy_sender_map=true
  else
    cat >&2 <<EOF
Moolias Mailcow Agent installer:
  ${EXTRA_CF} already contains a custom smtpd_sender_login_maps override.

The installer will not replace an unknown sender policy automatically.
Back up and merge the Moolias PCRE map before Mailcow's normal SQL sender ACL,
then run the installer again.

Required order:
  ${PCRE_MAP}
  ${SQL_SENDER_MAP}
EOF
    exit 1
  fi
fi

manage_compose_override=true
if [[ -s "$OVERRIDE_FILE" ]] && ! grep -Fq "$OVERRIDE_MARKER" "$OVERRIDE_FILE"; then
  if grep -Eq '^[[:space:]]+moolias-sender-agent:[[:space:]]*$' "$OVERRIDE_FILE" \
    && grep -Fq ':/opt/moolias-sender-agent:ro' "$OVERRIDE_FILE" \
    && grep -Fq ':/state' "$OVERRIDE_FILE" \
    && grep -Fq ':/postfix-policy' "$OVERRIDE_FILE"; then
    manage_compose_override=false
  else
    cat >&2 <<EOF
Moolias Mailcow Agent installer:
  ${OVERRIDE_FILE} already exists and is not managed by Moolias.

The installer intentionally refuses to rewrite custom Docker Compose overrides.
Merge the service and Postfix read-only policy mount from
  docs/sender-protection.md
into that file, then run this installer again.
EOF
    exit 1
  fi
fi

if [[ -e "$POSTFIX_HOOK" ]] && ! grep -Fq "$HOOK_MARKER" "$POSTFIX_HOOK"; then
  die "${POSTFIX_HOOK} already exists and is not managed by Moolias."
fi

install -d -m 0755 "$AGENT_DIR"
install -d -m 0755 "$POSTFIX_HOOK_DIR"
install -d -m 0700 -o 10001 -g 10001 "$STATE_DIR"
install -d -m 0755 -o 10001 -g 10001 "$POLICY_DIR"

stamp="$(date +%Y%m%d-%H%M%S)"
backup_file() {
  local path="$1"
  if [[ -e "$path" ]]; then
    cp -a "$path" "${path}.before-moolias-agent-${stamp}.bak"
  fi
}

# Move state from early development installs out of Postfix's configuration
# tree. Only the known Moolias files are accepted for automatic cleanup.
if [[ -d "$OLD_AGENT_STATE_DIR" ]]; then
  unknown_old_file="$(
    find "$OLD_AGENT_STATE_DIR" -mindepth 1 -maxdepth 1 \
      ! -name state.json \
      ! -name blocked_sender_login.pcre \
      ! -name .lock \
      -print -quit
  )"
  [[ -z "$unknown_old_file" ]] \
    || die "refusing to remove unknown file from old Moolias state directory: $unknown_old_file"

  if [[ -f "${OLD_AGENT_STATE_DIR}/state.json" ]]; then
    [[ ! -e "${STATE_DIR}/state.json" ]] \
      || die "old and new Moolias sender state both exist; refusing an unsafe automatic merge."
    install -m 0600 -o 10001 -g 10001 \
      "${OLD_AGENT_STATE_DIR}/state.json" "${STATE_DIR}/state.json"
  fi
  backup_file "$OLD_AGENT_STATE_DIR"
  rm -rf "$OLD_AGENT_STATE_DIR"
fi

if [[ "$legacy_sender_map" == true ]]; then
  [[ ! -e "${STATE_DIR}/state.json" ]] || \
    die "legacy sender map found together with an existing agent state; refusing an unsafe automatic merge."

  legacy_addresses="$(mktemp)"
  legacy_patterns="$(mktemp)"
  trap 'rm -f "${legacy_addresses:-}" "${legacy_patterns:-}"' EXIT

  grep -Ev '^[[:space:]]*(#|$)' "$LEGACY_PCRE" > "$legacy_patterns" || true
  sed -n \
    's#^[[:space:]]*/\^\(.*\)\$/[[:space:]]\+__blocked_hidden_sender__[[:space:]]*$#\1#p' \
    "$legacy_patterns" \
    | sed 's/\\//g' \
    | tr '[:upper:]' '[:lower:]' \
    | sort -u > "$legacy_addresses"

  pattern_count="$(wc -l < "$legacy_patterns" | tr -d ' ')"
  address_count="$(wc -l < "$legacy_addresses" | tr -d ' ')"
  [[ "$pattern_count" == "$address_count" ]] || \
    die "legacy blocked_sender_login.pcre contains rules that cannot be migrated safely."

  while IFS= read -r address; do
    [[ "$address" =~ ^[A-Za-z0-9._+@-]+$ ]] \
      || die "legacy sender address contains unsupported characters: $address"
    [[ "$address" == *@* ]] || die "invalid legacy sender address: $address"
  done < "$legacy_addresses"

  backup_file "$EXTRA_CF"
  backup_file "$LEGACY_PCRE"

  {
    printf '{"blocked":['
    first=true
    while IFS= read -r address; do
      [[ -n "$address" ]] || continue
      if [[ "$first" == true ]]; then
        first=false
      else
        printf ','
      fi
      printf '"%s"' "$address"
    done < "$legacy_addresses"
    printf '],"last_changed":{},"version":1}\n'
  } > "${STATE_DIR}/state.json"
  chown 10001:10001 "${STATE_DIR}/state.json"
  chmod 0600 "${STATE_DIR}/state.json"

  echo "Migrated ${address_count} existing blocked sender address(es) into the Moolias agent state."
  rm -f "$legacy_addresses" "$legacy_patterns"
  trap - EXIT
fi

if [[ -f "$AGENT_ENV" ]]; then
  secret="$(sed -n 's/^MOOLIAS_AGENT_SECRET=//p' "$AGENT_ENV" | head -n1)"
else
  secret=""
fi

if [[ -z "$secret" ]]; then
  secret="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
fi
[[ ${#secret} -ge 32 ]] || die "could not create a sufficiently long agent secret."

umask 077
cat > "$AGENT_ENV" <<EOF
MOOLIAS_AGENT_SECRET=${secret}
MOOLIAS_AGENT_STATE_DIR=/state
MOOLIAS_AGENT_POLICY_PATH=/postfix-policy/blocked_sender_login.pcre
MOOLIAS_AGENT_COOLDOWN_SECONDS=${MOOLIAS_AGENT_COOLDOWN_SECONDS}
EOF
chmod 0600 "$AGENT_ENV"

backup_file "$POSTFIX_HOOK"
cat > "$POSTFIX_HOOK" <<EOF
#!/usr/bin/env bash
set -euo pipefail

${HOOK_MARKER}
# Postfix caches PCRE maps in smtpd workers. Limit only authenticated submission
# workers to one client connection so the next connection sees policy changes.
for service in smtps 10465 submission 10587 588; do
  if /usr/sbin/postconf -c /opt/postfix/conf -M "\${service}/inet" >/dev/null 2>&1; then
    /usr/sbin/postconf -c /opt/postfix/conf -P "\${service}/inet/max_use=1"
  fi
done
EOF
chmod 0755 "$POSTFIX_HOOK"

if [[ "$manage_compose_override" == true ]]; then
  backup_file "$OVERRIDE_FILE"
  cat > "$OVERRIDE_FILE" <<EOF
${OVERRIDE_MARKER}
services:
  postfix-mailcow:
    volumes:
      - ./data/conf/moolias-sender-agent/postfix:/opt/moolias-sender-agent:ro

  moolias-sender-agent:
    image: ${MOOLIAS_AGENT_IMAGE}
    restart: unless-stopped
    env_file:
      - ./data/conf/moolias-sender-agent/agent.env
    command:
      - uvicorn
      - moolias.mailcow_agent:create_agent_app
      - --factory
      - --host
      - 0.0.0.0
      - --port
      - "8081"
      - --proxy-headers
      - --forwarded-allow-ips
      - "*"
    volumes:
      - ./data/conf/moolias-sender-agent/state:/state
      - ./data/conf/moolias-sender-agent/postfix:/postfix-policy
    networks:
      - mailcow-network
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import urllib.request;
          urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=3)
      interval: 30s
      timeout: 5s
      start_period: 5s
      retries: 3
EOF
  chmod 0644 "$OVERRIDE_FILE"
fi

if [[ "$manage_sender_map" == true ]]; then
  tmp_extra="$(mktemp "${POSTFIX_DIR}/.extra.cf.moolias.XXXXXX")"
  if [[ "$legacy_sender_map" != true ]]; then
    backup_file "$EXTRA_CF"
  fi
  awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" -v remove_legacy="$legacy_sender_map" '
    $0 == begin { skip = 1; next }
    $0 == end { skip = 0; next }
    skip { next }
    remove_legacy == "true" && /^[[:space:]]*smtpd_sender_login_maps[[:space:]]*=/ {
      skip_sender = 1
      next
    }
    skip_sender && /^[[:space:]]+/ { next }
    skip_sender { skip_sender = 0 }
    { print }
  ' "$EXTRA_CF" > "$tmp_extra"

  {
    cat "$tmp_extra"
    if [[ -s "$tmp_extra" ]]; then
      echo
    fi
    cat <<EOF
${BEGIN_MARKER}
# Block selected primary mailbox addresses before Mailcow's normal sender ACL.
smtpd_sender_login_maps =
  ${PCRE_MAP},
  ${SQL_SENDER_MAP}
${END_MARKER}
EOF
  } > "${tmp_extra}.new"
  chmod --reference="$EXTRA_CF" "${tmp_extra}.new" 2>/dev/null || chmod 0644 "${tmp_extra}.new"
  chown --reference="$EXTRA_CF" "${tmp_extra}.new" 2>/dev/null || true
  mv "${tmp_extra}.new" "$EXTRA_CF"
  rm -f "$tmp_extra"
fi

backup_file "$NGINX_CUSTOM"
cat > "$NGINX_CUSTOM" <<'EOF'
location ^~ /moolias-agent/ {
    proxy_pass http://moolias-sender-agent:8081/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 3s;
    proxy_send_timeout 10s;
    proxy_read_timeout 10s;
}
EOF
chmod 0644 "$NGINX_CUSTOM"

cd "$MAILCOW_DIR"
docker compose config >/dev/null

if ! docker image inspect "$MOOLIAS_AGENT_IMAGE" >/dev/null 2>&1; then
  docker pull "$MOOLIAS_AGENT_IMAGE"
fi

docker compose up -d moolias-sender-agent

agent_ready=false
for _ in $(seq 1 30); do
  if docker compose exec -T moolias-sender-agent \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=2)" \
    >/dev/null 2>&1; then
    agent_ready=true
    break
  fi
  sleep 1
done
[[ "$agent_ready" == true ]] || die "agent container did not become healthy."

[[ -r "${POLICY_DIR}/blocked_sender_login.pcre" ]] \
  || die "agent did not render the Postfix policy file."

docker compose exec -T nginx-mailcow nginx -t
docker compose exec -T nginx-mailcow nginx -s reload

# extra.cf, the read-only policy mount and the Postfix hook are consumed while
# the container starts. Recreate Postfix once so Docker applies the new mount;
# normal sender toggles do not restart, recreate or reload Postfix.
docker compose up -d --force-recreate --no-deps postfix-mailcow

postfix_ready=false
active_maps=""
for _ in $(seq 1 30); do
  active_maps="$(
    docker compose exec -T postfix-mailcow \
      postconf -c /opt/postfix/conf smtpd_sender_login_maps 2>/dev/null \
      || true
  )"
  if grep -Fq "$PCRE_MAP" <<<"$active_maps" \
    && grep -Fq "$SQL_SENDER_MAP" <<<"$active_maps"; then
    postfix_ready=true
    break
  fi
  sleep 1
done

[[ "$postfix_ready" == true ]] \
  || die "Postfix did not load the Moolias sender map within 30 seconds."

for service in smtps submission 588; do
  max_use="$(
    docker compose exec -T postfix-mailcow \
      postconf -c /opt/postfix/conf -P "${service}/inet/max_use" 2>/dev/null \
      || true
  )"
  grep -Eq '=[[:space:]]*1[[:space:]]*$' <<<"$max_use" \
    || die "Postfix service ${service}/inet did not load max_use=1 from the Moolias hook."
done

docker compose exec -T postfix-mailcow \
  test -r /opt/moolias-sender-agent/blocked_sender_login.pcre \
  || die "Postfix cannot read the Moolias sender policy."

cat <<EOF

Moolias Mailcow Agent installed successfully.

Add these values to the Moolias .env file:

MOOLIAS_SENDER_PROTECTION=true
MOOLIAS_SENDER_AGENT_SECRET=${secret}

By default Moolias uses:
  \${MAILCOW_URL}/moolias-agent

Only set MOOLIAS_SENDER_AGENT_URL when the agent is reachable at a different URL.

The agent:
  - has no SSH access
  - has no Docker socket
  - has no Mailcow API key
  - keeps private state outside Postfix configuration
  - renders only a dedicated policy directory that Postfix mounts read-only
  - does not restart or reload Postfix when users change the toggle
EOF
