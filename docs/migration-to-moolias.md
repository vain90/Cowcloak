# Migrating to Moolias

Moolias is the new name of Cowcloak. The rename is intentionally comprehensive because the project is still pre-release.

Existing installations need a one-time migration before starting the renamed service:

1. Rename every `COWCLOAK_*` variable in `.env` to `MOOLIAS_*`.
2. Change custom Compose service/image references from `cowcloak` to `moolias` and use `ghcr.io/vain90/moolias`.
3. Preserve the existing `/data` contents. If you use the repository's named Compose volume, copy its contents to the new Moolias volume before removing the old volume. If you use a bind mount, keep the same host directory.
4. Rename `cowcloak-stats.sqlite3` to `moolias-stats.sqlite3` when using the old default statistics path, or set `MOOLIAS_USAGE_DB_PATH` to the migrated file location.
5. Rename custom access/statistics tags from the old defaults to the new `moolias` / `moolias-stats*` names when those tags are in use.
6. Update reverse-proxy and automation references if they explicitly use the old service, container, repository or image name.

Already-created offline aliases using the old private reservation markers remain recognized during the transition so they are not accidentally exposed as normal assigned aliases. New markers use the Moolias namespace.

After the migration, the application uses the `moolias` package, `MOOLIAS_*` configuration variables and Moolias runtime names exclusively. The old reservation-marker recognition exists only to preserve aliases that were created before the rename.
