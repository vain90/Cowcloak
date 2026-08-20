# Statistics collector health

When `COWCLOAK_USAGE_STATS=true`, Cowcloak records health metadata for the Rspamd-history collector in the same SQLite database as the usage statistics. The dashboard shows a compact collector state next to the statistics setting and exposes the raw timestamps, counts and coverage calculation in an expandable detail view.

## States

- **OK / healthy**: the latest collection succeeded and the previous successful watermark is still comfortably covered by the current Rspamd history window.
- **Low headroom**: the latest collection succeeded, but less than 10% of the loaded history entries are older than the previous successful watermark.
- **Possible gap**: the previous successful watermark is no longer safely inside the current Rspamd history window. This indicates that events may have fallen out of the history window between polls.
- **Stale**: no successful collection has completed once the configured number of expected poll intervals has elapsed.
- **Failed**: the latest collection attempt failed. A failure does not overwrite the timestamp or history metadata from the last successful collection.
- **Starting**: statistics are enabled, but two successful history windows are not available for comparison yet.

If statistics are disabled globally, collector health is disabled as well and this is not treated as an error.

## Adaptive history loading

`COWCLOAK_USAGE_HISTORY_COUNT` is the maximum history window Cowcloak may load, not the amount fetched on every poll.

Cowcloak probes progressively larger candidate windows:

```text
10 -> 25 -> 50 -> 100 -> 250 -> 500 -> configured maximum
```

For each candidate below the configured maximum, Cowcloak requests only the single Rspamd history entry at the position needed to guarantee the target 10% overlap. Rspamd/mailcow range positions are zero-based. For example, a 10-entry candidate probes position `9`, while a 25-entry candidate probes position `22` because three older entries are required to exceed 10%.

If the probe shows that the previous watermark is still too close to the old edge, Cowcloak moves to the next candidate without downloading the full batch. Once a probe is old enough, Cowcloak downloads that candidate window and verifies the actual overlap again. This second check protects against new history entries arriving between the probe and the full request.

If the real batch still has less than 10% overlap, Cowcloak continues with the next size. If no smaller candidate is sufficient, it loads the configured maximum directly.

When there is no previous successful watermark yet, the statistics tracking start time is used only to choose an initial fetch size. The dashboard still reports the collector as **Starting** until a later successful poll can compare two actual history watermarks.

## History headroom

The displayed **history headroom** percentage is not CPU, memory, mailcow load or generic server utilization.

For two consecutive successful polls, Cowcloak uses the newest event timestamp from the previous Rspamd history response as the previous watermark. The headroom percentage is:

```text
number of entries in the current response older than the previous watermark
-------------------------------------------------------------------------- × 100
                  total entries in the current response
```

A value of 63% therefore means that 63% of the currently loaded Rspamd history window still lies behind the point reached by the previous successful poll. Higher overlap gives the collector more room for a delayed poll before the previous watermark reaches the oldest edge of the loaded history window.

Cowcloak treats less than 10% overlap as low headroom. Exactly 10% is healthy. If the previous watermark is outside the current history window, the state becomes **possible gap** regardless of the numerical percentage.

If Cowcloak has to load exactly `COWCLOAK_USAGE_HISTORY_COUNT` entries, the dashboard also exposes that the configured maximum was reached. With adaptive loading this means the collector genuinely needed to go all the way to the configured ceiling. Reaching the maximum is a warning signal that the window may be tight, but it is not by itself proof that any events were missed.

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
- configured Rspamd history maximum
- number of history entries actually loaded
- oldest and newest event timestamps in the loaded window
- previous and current successful watermarks
- number of entries older than the previous watermark
- calculated history headroom and coverage state

Collector failures do not replace the last successful timestamp or successful history-window metadata.
