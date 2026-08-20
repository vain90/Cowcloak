# Cowcloak

**Self-hosted privacy aliases for mailcow.**

Cowcloak gives mailcow users a simple self-service interface for creating and managing email aliases without exposing the mailcow administration interface.

Instead of using the same primary email address everywhere, you can give each service its own address. If one address is leaked, sold or starts receiving unwanted mail, you can identify the affected service and disable or replace only that alias. Your real mailbox address does not have to change.

> Cowcloak is under active development. Review the security and deployment notes before using it in an Internet-facing environment.

## Why use aliases?

Using one email address for every account makes it difficult to tell where unwanted mail originated and difficult to revoke one compromised address without affecting everything else.

With Cowcloak, each service can receive a separate address while all mail still arrives in the same mailbox:

```text
Amazon  -> amazon-k7@example.org --------\
Hotel   -> hotel-feder-27@example.org -----+-> alice@example.org
Shop    -> shop-wald-42@example.org -------/
```

If `hotel-feder-27@example.org` later becomes unwanted, that alias can be disabled or replaced while the other aliases and `alice@example.org` continue to work normally.

Cowcloak is not a spam filter. Its purpose is to make email addresses easier to isolate, trace and revoke.

## How it works

mailcow remains the source of truth for alias data. Cowcloak authenticates users through mailcow OAuth2 and uses the mailcow API to manage aliases on behalf of the signed-in mailbox.

A user can manage only aliases that belong exclusively to their authenticated mailbox. Cowcloak derives the alias domain and forwarding target on the server instead of accepting them from the browser.

By default, Cowcloak does not need its own user database. Optional usage statistics use a local SQLite database for counters, sender aggregates and review state; the aliases themselves remain in mailcow.

## Features

- Create aliases on the user's own mailcow domain.
- Choose between name-based aliases such as `amazon-k7`, readable random aliases such as `hafen-feder-27`, or a custom local part.
- Add a purpose or description to each alias.
- Enable and disable aliases without deleting them.
- Replace an alias while keeping the old address disabled for traceability.
- Optionally expose individual aliases as selectable SOGo sender addresses.
- Prepare offline aliases in advance and assign them later after they have been used.
- Detect catch-all delivery and warn when it weakens the one-alias-per-service model.
- Search, filter and manage aliases from one responsive dashboard.
- Review used offline aliases, unexpected senders and collector warnings in the **Action required / Handlungsbedarf** view.
- Optionally collect received/sent usage counters and sender information with configurable privacy levels.
- Review sender identities that do not match the expected use of an alias and mark them as expected or unexpected.
- Monitor the health and Rspamd-history coverage of the optional statistics collector.
- German and English interface.
- Installable web-app experience on supported desktop and mobile browsers.

## Installation

### Requirements

You need:

- a running mailcow installation that Cowcloak can reach;
- Docker with Docker Compose;
- a hostname for Cowcloak served over HTTPS;
- mailcow administrator access to create an OAuth2 client and a read/write API key.

### 1. Clone the repository

```bash
git clone https://github.com/vain90/Cowcloak.git
cd Cowcloak
cp .env.example .env
```

### 2. Create a mailcow OAuth2 client

In the mailcow administration interface, open **Configuration -> Access -> OAuth2** and create a client with this redirect URI:

```text
https://aliases.example.com/oauth/callback
```

Replace `aliases.example.com` with the hostname you will use for Cowcloak, then copy the generated client ID and client secret into `.env`.

### 3. Create a mailcow API key

Create a **read/write** API key in mailcow. Cowcloak needs it to create and manage aliases and, when usage-statistics self-service is enabled, to update the authenticated mailbox's statistics tags.

Restrict the API key to the Cowcloak server's source IP whenever your network design allows it.

### 4. Configure Cowcloak

At minimum, set these values in `.env`:

```dotenv
COWCLOAK_BASE_URL=https://aliases.example.com
COWCLOAK_SESSION_SECRET=<random-secret>
COWCLOAK_TRUSTED_HOSTS=aliases.example.com

MAILCOW_URL=https://mail.example.com
MAILCOW_API_KEY=<read-write-api-key>
MAILCOW_OAUTH_CLIENT_ID=<oauth-client-id>
MAILCOW_OAUTH_CLIENT_SECRET=<oauth-client-secret>
```

Generate a strong session secret with:

```bash
openssl rand -hex 32
```

See [.env.example](.env.example) for the complete configuration reference and all optional settings.

### 5. Start Cowcloak

```bash
docker compose pull
docker compose up -d
```

The repository Compose file publishes Cowcloak on host port `8080` by default. Put your normal HTTPS reverse proxy, such as Caddy, nginx or Traefik, in front of it and forward requests to Cowcloak.

Then open your configured `COWCLOAK_BASE_URL` and sign in through mailcow.

## Optional configuration

### Restrict access with a mailcow tag

By default, every successfully authenticated mailcow mailbox can use Cowcloak. To restrict access, configure a tag:

```dotenv
COWCLOAK_ACCESS_TAG=cowcloak
```

Assign the same tag to an allowed mailbox or domain in mailcow. Cowcloak checks access after authentication and keeps mailbox ownership isolated even when multiple users share the same domain.

### Usage statistics and sender review

Usage statistics are globally disabled by default:

```dotenv
COWCLOAK_USAGE_STATS=false
```

Enable them with:

```dotenv
COWCLOAK_USAGE_STATS=true
```

The default statistics policy uses the `cowcloak-stats` tag family and supports four privacy levels:

| Mode | Stored information |
| --- | --- |
| `off` | No new usage statistics |
| `basic` | Received and sent counters |
| `domain` | Counters plus sender-domain aggregates |
| `full` | Counters plus full sender-address aggregates |

A mailbox can override its domain's statistics mode; otherwise it inherits the domain setting. Users can change only their own statistics mode through Cowcloak.

When sender detail is enabled, Cowcloak can flag sender identities that appear unrelated to an alias and let the user review them. This is a traceability feature, not spam classification or threat intelligence.

Statistics and review state are stored in the persistent SQLite database configured by `COWCLOAK_USAGE_DB_PATH`. Alias configuration remains in mailcow.

The dashboard also reports collector health and warns when Rspamd history coverage may be too small, stale or interrupted. See [Statistics collector health](docs/statistics-collector-health.md) for the operational details.

### Offline aliases

Cowcloak can prepare aliases before they are needed. They can be copied to a phone or password manager and handed out even when Cowcloak is not currently reachable.

Once a prepared address has been used, Cowcloak can surface it in **Action required / Handlungsbedarf** so a purpose can be assigned. The address itself does not change when it is assigned.

### Install as a web app

Cowcloak includes a web-app manifest and icons. On supported platforms it can be installed from the browser, for example with **Add to Home Screen** on iPhone/iPad or **Add to Dock** in Safari on macOS.

The installed app uses the same Cowcloak server and mailcow OAuth login as the normal browser version.

## Updating

For deployments following the stable release channel:

```bash
./update.sh
```

Check whether an update is available without changing the running deployment:

```bash
./update.sh --check
```

To deliberately run the current unreleased `main` build from the `edge` image:

```bash
./update.sh --beta
```

Run `./update.sh --help` for all updater options.

The default Docker image tag is `latest`. A fixed release can be pinned with `COWCLOAK_TAG`, while `edge` follows the current `main` branch. See [.env.example](.env.example) for details.

Manual Docker Compose updates remain possible:

```bash
docker compose pull
docker compose up -d
```

## Security

Cowcloak holds a privileged mailcow read/write API key. Keep the API key and OAuth credentials on the server, use HTTPS, use secure cookies in production and restrict the API key by source IP where possible.

Alias ownership is validated server-side before Cowcloak modifies an existing alias.

See [SECURITY.md](SECURITY.md) for deployment recommendations and vulnerability reporting.

## Development

Development setup, test commands and contribution guidelines are documented in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Cowcloak is licensed under the [MIT License](LICENSE).
