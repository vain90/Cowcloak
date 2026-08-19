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
- **Readable random:** `harbor-fern-42@example.org` or `moon-meadow-fox@example.org`
- **Custom:** `my-choice@example.org`

Cowcloak ships curated English and German word lists with 250 English and 244 German words. The readable-random generator usually combines two distinct words with a two-digit number and occasionally uses three distinct short words for more variety.

The readable-random generator follows the selected Cowcloak UI language: German uses the German list, all other browser languages default to English. Users can switch between DE and EN in the interface; the preference is stored in a Cowcloak cookie.

## Catch-all and main-address protection

If an active catch-all forwards unmatched addresses on the mailbox domain to the authenticated mailbox, Cowcloak shows a notice without adding the catch-all to the normal alias list.

Cowcloak also separates the primary mailbox address from normal aliases. When mailcow exposes the matching primary alias record, the user can disable or re-enable its `sender_allowed` flag from Cowcloak. Disabling it blocks normal sending as the main address while the address continues to receive mail and regular aliases remain available.

Mailcow sender ACL rules can override an alias-level sender block. Administrators who need an absolute policy should enforce that separately in mailcow/Postfix policy.

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
      +-- sender permission
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

To update later:

```bash
docker compose pull
docker compose up -d
```

Pin `COWCLOAK_TAG` in `.env` if you prefer a fixed release instead of `latest`.

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

Before editing or toggling an existing alias, Cowcloak fetches the alias from mailcow and checks that:

1. it is not a catch-all alias,
2. its domain equals the authenticated mailbox domain, and
3. its forwarding target is exactly the authenticated mailbox.

The main-address sender-protection action does not accept an alias ID from the browser. Cowcloak finds the alias whose address and only target are both the authenticated mailbox, then changes only its sender permission.

Private mailcow comments are deliberately not surfaced to mailbox users. The only private-comment value Cowcloak interprets or changes is its own offline reservation marker.

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
- [x] active / disabled status filters with counts
- [x] configurable SOGo sender visibility per alias
- [x] offline pool with 1 / 5 / 10 / 20 aliases
- [x] individual offline-alias assignment
- [x] plain-text pool export
- [x] catch-all notice for the authenticated mailbox
- [x] main-address sender protection
- [x] concise built-in help
- [x] German and English UI with browser detection and manual switching
- [x] installable web app metadata and icons
- [x] Docker image and Compose deployment
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
