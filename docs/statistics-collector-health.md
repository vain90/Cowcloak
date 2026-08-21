# Statistics collector health

When `MOOLIAS_USAGE_STATS=true`, Moolias records health metadata for the Rspamd-history collector in the same SQLite database as the usage statistics. The dashboard keeps the normal status intentionally compact. The expandable collector details show only the values that are useful for day-to-day operation: last success, remaining history buffer, the actual history fetch used for the last full poll, the poll interval and error information when relevant.

## States

- **OK / healthy**: the latest collection succeeded and the previous successful watermark is still safely covered.
- **Low buffer**: less than 10% of the configured Rspamd history maximum remains before the previous successful watermark could fall out of the available history window.
- **Possible gap**: the previous successful watermark is no longer safely inside the current Rspamd history window. This indicates that events may have fallen out of the history window between polls.
- **Stale**: no successful collection has completed once the configured number of expected poll intervals has elapsed.
- **Failed**: the latest collection attempt failed. A failure does not overwrite the timestamp or history metadata from the last successful collection.
- **Starting**: statistics are enabled, but two successful history windows are not available for comparison yet.

If statistics are disabled globally, collector health is disabled as well and this is not treated as an error.

## Adaptive history loading

`MOOLIAS_USAGE_HISTORY_COUNT` is the maximum history window Moolias may load, not the amount fetched on every poll.

Moolias probes progressively larger candidate windows:

```text
10 -> 25 -> 50 -> 100 -> 250 -> 500 -> configured maximum
```

For each candidate below the configured maximum, Moolias requests only the single Rspamd history entry at the position needed to guarantee the internal 10% overlap target. Rspamd/mailcow range positions are zero-based. For example, a 10-entry candidate probes position `9`, while a 25-entry candidate probes position `22` because three older entries are required to exceed 10%.

If the probe shows that the previous watermark is still too close to the old edge, Moolias moves to the next candidate without downloading the full batch. Once a probe is old enough, Moolias downloads that candidate window and verifies the actual overlap again. This second check protects against new history entries arriving between the probe and the full request.

If the real batch still has less than the internal overlap target, Moolias continues with the next size. If no smaller candidate is sufficient, it loads the configured maximum directly.

When there is no previous successful watermark yet, the statistics tracking start time is used only to choose an initial fetch size. The dashboard still reports the collector as **Starting** until a later successful poll can compare two actual history watermarks.

The internal adaptive overlap is deliberately separate from the user-facing history buffer. A small adaptive batch can have only the overlap needed to prove continuity while the configured maximum still provides a very large safety margin.

## History buffer

The displayed **history buffer** answers the operational question: how much of the configured Rspamd history capacity is still available before the previous successful watermark could fall out of the maximum window?

Moolias derives how many positions have been consumed since the previous watermark from the successfully loaded adaptive window:

```text
consumed positions = loaded entries - entries older than the previous watermark
remaining positions = configured history maximum - consumed positions

history buffer = remaining positions / configured history maximum * 100
```

For example, with `MOOLIAS_USAGE_HISTORY_COUNT=1000`, an adaptive 10-entry fetch containing one entry older than the previous watermark means that roughly nine positions have been consumed since the previous poll. The displayed buffer is therefore about **99.1%**, not 10%.

Entries with exactly the same timestamp as the previous watermark are conservatively treated as consumed capacity. If the previous watermark is no longer inside the current history window, Moolias reports a **possible gap** instead of presenting a misleading percentage.

Less than 10% remaining configured capacity is reported as **low buffer**. Exactly 10% remains healthy.

If Moolias has to load exactly `MOOLIAS_USAGE_HISTORY_COUNT` entries, the collector details note that the configured maximum was reached. Reaching the maximum is worth watching, especially if it happens repeatedly or the remaining buffer is low, but it is not by itself proof that events were missed.

## Lightweight unchanged-history probe

After a trustworthy healthy full poll, Moolias can check only the newest three Rspamd history entries. Their ordered SHA-256 fingerprints are compared with the previous full poll.

If those three entries are unchanged, Moolias skips the normal adaptive history fetch for that poll. Collector details show `3 entries checked · unchanged`, while the history buffer remains the value derived from the last full adaptive window. Any changed, missing or invalid probe state falls back to the normal adaptive path immediately.

## Deduplication retention

Moolias stores SHA-256 event hashes in `processed_events` and `sender_processed_events` so repeated Rspamd history scans do not increment statistics more than once. These technical hashes are pruned over time; aggregate usage counters and sender aggregates are not retention targets.

Rspamd history is count-based rather than time-based, so Moolias does not use an unsafe fixed rule such as "delete hashes older than seven days". At low mail volume an entry that old could still be inside the configured history window.

Instead, cleanup advances only after an internally safe comparison between consecutive successful history windows. The previous successful watermark is then old enough to serve as a known processed boundary. Moolias keeps an additional time safety margin behind that boundary:

```text
safety margin = max(1 hour, 2 × stale threshold)
prune floor   = previous successful watermark - safety margin
```

The stale threshold is `MOOLIAS_USAGE_POLL_SECONDS × MOOLIAS_USAGE_STALE_POLLS`. Cleanup is skipped while the internal coverage state is starting, low-overlap, gap, or otherwise not safe enough for pruning. This conservative internal rule is intentionally stricter than the user-facing buffer display.

The prune floor is stored persistently in the statistics database. The same transaction that advances the floor removes deduplication rows at or below it. Persistent SQLite insert guards then reject any later replayed Rspamd event at or below that floor even though its original hash has already been deleted. This keeps cleanup safe across application restarts and prevents an old history entry from being counted a second time.

Cleanup is checked only periodically, at most once every six hours after a safe watermark is available. Each cleanup transaction deletes at most 50,000 old rows from `processed_events` and at most 50,000 from `sender_processed_events`; a larger backlog is drained over later passes rather than creating one unbounded delete transaction. The cleanup uses the existing `event_at` indexes and does not run `VACUUM` in the collector hot path. SQLite can reuse freed pages for later writes; administrators may perform offline database maintenance separately if shrinking the physical file is ever required.

## Stale threshold

`MOOLIAS_USAGE_STALE_POLLS` controls how many expected collector intervals may pass without a successful collection before the state becomes stale.

The default is:

```dotenv
MOOLIAS_USAGE_POLL_SECONDS=60
MOOLIAS_USAGE_STALE_POLLS=3
```

With those values, a successful run becomes stale after 180 seconds without another success. The threshold scales with the poll interval:

```text
stale after = MOOLIAS_USAGE_POLL_SECONDS × MOOLIAS_USAGE_STALE_POLLS
```

A failed latest attempt is reported as **failed** immediately. The stale threshold is not a delay before reporting failures.

## Persisted metadata

The collector health row keeps the technical information required to calculate health and safely continue after application restarts, including:

- last collection attempt and success
- failure type for the latest failed attempt
- configured poll interval and Rspamd history maximum
- number and time range of entries in the last full history window
- previous and current successful watermarks
- internal adaptive overlap count and percentage
- internal coverage state

Most of this metadata is intentionally not displayed in the normal dashboard. It exists for collector safety and diagnostics, while the UI focuses on the smaller set of values useful during normal operation.
