# Statistics collector health

When `COWCLOAK_USAGE_STATS=true`, Cowcloak records health metadata for the Rspamd-history collector in the same SQLite database as the usage statistics. The dashboard shows a compact collector state next to the statistics setting and exposes the raw timestamps, counts and coverage calculation in an expandable detail view.

## States

- **OK / healthy**: the latest collection succeeded and the previous successful watermark is still comfortably covered by the current Rspamd history window.
- **Low headroom**: the latest collection succeeded, but less than 25% of the returned history entries are older than the previous successful watermark.
- **Possible gap**: the previous successful watermark is no longer safely inside the current Rspamd history window. This indicates that events may have fallen out of the history window between polls.
- **Stale**: no successful collection has completed once the configured number of expected poll intervals has elapsed.
- **Failed**: the latest collection attempt failed. A failure does not overwrite the timestamp or history metadata from the last successful collection.
- **Starting**: statistics are enabled but there has not been a successful collection yet.

If statistics are disabled globally, collector health is disabled as well and this is not treated as an error.

## History headroom

The displayed **history headroom** percentage is not CPU, memory, mailcow load or generic server utilization.

For two consecutive successful polls, Cowcloak uses the newest event timestamp from the previous Rspamd history response as the previous watermark. The headroom percentage is:

```text
number of entries in the current response older than the previous watermark
-------------------------------------------------------------------------- × 100
                  total entries in the current response
```

A value of 63% therefore means that 63% of the current Rspamd history response still lies behind the point reached by the previous successful poll. Higher overlap gives the collector more room for a delayed poll before the previous watermark reaches the oldest edge of the Rspamd history window.

Cowcloak currently treats less than 25% overlap as low headroom. If the previous watermark is outside the current history window, the state becomes **possible gap** regardless of the numerical percentage.

When the Rspamd API returns exactly `COWCLOAK_USAGE_HISTORY_COUNT` entries, Cowcloak also exposes a warning that the configured limit was reached. A full response is a warning signal that the window may be tight, but it is not by itself proof that any events were missed.

## Stale threshold

`COWCLOAK_USAGE_STALE_POLLS` controls how many expected collector intervals may pass without a successful collection before the state becomes stale.

The default is:

```dotenv
COWCLOAK_USAGE_POLL_SECONDS=60
COWCLOAK_USAGE_STALE_POLLS=3
```

With those values, a successful run becomes stale after 180 seconds without another success. The threshold scales with the poll interval:

```text
stale after = COWCLOAK_USAGE_POLL_SECONDS × COWCLOAK_USAGE_STALE_POLLS
```

A failed latest attempt is reported as **failed** immediately. The stale threshold is not a delay before reporting failures.

## Persisted metadata

The collector health row stores:

- last collection attempt
- last successful collection
- failure type for the latest failed attempt
- duration of the last completed collection
- configured poll interval
- requested Rspamd history limit
- number of history entries returned
- oldest and newest event timestamps in the returned window
- previous and current successful watermarks
- number of entries older than the previous watermark
- calculated history headroom and coverage state

Collector failures do not replace the last successful timestamp or successful history-window metadata.
