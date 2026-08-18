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
- Alias addresses are immutable in Cowcloak. Renaming a description never renames the address.
- Descriptions are stored as the alias private comment in mailcow.

For example, `alice@example.org` may create `shop-k7p4@example.org`, but not an alias on another domain and not an alias that forwards to `bob@example.org`.

## Offline alias pool

Cowcloak can pre-create 1, 5, 10 or 20 active, readable aliases. Copy the list into your phone notes and hand out an address even when Cowcloak is unreachable or you have no internet connection.

Prepared aliases are marked in mailcow with the private comment `[reserved] Offline alias`. After using one, assign a description in Cowcloak. Only the comment changes; the email address stays exactly the same.

## Alias styles

- **Readable random:** `harbor-fern-42@example.org`
- **Name + random:** `amazon-k7p4@example.org`
- **Custom:** `my-choice@example.org`

Readable random aliases use a curated English or German word list configured with `COWCLOAK_WORDLIST`.

## Architecture

Cowcloak is intentionally stateless. Persistent alias data stays in mailcow.

```text
Browser / PWA
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
      +-- private comment / description
      +-- active state
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

Python 3.12 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest
```

## Security model

The read/write mailcow API key is highly privileged. Cowcloak therefore enforces ownership server-side on every modifying request. Neither the alias domain nor the forwarding target is accepted from the browser. Both are derived from the mailbox authenticated by mailcow.

Before editing or toggling an existing alias, Cowcloak fetches the alias from mailcow and checks that:

1. it is not a catch-all alias,
2. its domain equals the authenticated mailbox domain, and
3. its forwarding target is exactly the authenticated mailbox.

See [SECURITY.md](SECURITY.md) for deployment guidance.

## Status

The current milestone is the first testable MVP:

- [x] mailcow OAuth2 login
- [x] mailbox-derived alias domain
- [x] mailbox-isolated alias listing
- [x] readable, named and custom aliases
- [x] mailcow private comments as descriptions
- [x] immutable alias addresses when descriptions change
- [x] enable / disable aliases
- [x] offline pool with 1 / 5 / 10 / 20 aliases
- [x] plain-text pool export
- [x] Docker image and Compose deployment
- [x] CI and multi-architecture GHCR builds
- [ ] integration test against a real mailcow test instance
- [ ] polished error pages and notifications
- [ ] alias replacement workflow
- [ ] localization

## Project name

`Cowcloak` is a working project name and may change before the first stable release.

## License

MIT. Cowcloak is an independent project and is not affiliated with or endorsed by the mailcow project or The Infrastructure Company GmbH.
