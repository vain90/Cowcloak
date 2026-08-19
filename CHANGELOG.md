# Changelog

All notable changes to Cowcloak are documented here.

## 0.1.1 - Unreleased

### Added

- self-updating `update.sh` for deployments following the latest stable release
- explicit `--beta` updater mode for testing the unreleased `edge` image and refreshing the updater from `main`
- automatic health verification after updates with rollback to the previously running image on failure
- `--check`, `--yes`, `--force` and version/help options for the updater

### Changed

- `latest` is reserved for stable releases while `edge` follows `main`
- the updater selects `latest` or `edge` through `COWCLOAK_TAG` without requiring Compose edits between stable and beta updates
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
- installable web-app metadata for iPhone, iPad and macOS
- Docker Compose deployment and GHCR image publishing
- contributor, issue and pull-request templates plus CI

### Notes

- Alias data remains in mailcow; Cowcloak is stateless.
- Existing private mailcow admin comments are not exposed or modified.
- Main-mailbox sender blocking remains an administrator-side mail-server setting.
- Test the complete OAuth flow on installed Apple web apps before relying on that mode for daily use.
