# The browser-level journey on the isolated pair, 2026-10-18

The user-experience half of the journey, shown through the real pages in a real browser
(Chromium under Playwright, `frontend/e2e/live-isolated/suggestion-journey.spec.ts`) against the
isolated pair: the frontend on :3101, the backend on :8001, the database `soccer_predictions_e2e`
recreated from the live database at 19:33:02 UTC that evening. Nothing here touched the live
database: the isolated backend has no provider credentials and its scheduler is off, and the
spec refuses any backend whose `/health` does not name the clone.

Run at 19:34:34 UTC: `2 passed (6.5s)`, `playwright-run.txt`.

## Half one — a suggested combination becomes a recorded slip, through the page

1. The QA account signed in through the sign-in form.
2. `/selections/suggestions` showed three combinations, generated with the page's own defaults
   (three legs, not the two the API probe asks for). The first — `01-first-suggested-combination.txt`,
   `01-suggestions-page.jpg` — was Monza v Cagliari over 0.5 goals, Parma v Torino over 0.5
   goals, and Tottenham Hotspur v Coventry City double chance (Tottenham or draw), each published
   at 95% by GameForecast with a 44-hour-old forecast, combined chance "≈ 85.7%" with the page's
   own caveat that it is an approximation, not a calibrated prediction.
3. "Add all to slip" put the three legs in the slip dock (`02-slip-saved-in-the-dock.jpg`), the
   dock saved them under the name `Browser journey 2026-10-18T19:34`, and "record" with the
   reference `browser journey on the isolated pair` made the slip immutable
   (`03-slip-recorded-in-the-dock.jpg`).
4. `/selections` then showed the new card as *Recorded as placed · Pending*, three legs pending,
   with the page's own line that this is "the reader's own statement that this was placed
   elsewhere; nothing here is confirmed by any bookmaker" (`04-history-new-slip.txt`,
   `04-history-with-the-new-slip.jpg`). The API agrees: recorded, pending, three legs, each leg
   attributed to a forecast snapshot (`04-recorded-slip-from-the-api.json`).

This slip can only ever be pending on the clone, which receives no results.

## Half two — a settled slip shows its results, and viewing it again changes nothing

The slip displayed is `a0dce8dd`, the suggestion-born slip recorded through the API and settled
on the live database on 2026-10-17 (`../suggested-slip-2026-10-17.md`), carried into the clone by
the refresh.

1. `/selections` showed its card as *Recorded as placed · Won*, "2 won · 0 lost · 0 void ·
   0 unresolved · 0 pending", each leg **WON** with its result and its rule: Strasbourg v Paris
   Saint Germain, PSG goals under 3.5 — *Result 1-3*, "away team's regulation-time goals against
   the 3.5 line"; Bologna v Inter, total goals over 0.5 — *Result 1-3*, "regulation-time goals
   against the 0.5 line" (`05-history-settled-slip.txt`, `05-history-settled-slip.jpg`).
2. A reload showed the same card, text for text; leaving for the home page and coming back
   showed it again, text for text. The screenshot after the reload is byte-identical to the one
   before it (`md5-of-the-paired-captures.txt`, first two lines), so only one is kept.
3. `GET /api/v1/me/slips` before the views and after them answered byte-identically for every
   slip (`05-all-slips-before-viewing.json`; the "after" capture has the same md5, last two lines
   of the same file).
4. Outside the browser, the clone's slip tables were hashed before and after the whole run
   (`clone-slip-rows-before-and-after.txt`): 6 slips and 12 legs became 7 and 15 — the one slip
   half one recorded — and the md5 over every settled slip row and every settled leg row is the
   same before and after. Viewing changed nothing.

## What this does and does not show

It shows the pages: a suggestion chosen and recorded as a slip, and a settled slip displaying its
results, with repeat viewing changing nothing — on the isolated pair, adding nothing to the live
database. It is two slips rather than one because the clone cannot receive results: the slip
recorded here will never settle here, and the slip whose results are shown was settled on the
live database the day before. The full chain on one slip — suggestion, record, results,
settlement — is the API demonstration of 2026-10-17; this run shows what a reader sees at both
ends of it.

**One thing the captures show that is not right:** the selection line reads "Total goals 0.5:
Over 0.595%" and "Under 3.595%" — the probability ("95%") is rendered straight after the line
("0.5", "3.5") with nothing between them, on the suggestions page and on the history card alike.
The texts are kept as rendered; the join is a presentation defect to fix, not a value.

## Files

| File | What |
|---|---|
| `01-first-suggested-combination.txt`, `01-suggestions-page.jpg` | the first combination as the page rendered it |
| `02-slip-saved-in-the-dock.jpg`, `03-slip-recorded-in-the-dock.jpg` | the dock after save and after record |
| `04-history-new-slip.txt`, `04-history-with-the-new-slip.jpg`, `04-recorded-slip-from-the-api.json` | the new slip on the history page and from the API |
| `05-history-settled-slip.txt`, `05-history-settled-slip.jpg`, `05-all-slips-before-viewing.json` | the settled slip's card and every slip from the API before the views |
| `md5-of-the-paired-captures.txt` | the screenshot and the API answer after the views: identical to the ones before |
| `clone-slip-rows-before-and-after.txt` | the clone's slip tables hashed around the run |
| `playwright-run.txt` | the runner's own output |
