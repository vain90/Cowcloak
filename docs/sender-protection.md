# Optional primary sender protection

Moolias can optionally prevent a signed-in mailbox user from sending mail with the
mailbox's primary address. Receiving mail at the primary address is unchanged.

This feature is disabled by default and Moolias works normally without it.

## How it works

Mailcow's normal authenticated sender policy remains in place. Moolias adds one small
PCRE sender-login map before Mailcow's normal SQL map:

```text
pcre:/opt/postfix/conf/moolias-sender-agent/blocked_sender_login.pcre
proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf
```

The Moolias policy file lives inside Mailcow's existing Postfix configuration tree:

```text
data/conf/postfix/moolias-sender-agent/blocked_sender_login.pcre
```

Postfix already receives `data/conf/postfix/` through Mailcow's normal configuration
mount, so Moolias does not add another volume to `postfix-mailcow`.

For a blocked mailbox the Moolias map returns a deliberately non-existent owner.
Mailcow's existing `reject_authenticated_sender_login_mismatch` policy then rejects
the primary address as an authenticated sender. Normal Mailcow aliases and sender
permissions continue through the SQL map.

The agent keeps private state separately:

```text
data/conf/moolias-sender-agent/state/state.json
```

The agent writes only its dedicated policy directory and its private state directory.
It never receives the complete Mailcow Postfix configuration tree.

Postfix PCRE maps are cached by an `smtpd` worker once opened. The installer therefore
adds a small Mailcow Postfix hook that sets `max_use=1` only on authenticated
submission services (`smtps`, `10465`, `submission`, `10587`, and SOGo's internal
port `588`, when those services exist). Each new client connection consequently uses
a fresh `smtpd` process and sees the current policy file. Normal SMTP delivery
services are not changed.

The one-time installation restarts `postfix-mailcow` so Postfix consumes the persistent
configuration and hook. Runtime switch changes do not reload, restart or recreate
Postfix.

## Existing sender-login PCRE rules

An administrator may already have a manual map such as:

```text
data/conf/postfix/blocked_sender_login.pcre
```

The installer does not silently take ownership of that file. If it is already active
in `smtpd_sender_login_maps`, the existing map remains separate from the Moolias map:

```text
pcre:/opt/postfix/conf/blocked_sender_login.pcre
pcre:/opt/postfix/conf/moolias-sender-agent/blocked_sender_login.pcre
proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf
```

Simple exact-address rules are shown during interactive installation. The
administrator can explicitly choose whether those exact rules should move under
Moolias management.

If they are imported:

- only the recognized exact-address lines are removed from the old file;
- the addresses are added to the Moolias agent state;
- the Moolias policy renders them with the Moolias blocked-owner marker;
- unrelated comments, custom rules and regular expressions remain untouched.

If they are not imported, the old rules stay byte-for-byte under the existing Postfix
policy. Moolias records the recognized exact addresses as externally managed and shows
the switch as read-only for those users instead of pretending that the address can be
unblocked through Moolias.

Rules that cannot be mapped safely to one exact mailbox address are never imported
automatically.

For unattended installations the prompt can be controlled explicitly:

```bash
MOOLIAS_IMPORT_EXISTING_SENDER_RULES=yes sudo bash install-mailcow-agent.sh
MOOLIAS_IMPORT_EXISTING_SENDER_RULES=no sudo bash install-mailcow-agent.sh
```

The default is `ask`. When no interactive terminal is available, existing rules are
kept external.

## Security model

The browser never sends a mailbox address when the switch is changed. It sends only
the desired boolean state. Moolias derives the mailbox address from the authenticated
server-side session, verifies the mailbox against Mailcow, validates CSRF and then
contacts the agent.

Moolias-to-agent requests are authenticated with HMAC-SHA256 using a secret that is
never exposed to the browser. Signed requests include a timestamp and nonce. The agent
rejects invalid signatures, stale requests and nonce replays.

The agent:

- runs explicitly as uid/gid `10001:10001`;
- has no SSH access;
- has no Docker socket;
- has no Mailcow API key or database credentials;
- runs without Linux capabilities, with `no-new-privileges`, and with a read-only
  root filesystem;
- has no host port published directly;
- can write only its private state directory and its dedicated Moolias Postfix policy
  directory;
- validates and escapes mailbox addresses itself; clients cannot submit PCRE rules;
- serializes state changes with a file lock;
- enforces a per-mailbox cooldown, 10 seconds by default.

The SMTP path has no runtime dependency on the agent. If the agent stops, the last
rendered policy remains on disk and existing sender protection continues to be
enforced. Only changes to the switch are temporarily unavailable.

The agent is exposed through Mailcow's existing HTTPS nginx endpoint rather than a
new host port. That location limits request bodies to 4 KiB; state-changing endpoints
still require a valid HMAC signature.

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
Moolias `edge` image. The release PR will pin both the script URL and agent image to
the corresponding stable release.

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

1. validates the Mailcow directory and Docker Compose;
2. inspects any existing sender-login PCRE configuration;
3. optionally imports recognized exact existing sender rules after explicit approval;
4. generates or reuses a 256-bit agent secret;
5. creates private state under `data/conf/moolias-sender-agent/state/`;
6. creates the dedicated Postfix policy directory under
   `data/conf/postfix/moolias-sender-agent/`;
7. creates the persistent Postfix hook for submission-worker `max_use=1`;
8. adds the ordered sender maps to `data/conf/postfix/extra.cf`;
9. adds only the `moolias-sender-agent` sidecar to the existing
   `docker-compose.override.yml`, inside a clearly marked managed block;
10. adds `/moolias-agent/` to Mailcow's existing HTTPS nginx virtual host;
11. validates the combined Compose configuration;
12. starts and hardening-checks the agent;
13. validates and reloads nginx;
14. restarts Postfix once so it consumes the persistent configuration and hook;
15. verifies the active sender-map order, submission-service `max_use=1` settings,
    and Postfix access to the Moolias policy;
16. prints the Moolias `.env` values to copy.

Existing Compose services outside the marked Moolias block are preserved. The
installer does not add a `postfix-mailcow` service override or a new Postfix volume.
If the existing YAML cannot be merged conservatively, the installer stops rather than
replacing administrator configuration.

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

## Updating the agent

While this feature is unreleased, the installer on `main` uses the `edge` image.
Re-running the installer reuses the existing secret and state, replaces only its own
marked Compose and Postfix configuration blocks, validates the result and restarts the
agent as required. Administrator configuration outside those managed blocks is left
alone.
