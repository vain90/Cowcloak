# Optional primary sender protection

Moolias can optionally prevent a signed-in mailbox user from sending mail with the
mailbox's primary address. Receiving mail at the primary address is unchanged.

This feature is disabled by default and Moolias works normally without it.

## How it works

Mailcow's normal authenticated sender policy is kept intact. The optional Moolias
Mailcow Agent maintains one PCRE sender-login map before Mailcow's normal SQL map:

```text
pcre:/opt/moolias-sender-agent/blocked_sender_login.pcre
proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf
```

For a blocked mailbox the PCRE map returns a deliberately non-existent owner.
Mailcow's existing `reject_authenticated_sender_login_mismatch` policy then rejects
the primary address as an authenticated sender.

Normal Mailcow aliases and sender permissions continue through the SQL map.

The agent keeps its private state separate from Postfix configuration:

```text
data/conf/moolias-sender-agent/state/state.json
data/conf/moolias-sender-agent/postfix/blocked_sender_login.pcre
```

The agent writes the policy atomically. Postfix mounts only the policy directory and
mounts it read-only at `/opt/moolias-sender-agent/`; Postfix cannot modify the agent's
state or policy files.

Postfix PCRE maps are cached by an `smtpd` worker once opened. The installer therefore
adds a small Mailcow Postfix hook that sets `max_use=1` only on authenticated
submission services (`smtps`, `10465`, `submission`, `10587`, and SOGo's internal
port `588`, when those services exist). Each new client connection consequently uses
a fresh `smtpd` process and sees the current policy file. Normal SMTP delivery
services are not changed.

The one-time installation recreates `postfix-mailcow` so Docker applies the new
read-only policy mount and Postfix consumes the persistent configuration and hook.
After installation, changing the switch does **not** reload, restart, or recreate
Postfix.

The disposable-Mailcow integration test verifies the complete allow -> block ->
allow sequence on normal authenticated submission port 587 and on Mailcow's SOGo
submission service on port 588. It also verifies that a normal sender-enabled alias
continues to work while the primary address is blocked.

## Security model

The browser never sends a mailbox address when the switch is changed. It sends only
the desired boolean state. Moolias derives the mailbox address from the authenticated
server-side session, verifies the mailbox against Mailcow, validates CSRF and then
contacts the agent.

Moolias-to-agent requests are authenticated with HMAC-SHA256 using a secret that is
never exposed to the browser. Signed requests include a timestamp and nonce. The
agent rejects invalid signatures, stale requests and nonce replays.

The agent:

- has no SSH access
- has no Docker socket
- has no Mailcow API key or database credentials
- runs without Linux capabilities and with a read-only root filesystem
- keeps private state in its dedicated `state/` directory
- can render only its dedicated `postfix/` policy directory
- has no writable mount into Mailcow's Postfix configuration tree
- validates and escapes mailbox addresses itself; clients cannot submit PCRE rules
- serializes state changes with a file lock
- enforces a per-mailbox cooldown (10 seconds by default)

Postfix receives the rendered policy directory read-only. The SMTP path has no
runtime dependency on the agent: if the agent stops, the last rendered policy remains
on disk and existing sender protection continues to be enforced. Only changes to the
switch are temporarily unavailable.

Moolias also applies a per-mailbox cooldown before contacting the agent. The agent
remains authoritative, so direct or concurrent requests cannot bypass the cooldown.
Repeated requests for the already active state are idempotent and do not rewrite the
policy.

## Standard installation

Requirements are the same Docker and Docker Compose installation already required by
Mailcow. No Python installation, SSH access from Moolias, database access, additional
public port, TLS certificate or new DNS record is required.

Run this command on the Mailcow host:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/scripts/install-mailcow-agent.sh \
  | sudo bash
```

While this feature is still under `Unreleased`, the installer from `main` uses the
Moolias `edge` image. The release PR will pin both the script URL and the agent image
to the stable release, so normal release users keep a version-matched agent.

The installer assumes Mailcow is located at `/opt/mailcow-dockerized`. For another
location:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/vain90/Moolias/main/scripts/install-mailcow-agent.sh \
  | sudo MAILCOW_DIR=/path/to/mailcow bash
```

For administrators who prefer to inspect the script before running it:

```bash
curl -fsSLO \
  https://raw.githubusercontent.com/vain90/Moolias/main/scripts/install-mailcow-agent.sh
less install-mailcow-agent.sh
sudo bash install-mailcow-agent.sh
```

The installer:

1. validates the Mailcow directory and Docker Compose
2. generates or reuses a 256-bit agent secret
3. creates separate private-state and rendered-policy directories under
   `data/conf/moolias-sender-agent/`
4. creates the persistent Postfix hook for the submission-worker `max_use=1` setting
5. adds the Moolias sender map to `data/conf/postfix/extra.cf`
6. adds a read-only policy mount to `postfix-mailcow`
7. adds the unprivileged agent as a Mailcow Compose sidecar
8. adds `/moolias-agent/` to Mailcow's existing HTTPS nginx virtual host
9. validates the combined Compose configuration
10. starts and health-checks the agent and verifies that it rendered the policy
11. validates and reloads nginx
12. recreates `postfix-mailcow` once so Docker applies the new mount and Postfix
    consumes the persistent configuration and hook
13. verifies the active sender-map order, submission-service `max_use=1` settings,
    and Postfix access to the read-only policy
14. prints the Moolias `.env` values to copy

All Mailcow changes are under Mailcow's persistent configuration paths, hook path, or
local Compose override and therefore survive normal Mailcow updates.

## Enable the feature in Moolias

Copy the secret printed by the installer to the Moolias `.env` file:

```dotenv
MOOLIAS_SENDER_PROTECTION=true
MOOLIAS_SENDER_AGENT_SECRET=replace-with-the-secret-printed-by-the-installer
```

Moolias uses this URL automatically:

```text
<MAILCOW_URL>/moolias-agent
```

Only set a custom URL when the agent is exposed elsewhere:

```dotenv
MOOLIAS_SENDER_AGENT_URL=https://mail.example.org/moolias-agent
```

The default per-mailbox cooldown is 10 seconds:

```dotenv
MOOLIAS_SENDER_PROTECTION_COOLDOWN_SECONDS=10
```

Restart the Moolias application after changing its `.env` file.

When the feature is disabled:

```dotenv
MOOLIAS_SENDER_PROTECTION=false
```

Moolias does not contact the agent and the normal application remains fully
functional.

When the feature is enabled but the agent is missing, unreachable or authenticated
with the wrong secret, Moolias continues to work and reports sender protection as
unavailable. Existing rules on the Mailcow host remain in effect.

### Migration from the earlier manual PCRE setup

The installer recognizes the earlier manual Moolias sender-block setup that used:

```text
data/conf/postfix/blocked_sender_login.pcre
pcre:/opt/postfix/conf/blocked_sender_login.pcre
__blocked_hidden_sender__
```

When that exact layout is present, the installer imports all simple exact mailbox
rules into the agent state before replacing the sender-map override. The addresses
therefore remain blocked across the migration. `extra.cf` and the old PCRE file are
backed up with a timestamp before anything is changed.

The installer also migrates the known state files from early unreleased agent builds
that used `data/conf/postfix/moolias/`. Unknown files in that directory cause the
installer to stop instead of deleting or guessing.

If the legacy PCRE file contains rules that cannot be interpreted safely as exact
mailbox addresses, the installer stops instead of guessing.

## Existing custom Mailcow overrides

The installer deliberately refuses to overwrite an existing custom
`smtpd_sender_login_maps` policy, unrelated Postfix hook, or unrelated
`docker-compose.override.yml`.

This is a safety feature. Existing customizations must be reviewed rather than
silently replaced.

### Existing Postfix sender policy

The required Moolias map must appear before Mailcow's normal sender ACL:

```text
smtpd_sender_login_maps =
  pcre:/opt/moolias-sender-agent/blocked_sender_login.pcre,
  proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf
```

After manually merging this ordering into `data/conf/postfix/extra.cf`, rerun the
installer. It detects the required map and leaves the custom policy untouched.

The Postfix hook is still required so runtime changes are visible on the next
submission connection. If the Moolias hook path is already occupied by an unrelated
file, the installer stops rather than replacing it.

### Existing Docker Compose override

Merge both the Postfix read-only mount and the agent service into the existing
`docker-compose.override.yml`:

```yaml
services:
  postfix-mailcow:
    volumes:
      - ./data/conf/moolias-sender-agent/postfix:/opt/moolias-sender-agent:ro

  moolias-sender-agent:
    image: ghcr.io/vain90/moolias:edge
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
```

Then rerun the installer. When it finds the expected `moolias-sender-agent` service,
state/policy mounts and Postfix read-only mount, it leaves the custom Compose override
untouched and completes the remaining setup.

## Updating the agent

While this feature is unreleased, the installer on `main` uses the `edge` image.
The release PR will pin the installer and documentation to the corresponding stable
Moolias release. Re-running the installer reuses the existing secret and state.
