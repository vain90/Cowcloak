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

For example, `alice@example.org` may create `shop-k7p4@example.org`, but not an alias on another domain and not an alias that forwards to `bob@example.org`.

## Offline alias pool

Cowcloak can pre-create 1, 5, 10 or 20 active, readable aliases. Copy the list into your phone notes and hand out an address even when Cowcloak is unreachable or you have no internet connection.

Prepared aliases are marked internally with the private comment `[cowcloak:reserved]`. Older Cowcloak aliases using `[reserved] Offline alias` are still recognized. The marker is the only private comment Cowcloak manages. When a prepared alias is assigned, Cowcloak removes that marker and stores the user-visible purpose in the public comment. The email address stays exactly the same.

Offline pool aliases are hidden from the SOGo sender chooser until they are assigned and SOGo visibility is explicitly enabled. Each prepared alias can be assigned individually from the offline-pool list.

## Alias styles

- **Name + random suffix (default):** `amazon-k7p4@example.org`
- **Readable random:** `hafen-feder-27@example.org`
- **Custom:** `my-choice@example.org`

Cowcloak ships curated English and German word lists with 250 unique words each. Every readable word is at most six characters long. The readable-random generator combines exactly two distinct words with a two-digit number, keeping generated local parts compact while remaining easy to read and dictate.

The readable-random generator follows the selected Cowcloak UI language: German uses the German list, all other browser languages default to English. Users can switch between DE and EN in the interface; the preference is stored in a Cowcloak cookie.

## Catch-all

If an active catch-all forwards unmatched addresses on the mailbox domain to the authenticated mailbox, Cowcloak shows a warning without adding the catch-all to the normal alias list.

A catch-all weakens the one-alias-per-service model because addresses that were never explicitly created can still receive mail. For clean separation and individually revocable aliases, use explicit aliases instead of catch-all delivery.

## Install as a web app

Cowcloak ships a web app manifest, standalone metadata and app icons so the normal web deployment can also be installed as an app-like experience.

- On iPhone or iPad, open Cowcloak in Safari and use **Add to Home Screen**.
- On macOS, open Cowcloak in Safari and use **Add to Dock**.
- Other browsers can use their normal install-web-app flow when supported.

The installed app still connects to the same Cowcloak server and mailcow instance. No alias data is copied into a separate local database. Because OAuth and cookie behavior can differ in standalone web apps, test the complete mailcow login and callback flow on the target Apple devices before treating a deployment as production-ready.

## Architecture

Cowcloak is intentionally stateless. Persistent alias data stays in mailcow.

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

Cowcloak needs a mailcow read/write API key to create and update aliases. Restrict the API key to the Cowcloak host's source IP in mailcow whenever your network design allows it.

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
MAILCOW_OAUTH_CLIENT_SECRET=<client-secret>
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

Before editing, toggling or applying a bulk action to an alias, Cowcloak verifies that the alias belongs exclusively to the authenticated mailbox. Bulk actions reject reserved offline aliases and the primary mailbox alias even if an arbitrary ID is submitted manually.

Private mailcow comments are deliberately not surfaced to mailbox users. The only private-comment value Cowcloak interprets or changes is its own offline reservation marker.

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
- [ ] integration test against a real mailcow test instance
- [ ] iOS and macOS standalone OAuth device test
- [ ] polished error pages and notifications
- [ ] alias replacement workflow

## Project name

`Cowcloak` is a working project name and may change before the first stable release.

## License

MIT. Cowcloak is an independent project and is not affiliated with or endorsed by the mailcow project or The Infrastructure Company GmbH.
