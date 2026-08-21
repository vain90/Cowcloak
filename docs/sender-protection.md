# Optional primary sender protection

Moolias can optionally prevent a signed-in mailbox user from sending mail with the
mailbox's primary address. Receiving mail at the primary address is unchanged.

This feature is disabled by default and Moolias works normally without it.

## How it works

Mailcow's normal authenticated sender policy is kept intact. The optional Moolias
Mailcow Agent maintains one PCRE sender-login map before Mailcow's normal SQL map:

```text
pcre:/opt/postfix/conf/moolias/blocked_sender_login.pcre
proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf
```

For a blocked mailbox the PCRE map returns a deliberately non-existent owner.
Mailcow's existing `reject_authenticated_sender_login_mismatch` policy then rejects
the primary address as an authenticated sender.

Normal Mailcow aliases and sender permissions continue through the SQL map.

The map file is rewritten atomically. New Postfix `smtpd` processes pick up changes
without a Postfix reload or container restart. Only the one-time installation needs
to restart `postfix-mailcow` so the persistent `extra.cf` override becomes active.

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
- can write only `data/conf/postfix/moolias/`
- validates and escapes mailbox addresses itself; clients cannot submit PCRE rules
- serializes state changes with a file lock
- enforces a per-mailbox cooldown (10 seconds by default)

Moolias also applies a per-mailbox cooldown before contacting the agent. The agent
remains authoritative, so direct or concurrent requests cannot bypass the cooldown.

## Standard installation

Requirements are the same Docker and Docker Compose installation already required by
Mailcow. No Python installation, SSH access from Moolias, database access or new DNS
record is required.

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
3. creates `data/conf/postfix/moolias/`
4. adds the Moolias sender map to `data/conf/postfix/extra.cf`
5. adds the agent as a Mailcow Compose sidecar
6. adds `/moolias-agent/` to Mailcow's existing HTTPS nginx virtual host
7. validates the combined Compose configuration
8. starts and health-checks the agent
9. validates and reloads nginx
10. restarts `postfix-mailcow` once to activate the persistent sender map
11. verifies the active Postfix sender-map order
12. prints the Moolias `.env` values to copy

All Mailcow changes are under Mailcow's persistent configuration paths or the local
Compose override and therefore survive normal Mailcow updates.

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

If the legacy file contains rules that cannot be interpreted safely as exact mailbox
addresses, the installer stops instead of guessing.

## Existing custom Mailcow overrides

The installer deliberately refuses to overwrite an existing custom
`smtpd_sender_login_maps` policy or an unrelated `docker-compose.override.yml`.

This is a safety feature. Existing customizations must be reviewed rather than
silently replaced.

### Existing Postfix sender policy

The required Moolias map must appear before Mailcow's normal sender ACL:

```text
smtpd_sender_login_maps =
  pcre:/opt/postfix/conf/moolias/blocked_sender_login.pcre,
  proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf
```

After manually merging this ordering into `data/conf/postfix/extra.cf`, rerun the
installer. It detects the required map and leaves the custom policy untouched.

### Existing Docker Compose override

Merge this service into the existing `docker-compose.override.yml`:

```yaml
services:
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
      - ./data/conf/postfix/moolias:/state
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

Then rerun the installer. When it finds the `moolias-sender-agent` service, it leaves
the custom Compose override untouched and completes the remaining setup.

## Updating the agent

While this feature is unreleased, the installer on `main` uses the `edge` image.
The release PR will pin the installer and documentation to the corresponding stable
Moolias release. Re-running the installer reuses the existing secret and state.
