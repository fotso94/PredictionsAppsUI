# What is still overdue, and what is still waiting, on 2026-10-10

Read at 17:11–17:45 UTC against the live database (read-only) and the running backend. Where the
application's own record could not say why a result was missing, Live Score's history was read
directly — 27 read-only requests in all (history by competition and day, paged; the live feed
twice; the fixtures list once), outside the application, charged to the Starter plan's allowance
and written nowhere.

## The 17 overdue results, one by one

The retry schedule (`backend/app/services/match_registry.py`, `RETRY_SCHEDULE`): a fixture
without a result is asked about every pass (30 min) for six hours after kick-off, then every 2 h
until it is a day old, every 6 h until three days, every 12 h until a week, every 24 h until
14 days — and is given up on at the horizon, only ever straight after an ask the provider
answered. The 24 September rows reached that stop on 9 October.

| Kick-off (UTC) | Fixture | Asks | State | What Live Score holds | What happens next |
|---|---|---|---|---|---|
| 09-24 04:00 | Solomon Islands v Vanuatu | at most 19 | **stopped** 10-09 01:35 | absent from the friendlies' history on 23, 24 and 25 Sep (five matches on the 24th, none ours) | nothing asks again on its own |
| 09-24 07:00 | Papua New Guinea v New Caledonia | at most 19 | **stopped** 10-09 01:35 | absent, as above | nothing asks again on its own |
| 09-24 09:30 | Turkmenistan v New Zealand | at most 19 | **stopped** 10-09 01:35 | absent; New Zealand v Palestine that day is stored (2-2) under another id — whether this listing was played is not established | nothing asks again on its own; it stays unresolved |
| 09-28 12:00 | Tajikistan v Palestine (`livescore:735608`) | at most 25 | next ask 10-11 02:02 | **stored and FINISHED 2-4 on its twin row** `livescore:1901222`, same pairing, same kick-off | an exact duplicate listing; see finding 2 |
| 09-28 12:00 | Kyrgyzstan v Lebanon (`livescore:1901250`) | at most 25 | next ask 10-11 02:02 | absent on 28 Sep; Kyrgyzstan v Maldives at 14:00 (5-0) and Kyrgyzstan v Lebanon on 10-04 (3-1) are stored under other ids — neither is this listing's result, and whether it was played is not established | unresolved; asks stop at the horizon, 12 Oct |
| 09-30 04:00 | Papua New Guinea v Solomon Islands | at most 31 | next ask 10-11 02:03 | absent 29 Sep – 1 Oct | unresolved; asks stop at the horizon, 14 Oct |
| 09-30 12:00 | Mauritius v Djibouti | 22, unverified | next ask 10-11 02:03 | absent; Live Score once reported it in play (our row still says `live`, 24') and never closed it | horizon 14 Oct; the page does not show it as in play (finding 4) |
| 10-03 10:00 | Sri Lanka v Djibouti | 3 | next ask 10-11 02:35 | absent on 3 Oct (six friendlies, none ours) | unresolved; horizon 17 Oct |
| 10-03 10:00 | Tunisia v Mali | 3 | next ask 10-11 02:35 | absent on 3 Oct; other matches of both teams are stored under other ids, none of them this one | unresolved; horizon 17 Oct |
| 10-04 18:00 | Morocco v Ghana (`livescore:1901162`) | 4 | next ask 10-11 04:03 | absent on 4 and 5 Oct; Morocco v Mali, 18:03, 1-1 is stored under `livescore:736547` — a different listing, which cannot supply this one's result | unresolved; horizon 18 Oct |
| 10-04 22:30 | Bolivia v Gambia | 4 | next ask 10-11 04:03 | absent on 4 and 5 Oct | unresolved; horizon 18 Oct |
| 10-06 18:45 | Croatia v Spain (UEFA Nations League) | 4 | next ask 10-10 17:54 | absent from the Nations League history on 5, 6 and 7 Oct (nine results on the 6th) | every 12 h now, every 24 h from the 13th; stops 20 Oct unless Live Score publishes it |
| 10-06 19:00 | Montserrat v Turks and Caicos Islands | 4 | next ask 10-10 17:54 | Live Score's CONCACAF Nations League history holds one result on the 6th and one on the 7th; none of these four | same schedule; stops 20 Oct |
| 10-06 20:00 | Saint Martin v Bahamas | 4 | next ask 10-10 17:54 | as above | same |
| 10-06 21:00 | Saint Vincent and The Grenadines v Sint Maarten | 4 | next ask 10-10 17:54 | as above | same |
| 10-06 23:00 | Antigua and Barbuda v Aruba | 4 | next ask 10-10 17:54 | as above | same |
| 10-10 12:02 | Rayo Vallecano v Athletic Bilbao | 4 | every pass | Live Score's live feed still shows it **in play at minute 31, 0-0**, more than five hours after the kick-off it lists as 12:02 (our row says 12:00), and its La Liga history for today is empty | the row follows the feed; the result is stored the moment Live Score closes the match or lists it; every pass for 6 h, then every 2 h |

So "keep waiting and everything will clear" is wrong for 16 of the 17. One (Rayo) is a provider
feed that has stalled and will clear when the provider closes it. One is an exact duplicate of a
played row. The other 15 are absent from Live Score's history on their dates and on the adjacent
dates checked. **Absence from one provider's history does not establish that a match was cancelled
or replaced**; what the record supports is that this provider holds no result under these ids.
They stay unresolved — no selection on them is voided, nothing is inferred — three with asking
already stopped, the rest asked on the schedule until its horizon and then left as they are.

## The 40 forecasts waiting for fixtures

All 40 are for matches **beyond the fixture window**: fixtures are fetched for today and the next
two days (`SYNC_FIXTURES_DAYS_AHEAD = 3`), forecasts for the next seven. None is a matching
failure: every one names a match the database does not hold yet.

| Competition | Matches on | Forecasts | Fixtures become eligible | Attachment |
|---|---|---|---|---|
| Champions League | 13 Oct | 9 | 11 Oct (the first fixtures pass after 00:00 UTC) | the competition's next forecast turn after the fixtures are stored, if its re-try succeeds |
| Champions League | 14 Oct | 9 | 12 Oct | likewise |
| Bundesliga | 16–17 Oct | 7 | 14–15 Oct | likewise |
| La Liga | 16–17 Oct | 5 | 14–15 Oct | likewise |
| Premier League | 17 Oct | 5 | 15 Oct | likewise |
| Serie A | 16–17 Oct | 4 | 14–15 Oct | likewise |
| Ligue 1 | 16 Oct | 1 | 14 Oct | likewise |

The mechanism is `ForecastService._retry_pending` / `reattach_pending`: forecasts already paid for
are kept under `forecast:pending:<provider>:<competition>` in Redis and re-tried against the
fixtures the database holds before anything is fetched. The re-try itself spends nothing; the
fetch that follows it in a competition's turn spends one request, and attachment depends on the
fixture being stored and that turn's re-try succeeding, not on the calendar alone. Each entry lives 48 hours from its last
refresh, and every daily fetch refreshes it; a day of failed fetches (three competitions timed
out at 14:12 today and were deferred to the next reset) narrows that margin. That expiry is the
only way the count can fall other than by attaching.

## Findings

1. **Live Score's history is paged by `total_pages`, and the client stopped on `next_page` — fixed
   the same day.** `LiveScoreProvider._paginate` ended when the answer carried no `next_page`;
   `matches/history.json` announces its pages as `total_pages` only, and the provider documents 30
   results per page (`fixtures/list.json` does send `next_page`). So every results and recovery
   request read one page — the first 30 results — of its competition-day. No competition-day asked
   about so far has exceeded 30 (the most seen is 9), so nothing was lost here; a busier day would
   have been, silently. The pager now reads `total_pages` where it is sent, keeps `next_page` where
   that is what is sent, and logs when it stops at its own page cap with more advertised. The
   regression test is `backend/tests/providers/test_livescore_provider.py`
   (`test_history_is_paged_by_total_pages…`), and the sanitized responses showing both field styles
   are `docs/evidence/livescore-pagination-fields-2026-10-10.json`.
2. **An exact duplicate listing is outside the relisting rule by design.** `relisting_of` closes a
   second listing only when the same two teams appear the other way round within a day of each
   other; the same pairing at the same kick-off, stored twice under two provider ids, is what
   `scripts/repair_duplicate_matches.py` folds. Tajikistan v Palestine (`735608`, created
   2026-09-28 11:45) is such a row beside the played `1901222`. Folding it is an operator action
   on the live database — the owner's call.
3. **A listing the provider stops reporting has no state of its own.** A fixture Live Score
   published and then never reported a result for rides the retry schedule to the horizon and then
   sits as "awaiting a result" for good, with asking stopped — which is the right place for it
   while nothing establishes what happened. Retries running out is a budget fact about this
   application, not evidence about the match, so it must never void a selection. Closing such a
   row would need explicit evidence — a provider status saying cancelled or postponed, or a second
   source — and whether to seek that is a product decision, not built here.
4. **A match the provider left "in play" is not shown as in play.** Mauritius v Djibouti is served
   with status `live` and minute 24 ten days on, because status and minute are the last thing the
   provider said. The page trusts a status only while it can still be current
   (`frontend/src/utils/resultDelay.ts`, the Andorra v Malta precedent of 24 September), so every
   surface shows it as a result overdue, not as a running match.
5. **Rayo v Athletic is the provider's stall, not a rescheduling.** Live Score's own listing gives
   the kick-off as 12:02; the row's 12:00 is right, and the live task has been following the feed
   (last synced 17:17, minute 31, 0-0). Nothing to change on this side.
