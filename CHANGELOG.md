# Changelog

All notable changes to Cowcloak are documented here.

## 0.1.3 - 2026-08-20

### Added

- optional usage-statistics subsystem gated by `COWCLOAK_USAGE_STATS`
- four-level mailcow statistics policy using `cowcloak-stats-off`, `cowcloak-stats`, `cowcloak-stats-domain` and `cowcloak-stats-full`
- mailbox statistics-mode overrides with domain inheritance and user self-service in the Cowcloak dashboard
- versioned SQLite storage for alias counters, optional sender aggregates, sender-review state and event deduplication, created only when statistics are enabled
- background collection of accepted incoming alias deliveries and authenticated outgoing alias sends from mailcow Rspamd history
- inline received/sent usage counters and last-used timestamps for opted-in mailboxes
- optional sender-domain or full sender-address aggregation for incoming alias mail
- sender review with manual expected/unexpected decisions and conservative automatic recognition from meaningful alias-purpose/local-part words
- `Unexpected` / `Nicht erwartet` review filter with a global count across assigned aliases
- aggregate `Review all` / `Alle prüfen` workflow for aliases that need sender review, including an automatic once-per-login prompt when review is pending
- per-alias option to disable unexpected-sender review while retaining sender statistics
- sender-detail dialogs for assigned aliases and used offline-pool aliases
- usage detection for reserved offline aliases before assignment, including accepted incoming and authenticated outgoing messages
- once-per-login assignment prompt for used offline-pool aliases
- persistent mailcow lifecycle marker for reserved aliases that have ever been used, independent of retained statistics data
- persistent Docker data volume for deployments that enable statistics

### Changed

- reserved offline aliases that have been used must be assigned before they can enter the normal alias lifecycle; they can no longer be deleted or exported/copied as unused pool addresses
- the offline pool treats both received and sent messages as usage and keeps action buttons aligned when deletion is unavailable
- `FULL -> DOMAIN` privacy downgrades collapse full sender addresses to domain aggregates while preserving allowed counts, latest timestamps and consistent manual review decisions
- downgrades to `BASIC` remove sender-detail aggregates and review decisions; switching to `OFF` additionally removes stored usage counters while the non-statistical used-reserved lifecycle marker remains in mailcow
- statistics-mode changes prevent retroactive collection of older sender detail and stale collector writes after a privacy downgrade
- mailbox statistics tags override domain defaults; conflicting mode tags on the same level pause statistics for safety without unnecessarily destroying stored state
- live search preserves the dynamically added unexpected-sender workflow
- expired or missing browser sessions on protected pages redirect to login, while API/fetch requests continue to receive a JSON `401`
- offline sender details use the same unexpected visual treatment as assigned aliases while review actions remain unavailable until assignment

### Fixed

- mailcow mailbox statistics-tag removal now uses the API's required POST method instead of returning `405 Method Not Allowed`
- `FULL -> DOMAIN` no longer loses sender-domain history
- the unexpected-sender filter no longer disappears after live-search refreshes
- offline-pool sender dialogs remain functional while the unexpected filter is active
- used offline aliases cannot regain a delete path after statistics are switched off
- used offline aliases are excluded from `pool.txt` and `Copy all` even before their persistent lifecycle marker has been written

## 0.1.2 - 2026-08-19

### Added

- optional mailcow tag based access control for individual mailboxes or complete domains

### Changed

- mailboxes without the configured access tag now return to a clear Cowcloak access-denied screen instead of showing a raw JSON error after OAuth
- active Cowcloak sessions are revalidated against the configured mailcow access tag on protected alias routes, so removing the tag revokes access on the next request
- improved the assigned-alias layout on small screens
- reduced the visual weight and size of active/SOGo status badges on mobile
- changed the mobile alias edit popover into a viewport-safe bottom sheet with its own scrolling area

## 0.1.1 - 2026-08-19

### Added

- self-updating `update.sh` for deployments following the latest stable release
- explicit `--beta` updater mode for testing the unreleased `edge` image and refreshing the updater from `main`
- automatic health verification after updates with rollback to the previously running image on failure
- `--check`, `--yes`, `--force` and version/help options for the updater
- bulk selection for assigned aliases with enable, disable, SOGo visibility and clipboard actions
- alias replacement workflow that creates a fresh address with the same purpose and SOGo visibility while keeping the previous alias disabled for traceability
- replacement format selection for name-based, readable-random or custom replacement addresses

### Changed

- `latest` is reserved for stable releases while `edge` follows `main`
- the updater selects `latest` or `edge` through `COWCLOAK_TAG` without requiring Compose edits between stable and beta updates
- name-based aliases now use a two-character ASCII letter/digit suffix with ambiguous characters excluded
- readable-random aliases now use exactly two short words of at most six characters plus a two-digit number
- both readable word lists contain 200–250 unique short words
- bulk selection now uses one tri-state select-all checkbox and a compact action dropdown below the alias list instead of separate selection and action buttons
- the alias replacement dialog has clearer spacing between the current address and replacement format selection
- the offline pool stays compact and scrolls internally instead of stretching the create-alias card
- alias edit popovers close when clicking outside them
- removed a redundant address-immutability hint from the alias creation form

## 0.1.0 - 2026-08-19

First public release.

### Highlights

- mailcow OAuth2 login without a separate Cowcloak user database
- mailbox-isolated alias management with server-side ownership checks
- name + random suffix, readable random and custom alias creation
- offline alias pool with individual assignment and deletion of unused entries
- active/disabled filtering, live search and pagination
- optional SOGo sender visibility per alias
- catch-all detection with a user-facing warning
- built-in German and English help dialog
- German and English UI with matching readable-word lists
- installable web app metadata for iPhone, iPad and macOS
- Docker Compose deployment and GHCR image publishing
- contributor, issue and pull-request templates plus CI

### Notes

- Alias data remains in mailcow; Cowcloak is stateless.
- Existing private mailcow admin comments are not exposed or modified.
- Main-mailbox sender blocking remains an administrator-side mail-server setting.
- Test the complete OAuth flow on installed Apple web apps before relying on that mode for daily use.
