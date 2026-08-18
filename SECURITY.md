# Security policy

Cowcloak holds a mailcow read/write API key and must therefore be treated as a privileged service.

Please do not open public issues for vulnerabilities that could expose mailboxes, aliases, OAuth credentials, API keys, or session data. Use GitHub's private vulnerability reporting when it is enabled for this repository.

## Deployment recommendations

- Serve Cowcloak only over HTTPS.
- Restrict the mailcow API key to the Cowcloak server's source IP where possible.
- Keep `COWCLOAK_COOKIE_SECURE=true` in production.
- Use a randomly generated session secret of at least 32 bytes.
- Do not expose `.env` files, API keys, or OAuth client secrets to the browser.
- Put Cowcloak and mailcow behind maintained reverse proxies and keep both updated.
