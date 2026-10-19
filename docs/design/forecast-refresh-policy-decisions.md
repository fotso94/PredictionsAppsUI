# Forecast refresh policy — decisions taken while implementing it

Branch `policy-round`, 2026-10-18. Companion to `forecast-refresh-policy.md`: each item is a choice
the design note left open, or one the implementation forced, with the reason, so a reviewer can
overturn it knowingly. Code: `backend/app/services/forecast_refresh_policy.py`,
`forecast_service.py` (`ensure_synced`, `estimate_pass`, the pending store), `sync_scheduler.py`
(`due`, `_estimate_cost`), `providers/gameforecast.py` (`request_cost`).

1. **The publication hour never moves later than the baseline.** The hour in force is the
   earliest of `SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR` (12, the week of fetch history that observed
   same-day runs at 12:xx and 18:xx) and every same-day-run observation of the last fourteen days.
   Read literally, "the earliest observed hour, 12 until observed" would let a first observation
   at 18 — one day on which the noon fetch bought an older run and the re-check bought the day's —
   set the hour to 18, after which nothing fetches before 18 and nothing can ever observe earlier
   again. The baseline is itself an observation, so it participates as one. Observations can only
   bring the hour forward (a forced sync at 09:30 that obtains the day's run makes 9 the hour for a
   fortnight), and "not yet published at H on D" is recorded for a reader without moving anything.
2. **A dormant verdict takes the day's slot** (`outcome: dormant`). The competition is re-examined
   at its next slot, the fixture sync running again at that turn, which is how it resumes by
   itself. Re-examining on every pass would cost a Live Score request per dormant competition per
   pass for a fixture that appears, at most, hours earlier than the next day's slot.
3. **A re-check that cannot be paid for is skipped, not deferred.** It is paid from what is left
   after every owed turn; nothing is owed, so it is neither recorded as deferred nor does it pause
   the provider. `report["recheck_skipped"]` names it.
4. **A deferral pauses the provider until the reset that refused it**, exactly as a stop did under
   the earlier rule: once a turn cannot be paid for, nothing bought later in the same window can be
   paid for either, and the pause is bounded by `_quota_cooldown_seconds` (ours or the provider's).
   The pass first serves every cheaper competition it can, so the pause follows the last fetch.
5. **Dormancy still applies under a forced sync.** `force` bypasses eligibility (the slot and the
   hour), never the budget, and never the calendar evidence: a forced fetch of a competition whose
   calendar lists nothing in the window buys an empty page.
6. **Retention.** Pending forecasts are retried on every pass while the kick-off is within the last
   `PENDING_RETRY_DAYS` (30) — attaching is a database read, and a fixture that arrives late or an
   alias added later binds the forecast for nothing, still prematch evidence if it was retrieved
   before kick-off. Past that window the item moves, payload untouched, to
   `forecast:retained:{provider}:{key}` under `{"forecast", "retention": {"retry": false, "reason",
   "retired_at", ...}}`, kept 180 days (`RETAINED_TTL_SECONDS`) and attachable on request through
   `reattach_pending(include_retained=True)`. The pending key's TTL is 37 days (window plus a
   week), not 48 h: a key that expires inside the retry window is a deletion nobody recorded. An
   item with no usable market is retained with its own reason rather than dropped.
7. **Pagination is priced from the last fetch.** `request_cost` quotes one page until a fetch of
   that competition has shown more (`provider:gameforecast:pages:{key}`, 14 days); the first fetch
   of a two-page competition costs one more than quoted, and the quote is exact from then on. The
   turn remains all-or-nothing on the quoted price, as the design says.
8. **The estimate reuses recorded calendar evidence only while the fixture cache would return the
   same answer** (`MATCH_CACHE_TTL_FIXTURES * 4`, the TTL `sync_upcoming` caches under), for the
   same window, and re-counts the database now. Outside that it prices the turn in full. Under
   `daily-slot` a dormant verdict takes the slot, so this reuse mostly matters when the hour rule
   is off or observed early (a turn late on D, an estimate in the small hours of D+1).
9. **Forecasts with no run date count as the day's run** for the slot: a provider that never dates
   its runs would otherwise be re-checked daily on a question it cannot answer. No observation is
   recorded from such a fetch.
10. **`forecast:last_sync:{provider}:{key}` is still written under `daily-slot`**: the coverage
    diagnosis reads it and `sync_order` (the earlier rule's order) is still a public method.
11. **The scheduler's `due()` applies its hour gate only under `elapsed-interval`.** Under
    `daily-slot` the task is offered every pass and the pass decides; a pass with nothing eligible
    re-attaches pending forecasts and records a success.
12. **No completeness flag, and why that is harmless for dormancy.** A Live Score calendar cut
    off at the provider's page cap is not reported by `SyncMeta`, so "covered the whole window" is
    established by the window asked (`days_ahead`, equal to the window judged) and the provider's
    own stop-when-past-the-window rule. Examined after both writers finished: the pager reaches
    `MAX_PAGES` only after that many non-empty pages lying wholly inside the window, so a cut-off
    answer always holds fixtures and can never produce the zero-fixture verdict dormancy needs; the
    fallback's calendar (`base.get_upcoming`, one unpaginated API-Football call per day) either
    covers every day or raises. Pinned by
    `test_a_calendar_cut_off_at_the_page_cap_is_never_empty_so_it_cannot_read_as_dormant`. A cut-off
    still under-counts fixtures for other readers; a flag is worth adding if one of them comes to
    depend on the count.
