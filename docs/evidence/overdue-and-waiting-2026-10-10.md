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
| 09-24 09:30 | Turkmenistan v New Zealand | at most 19 | **stopped** 10-09 01:35 | absent; New Zealand played Palestine that day (2-2, stored) — a provisional pairing | nothing asks again on its own |
| 09-28 12:00 | Tajikistan v Palestine (`livescore:735608`) | at most 25 | next ask 10-11 02:02 | **stored and FINISHED 2-4 on its twin row** `livescore:1901222`, same pairing, same kick-off | an exact duplicate listing; see finding 2 |
| 09-28 12:00 | Kyrgyzstan v Lebanon (`livescore:1901250`) | at most 25 | next ask 10-11 02:02 | Kyrgyzstan played Maldives at 14:00 (5-0, stored) and Lebanon on 10-04 (3-1, stored) under new ids | a provisional pairing the provider replaced; asks stop at the horizon, 12 Oct |
| 09-30 04:00 | Papua New Guinea v Solomon Islands | at most 31 | next ask 10-11 02:03 | absent 29 Sep – 1 Oct | provisional; horizon 14 Oct |
| 09-30 12:00 | Mauritius v Djibouti | 22, unverified | next ask 10-11 02:03 | absent; Live Score once reported it in play (our row still says `live`, 24') and never closed it | horizon 14 Oct; the page does not show it as in play (finding 4) |
| 10-03 10:00 | Sri Lanka v Djibouti | 3 | next ask 10-11 02:35 | absent on 3 Oct (six friendlies, none ours) | provisional; horizon 17 Oct |
| 10-03 10:00 | Tunisia v Mali | 3 | next ask 10-11 02:35 | absent; Tunisia played Botswana on 09-28 (2-2, stored), Mali played Liberia on 09-29 (0-1, stored) and Morocco on 10-04 | provisional; horizon 17 Oct |
| 10-04 18:00 | Morocco v Ghana (`livescore:1901162`) | 4 | next ask 10-11 04:03 | the match played was **Morocco v Mali**, 18:03, 1-1 — stored under `livescore:736547` on 10-09 | a changed opponent under a new id; horizon 18 Oct |
| 10-04 22:30 | Bolivia v Gambia | 4 | next ask 10-11 04:03 | absent on 4 and 5 Oct | provisional; horizon 18 Oct |
| 10-06 18:45 | Croatia v Spain (UEFA Nations League) | 4 | next ask 10-10 17:54 | absent from the Nations League history on 5, 6 and 7 Oct (nine results on the 6th) | every 12 h now, every 24 h from the 13th; stops 20 Oct unless Live Score publishes it |
| 10-06 19:00 | Montserrat v Turks and Caicos Islands | 4 | next ask 10-10 17:54 | Live Score's CONCACAF Nations League history holds one result on the 6th and one on the 7th; none of these four | same schedule; stops 20 Oct |
| 10-06 20:00 | Saint Martin v Bahamas | 4 | next ask 10-10 17:54 | as above | same |
| 10-06 21:00 | Saint Vincent and The Grenadines v Sint Maarten | 4 | next ask 10-10 17:54 | as above | same |
| 10-06 23:00 | Antigua and Barbuda v Aruba | 4 | next ask 10-10 17:54 | as above | same |
| 10-10 12:02 | Rayo Vallecano v Athletic Bilbao | 4 | every pass | Live Score's live feed still shows it **in play at minute 31, 0-0**, more than five hours after the kick-off it lists as 12:02 (our row says 12:00), and its La Liga history for today is empty | the row follows the feed; the result is stored the moment Live Score closes the match or lists it; every pass for 6 h, then every 2 h |

So "keep waiting and everything will clear" is wrong for 16 of the 17. One (Rayo) is a provider
feed that has stalled and will clear when the provider closes it. Two have their result stored
under another row (the duplicate Tajikistan listing; Morocco v Mali for "Morocco v Ghana"). The
rest are listings Live Score published before kick-off and never played as listed — provisional
pairings of international friendlies and League C Nations League games it does not report — and
no result will ever arrive under their ids. Three of those are already stopped; the others ride
the schedule to the 14-day horizon and stop there.

## The 40 forecasts waiting for fixtures

All 40 are for matches **beyond the fixture window**: fixtures are fetched for today and the next
two days (`SYNC_FIXTURES_DAYS_AHEAD = 3`), forecasts for the next seven. None is a matching
failure: every one names a match the database does not hold yet.

| Competition | Matches on | Forecasts | Fixtures enter the window | Attach by |
|---|---|---|---|---|
| Champions League | 13–14 Oct | 18 | 11 Oct (first fixtures pass after 00:00 UTC) | the competition's next forecast turn, within 24 h, spending nothing |
| Bundesliga | 16–17 Oct | 7 | 14–15 Oct | likewise |
| La Liga | 16–17 Oct | 5 | 14–15 Oct | likewise |
| Premier League | 17 Oct | 5 | 15 Oct | likewise |
| Serie A | 16–17 Oct | 4 | 14–15 Oct | likewise |
| Ligue 1 | 16 Oct | 1 | 14 Oct | likewise |

The mechanism is `ForecastService._retry_pending` / `reattach_pending`: forecasts already paid for
are kept under `forecast:pending:<provider>:<competition>` in Redis and re-tried against the
fixtures the database holds before anything is fetched. Each entry lives 48 hours from its last
refresh, and every daily fetch refreshes it; a day of failed fetches (three competitions timed
out at 14:12 today and were deferred to the next reset) narrows that margin. That expiry is the
only way the count can fall other than by attaching.

## Findings

1. **Live Score's history is paged by `total_pages`, and the client stops on `next_page`.**
   `LiveScoreProvider._paginate` ends when the answer carries no `next_page`; `matches/history.json`
   announces its pages as `total_pages` only (`fixtures/list.json` does send `next_page`). So the
   results and recovery passes read one page — 30 results — per competition-day. No competition-day
   asked about so far has exceeded 30 (the most seen is 9), so nothing has been lost; a busier day
   would be. The fix is to honour `total_pages` in `_paginate`. Not changed in this round: it is
   provider-client code, the backend would need a restart during live matches, and the proof came
   first.
2. **An exact duplicate listing is outside the relisting rule by design.** `relisting_of` closes a
   second listing only when the same two teams appear the other way round within a day of each
   other; the same pairing at the same kick-off, stored twice under two provider ids, is what
   `scripts/repair_duplicate_matches.py` folds. Tajikistan v Palestine (`735608`, created
   2026-09-28 11:45) is such a row beside the played `1901222`. Folding it is an operator action
   on the live database — the owner's call.
3. **A listing the provider abandons has no state of its own.** A fixture Live Score published and
   then dropped (a provisional friendly pairing, a changed opponent under a new id) rides the retry
   schedule to the horizon and then sits as "awaiting a result" for good, with asking stopped. A
   rule that retires such a row — absent from the provider's listing for its day after kick-off and
   from its history for some days, so "withdrawn", with any selection on it void — would close 13
   of today's 17. That is a product decision, not built here.
4. **A match the provider left "in play" is not shown as in play.** Mauritius v Djibouti is served
   with status `live` and minute 24 ten days on, because status and minute are the last thing the
   provider said. The page trusts a status only while it can still be current
   (`frontend/src/utils/resultDelay.ts`, the Andorra v Malta precedent of 24 September), so every
   surface shows it as a result overdue, not as a running match.
5. **Rayo v Athletic is the provider's stall, not a rescheduling.** Live Score's own listing gives
   the kick-off as 12:02; the row's 12:00 is right, and the live task has been following the feed
   (last synced 17:17, minute 31, 0-0). Nothing to change on this side.
