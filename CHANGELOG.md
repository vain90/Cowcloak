# Changelog

All notable changes to Cowcloak are documented here.

## 0.1.0 - 2026-08-19

First public release.

### Highlights

- mailcow OAuth2 login without a separate Cowcloak user database
- mailbox-isolated alias management with server-side ownership checks
- name + random suffix, readable random and custom alias creation
- offline alias pool with individual assignment and deletion of unused entries
- active/disabled filtering, live search and pagination
- optional SOGo sender visibility per alias
- catch-all notice for mailboxes receiving unmatched addresses
- optional sending block for the main mailbox address
- concise built-in help in German and English
- German and English UI with matching readable-word lists
- installable web-app metadata for iPhone, iPad and macOS
- Docker Compose deployment and GHCR image publishing
- contributor, issue and pull-request templates plus CI

### Notes

- Alias data remains in mailcow; Cowcloak is stateless.
- Existing private mailcow admin comments are not exposed or modified.
- Mailcow sender ACL rules can override an alias-level sender block.
- Test the complete OAuth flow on installed Apple web apps before relying on that mode for daily use.
