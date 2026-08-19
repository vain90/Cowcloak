# Cowcloak

Cowcloak is a self-hosted privacy alias manager for [mailcow](https://mailcow.email/). It gives mailbox users a fast way to create, label, disable and prepare email aliases while keeping mailcow as the source of truth.

> Early development. The project is not yet ready for production use.

## Core rules

Cowcloak deliberately keeps its authorization model small:

- Authentication is delegated to mailcow via OAuth2.
- There is no separate Cowcloak user database or password store.
- A mailbox may create aliases only on its own domain.
- Every alias created by a mailbox points only to that mailbox.
- Multiple mailboxes on the same mailcow domain remain isolated from each other.
- Cowcloak only manages an existing alias when its target is exactly the authenticated mailbox.
- Alias addresses are immutable in Cowcloak. Renaming a purpose never renames the address.
- User-visible alias purposes are stored in mailcow's public comment.
- Private mailcow admin comments are not exposed or edited by Cowcloak.
- SOGo visibility can be enabled per alias when the alias should appear as a selectable sender.

For example, `alice@example.org` may create `shop-k7@example.org`, but not an alias on another domain and not an alias that forwards to `bob@example.org`.

## Offline alias pool

Cowcloak can pre-create 1, 5, 10 or 20 active, readable aliases. Copy the list into your phone notes and hand out an address even when Cowcloak is unreachable or you have no internet connection.

Prepared aliases are marked internally with the private comment `[cowcloak:reserved]`. Older Cowcloak aliases using `[reserved] Offline alias` are still recognized. The marker is the only private comment Cowcloak manages. When a prepared alias is assigned, Cowcloak removes that marker and stores the user-visible purpose in the public comment. The email address stays exactly the same.

Offline pool aliases are hidden from the SOGo sender chooser until they are assigned and SOGo visibility is explicitly enabled. Each prepared alias can be assigned individually from the offline-pool list.

## Alias styles

- **Name + random suffix (default):** `amazon-k7@example.org`
- **Readable random:** `hafen-feder-27@example.org`
- **Custom:** `my-choice@example.org`

Named aliases use a two-character ASCII suffix chosen from lowercase letters and digits. Visually ambiguous characters such as `0`, `1`, `i`, `l` and `o` are excluded so addresses stay short and easier to dictate or spell.

Cowcloak ships curated English and German word lists with 250 unique words each. Every readable word is at most six characters long. The readable-random generator combines exactly two distinct words with a two-digit number, keeping generated local parts compact while remaining easy to read and dictate.

The readable-random generator follows the selected Cowcloak UI language: German uses the German list, all other browser languages default to English. Users can switch between DE and EN in the interface; the preference is stored in a Cowcloak cookie.

## Replacing an alias

When an assigned alias is no longer trustworthy, Cowcloak can replace it without deleting its history. The replacement action creates a fresh name-based alias using the same purpose and SOGo visibility, then disables the previous alias. The old address remains stored in mailcow so it can still be traced back to the service that used it and is never silently recycled.

The new address is shown immediately after replacement with a copy action. If the new alias is created but mailcow cannot disable the previous alias, Cowcloak reports the partial result and shows the new address so both aliases can be checked explicitly.

## Catch-all

If an active catch-all forwards unmatched addresses on the mailbox domain to the authenticated mailbox, Cowcloak shows a warning without adding the catch-all to the normal alias list.

A catch-all weakens the one-alias-per-service model because addresses that were never explicitly created can still receive mail. For clean separation and individually revocable aliases, use explicit aliases instead of catch-all delivery.

## Optional usage statistics

Usage statistics are disabled globally by default. With the default `COWCLOAK_USAGE_STATS=false`, Cowcloak does not create or open a statistics database, does not start the statistics collector and does not request Rspamd history for statistics.

To enable the subsystem:

```dotenv
COWCLOAK_USAGE_STATS=true
COWCLOAK_USAGE_TAG=cowcloak-stats
```

`COWCLOAK_USAGE_TAG` is the base tag for a four-level statistics policy:

- `cowcloak-stats-off`: no new statistics for the mailbox.
- `cowcloak-stats`: received/sent counters only.
- `cowcloak-stats-domain`: counters plus sender-domain aggregation for incoming mail.
- `cowcloak-stats-full`: counters plus full sender-address aggregation for incoming mail.

A statistics tag on the mailbox overrides the domain setting. When the mailbox has no statistics tag, the domain setting is inherited. Multiple statistics-mode tags on the same level are treated as a configuration conflict and statistics are disabled for that mailbox until the conflict is resolved.

Mailbox users can select their own statistics mode in Cowcloak. Cowcloak changes only the authenticated mailbox's statistics-tag family and preserves all unrelated mailcow tags. In particular, the normal Cowcloak access tag remains administrator-controlled and is never granted by the statistics selector.

Accepted incoming deliveries and accepted authenticated sends using a Cowcloak alias are counted. Primary mailbox addresses, shared aliases, catch-all aliases, unused offline aliases and rejected/soft-rejected messages are excluded.

Sender detail is opt-in and starts only when the effective mode is `domain` or `full`. Changing the effective statistics mode clears the existing sender-detail aggregates and manual sender-review decisions for that mailbox before starting the new mode. This prevents full sender addresses from surviving a privacy downgrade and prevents a more detailed mode from retroactively importing older Rspamd history.

For `domain` and `full`, Cowcloak shows every sender identity it has recorded for an alias rather than hiding low-frequency senders. Users can mark a sender as expected or explicitly unexpected. Cowcloak also performs a deliberately conservative automatic check: meaningful words from the alias local part and purpose may mark a sender as expected when the same word appears as a sender-domain label. For example, an alias named `amazon-k7` with purpose `Amazon` can automatically recognize `amazon.de` or `mail.amazon.de`. Generic words such as `shop`, `mail`, `info` and `newsletter` are ignored for automatic approval.

When enabled, counters, sender aggregates, manual sender-review decisions and deduplication hashes are stored in a versioned SQLite database at `/data/cowcloak-stats.sqlite3` by default. Raw subjects and message IDs are not persisted. In `domain` mode no full sender address is stored. In `full` mode the sender address and its domain are stored as aggregate keys.

The collector necessarily reads the global Rspamd history response from mailcow before filtering it in memory, but only currently eligible Cowcloak alias data is written to the local database. If a deployment requires sender metadata for non-opted-in mailboxes to never reach the Cowcloak process at all, use a server-side filtered exporter instead of the built-in Rspamd-history collector.

The repository Compose file mounts a persistent `cowcloak-data` volume at `/data`. The volume may exist while statistics are disabled; in that case no statistics database is created. Future schema changes are handled by Cowcloak's internal database schema version rather than by manual SQL steps.

## Install as a web app

Cowcloak ships a web app manifest, standalone metadata and app icons so the normal web deployment can also be installed as an app-like experience.

- On iPhone or iPad, open Cowcloak in Safari and use **Add to Home Screen**.
- On macOS, open Cowcloak in Safari and use **Add to Dock**.
- Other browsers can use their normal install-web-app flow when supported.

The installed app still connects to the same Cowcloak server and mailcow instance. Alias data remains in mailcow; optional usage statistics, when enabled on the server, remain in Cowcloak's server-side SQLite database. Because OAuth and cookie behavior can differ in standalone web apps, test the complete mailcow login and callback flow on the target Apple devices before treating a deployment as production-ready.

## Architecture

Cowcloak is stateless by default. Persistent alias data stays in mailcow. Optional usage statistics add only a local server-side SQLite store for aggregate counters, sender aggregates, review state and deduplication state.

```text
Browser / installed web app
      |
      | OAuth2 login
      v
   Cowcloak  -------- mailcow OAuth2
      |
      | X-API-Key
      v
   mailcow API
      |
      +-- alias address
      +-- target mailbox
      +-- public comment / purpose
      +-- private Cowcloak reservation marker
      +-- active state
      +-- SOGo visibility
      +-- mailbox/domain tags
      +-- Rspamd history (stats only, filtered in memory)

Optional when usage statistics are enabled:

   Cowcloak
      |
      v
   SQLite /data/cowcloak-stats.sqlite3
      +-- aggregate alias counters
      +-- optional sender domain/address aggregates
      +-- manual expected/unexpected sender decisions
      +-- hashed event deduplication keys
```

The mailcow API key is never sent to the browser.

## mailcow setup

### 1. Create an OAuth2 client

In mailcow, log in as administrator and open **Configuration → Access → OAuth2**. Add a client with this redirect URI:

```text
https://aliases.example.com/oauth/callback
```

Save the generated client ID and client secret.

Cowcloak uses mailcow's OAuth2 endpoints:

```text
/oauth/authorize
/oauth/token
/oauth/profile
```

### 2. Create a read/write API key

Cowcloak needs a mailcow read/write API key to create and update aliases and, when statistics self-service is enabled globally, to update the authenticated mailbox's statistics tags. Restrict the API key to the Cowcloak host's source IP in mailcow whenever your network design allows it.

### 3. Configure Cowcloak

```bash
cp .env.example .env
```

Set at least:

```dotenv
COWCLOAK_BASE_URL=https://aliases.example.com
COWCLOAK_SESSION_SECRET=<random-secret>
COWCLOAK_TRUSTED_HOSTS=aliases.example.com
MAILCOW_URL=https://mail.example.com
MAILCOW_API_KEY=<read-write-api-key>
MAILCOW_OAUTH_CLIENT_ID=<client-id>
MAILCOW_OAUTH_CLIENT_SECRET=<oauth-secret>
```

Generate a session secret with:

```bash
openssl rand -hex 32
```

### 4. Start with Docker Compose

```bash
docker compose pull
docker compose up -d
```

By default Cowcloak listens on host port `8080`. Put your normal HTTPS reverse proxy in front of it.

The container tags intentionally separate releases from development builds:

- `latest` points to the latest stable release.
- SemVer tags such as `0.1.0`, `0.1` and `0` are created for stable releases.
- `edge` follows the current `main` branch and may contain unreleased changes.

Pin `COWCLOAK_TAG` in `.env` if you prefer a fixed release instead of `latest`.

## Updating

Starting with Cowcloak 0.1.1, deployments using the parameterized image below can use the bundled updater for both stable and explicit beta updates:

```yaml
image: ghcr.io/vain90/cowcloak:${COWCLOAK_TAG:-latest}
```

A normal update always follows the latest stable release:

```bash
./update.sh
```

The stable updater refreshes itself from the immutable latest release, pulls `ghcr.io/vain90/cowcloak:latest`, recreates the Cowcloak container, waits for the health check and rolls back to the previously running image when the new container does not become healthy.

To deliberately test the current unreleased `main` build on the same deployment, opt in explicitly:

```bash
./update.sh --beta
```

Beta mode refreshes the updater from `main` and uses `ghcr.io/vain90/cowcloak:edge`. It never changes the Compose file or `.env`; the updater supplies `COWCLOAK_TAG=edge` only for that invocation. Running `./update.sh` without `--beta` switches the deployment back to the stable `latest` channel when necessary.

Useful options:

```bash
./update.sh --check
./update.sh --beta --check
./update.sh --yes
./update.sh --beta --yes
./update.sh --force
./update.sh --version
```

`--check` exits with `0` when an update is available and `3` when the selected channel is current. In beta mode the check pulls the current `edge` image metadata/layers if needed so the running image can be compared with the newest `edge` build without restarting it.

The updater automatically uses `compose.local.yml` when it exists, otherwise `compose.yml`. Set `COWCLOAK_COMPOSE_FILE` when a deployment uses a different file name. The Compose image must remain parameterized as `ghcr.io/vain90/cowcloak:${COWCLOAK_TAG:-latest}` so the updater can select stable or beta without rewriting local deployment configuration. Fixed-version deployments remain intentionally manual.

To add `update.sh` to an existing installation after 0.1.1 has been released:

```bash
LATEST_URL=$(curl -fsSL -o /dev/null -w '%{url_effective}' \
  https://github.com/vain90/Cowcloak/releases/latest)
LATEST_TAG=${LATEST_URL##*/}
curl -fsSLo update.sh \
  "https://raw.githubusercontent.com/vain90/Cowcloak/${LATEST_TAG}/update.sh"
chmod +x update.sh
```

Manual updates remain possible:

```bash
docker compose pull
docker compose up -d
```

## Development

Python 3.12 or newer is required. See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest -q
```

## Security model

The read/write mailcow API key is highly privileged. Cowcloak therefore enforces ownership server-side on every modifying request. Neither the alias domain nor the forwarding target is accepted from the browser. Both are derived from the mailbox authenticated by mailcow.

Before editing, toggling, replacing or applying a bulk action to an alias, Cowcloak verifies that the alias belongs exclusively to the authenticated mailbox. Bulk actions reject reserved offline aliases and the primary mailbox alias even if an arbitrary ID is submitted manually. Replacement also rejects reserved aliases and the primary mailbox alias server-side.

Private mailcow comments are deliberately not surfaced to mailbox users. The only private-comment value Cowcloak interprets or changes is its own offline reservation marker.

When optional usage statistics are enabled, the effective statistics mode is resolved from the authenticated mailbox and its domain. The mailbox can change only its own statistics-tag family through Cowcloak; all unrelated tags are preserved. Sender review actions are accepted only for sender rows already stored for an alias owned by the authenticated mailbox.

The collector reads recent Rspamd history using the same server-side mailcow API connection, filters it against currently eligible mailbox aliases and stores only data allowed by the effective statistics mode. Mode changes reset sender-detail state, and sender writes are checked against the current persisted mode so a collector iteration that started before a privacy downgrade cannot reinsert more detailed sender data afterward.

Main-mailbox sender blocking remains an administrator-side mail-server setting and is not controlled by Cowcloak.

See [SECURITY.md](SECURITY.md) for deployment and vulnerability-reporting guidance.

## Status

The current milestone is the first testable MVP:

- [x] mailcow OAuth2 login
- [x] mailbox-derived alias domain
- [x] mailbox-isolated alias listing
- [x] readable, named and custom aliases
- [x] user-visible purposes stored as mailcow public comments
- [x] private mailcow admin comments kept private
- [x] immutable alias addresses when purposes change
- [x] enable / disable aliases
- [x] bulk selection with enable / disable, SOGo visibility and clipboard actions
- [x] active / disabled status filters with counts
- [x] configurable SOGo sender visibility per alias
- [x] offline pool with 1 / 5 / 10 / 20 aliases
- [x] individual offline-alias assignment
- [x] plain-text pool export
- [x] catch-all notice for the authenticated mailbox
- [x] concise built-in help
- [x] German and English UI with browser detection and manual switching
- [x] installable web app metadata and icons
- [x] Docker image and Compose deployment
- [x] stable release updater with self-update, explicit beta channel and health rollback
- [x] CI and multi-architecture GHCR builds
- [x] contribution and issue templates
- [x] alias replacement workflow
- [x] optional usage-statistics backend foundation
- [x] incoming and outgoing alias usage classification from verified mailcow events
- [x] inline usage-statistics UI
- [x] mailbox/domain statistics modes with mailbox self-service overrides
- [x] optional sender-domain and full-address aggregation
- [x] manual and automatic expected-sender review
- [ ] integration test against a real mailcow test instance
- [ ] iOS and macOS standalone OAuth device test
- [ ] polished error pages and notifications

## Project name

`Cowcloak` is a working project name and may change before the first stable release.

## License

MIT. Cowcloak is an independent project and is not affiliated with or endorsed by the mailcow project or The Infrastructure Company GmbH.
