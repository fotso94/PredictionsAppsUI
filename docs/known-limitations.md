# What this application does not yet do

Measured on 2026-09-20 against the running installation, not inferred from the code. Each entry
says what is missing, why it is still missing, and what closing it would take. An entry here is a
commitment to honesty, not a promise of a date.

## Language

**The backend's rule prose is English only, on every page that shows it.**
The settlement rules, the market definitions and the minimum-sample rationale are constants in
`backend/app/services/settlement.py` (`MINIMUM_SAMPLE_RATIONALE`, `HIT_RATE_DEFINITION`) and the
interface renders what the server sends. A French reader meets English paragraphs on the home page
and on every match page.

This is deliberate, not an oversight. Those sentences decide whether a figure is withheld, whether
a void counts as a loss, and what a hit test actually compares. A French paraphrase that drifted
from the English rule would be worse than English, because the reader would then be told a rule the
system does not apply. Closing it means localising them at the source, with a native reviewer
checking that each translated rule still says exactly what the code enforces.

A characterisation test in `frontend/e2e/mocked/localisation.spec.ts` counts the untranslated prose
rendered on the French home page, so the gap is visible and cannot grow unnoticed. The count comes
down deliberately or not at all.

**Two pages are untranslated: `MatchDetailPage` and the developer pages.**
`MatchDetailPage` does not call the translation hook, so its labels are English in both languages.
Its timestamps are correct, however: both were converted to the reader's chosen zone. `APITestPage`
and `DebugAPIPage` are developer tools and are not reader-facing.

**The French is not reviewed by a native speaker.** It was written and checked by machine, and
every term the writer was unsure about was flagged during the work. Market and money vocabulary in
particular deserves a human read before anyone relies on it.

## Time zones

Every reader-facing timestamp now goes through the formatter that honours the chosen zone, and the
two remaining device-zone calls on the match detail page were converted. Two hazards are worth
knowing rather than fixing:

- A backend timestamp that carries no offset is read as UTC. That is a claim, not a fact, and
  `backendInstant` reports whether the server actually said. A page that shows such a value should
  say so rather than present it as certain.
- A date-only value is a calendar date and not an instant. Rendering it in a zone behind UTC would
  move it to the previous day, so it is deliberately not converted.

## Live updating

A saved fixture discovers its own kickoff while the tab stays open, and so does a fixture that
appears only because the reader follows a team or competition. Both watches respect the reader's
automatic-updates preference, stop behind a hidden tab, and cost no provider request.

**What is unproven is the real thing.** No fixture has been in play during any test run, so the
in-play path has only ever been exercised against stubbed data. One live test,
`a fixture in play keeps its running score under a running label across a return`, skips for
exactly this reason and will run the first time a saved fixture is genuinely live. Until then, the
transition is proven deterministically and not observed.

## Forecast coverage

Coverage depends on a trial allowance of eight requests a day against six competitions, so it is
never complete on the day a fixture appears. The provider also enforces its own window, which is
not the UTC day this application counts against; the application now reads the provider's
rate-limit headers and waits on its published reset rather than guessing.

`backend/scripts/diagnose_forecast_coverage.py` reports, for any day and without a provider
request, which fixtures lack a forecast and why. It reports `unexplained` rather than guessing when
the stored records cannot evidence a cause.

## Expert convictions

An expert's conviction is optional and is now stored as null when they do not give one. Twenty-six
prediction rows predate that change and hold exactly zero. Some of those were blank and some may be
a deliberate zero, and nothing stored can tell them apart. They were deliberately left alone:
converting them would be inventing the information the old coercion destroyed.

## What is not built at all

A wager journal, a money ledger, bookmaker integration, odds comparison, receipt scanning, a
community feed, automated messaging and any prediction model of our own. Each is gated behind an
owner decision, and several are gated behind user validation that has not happened. The money
semantics are defined and executable in `backend/app/services/money_semantics.py` and
`docs/money-semantics.md` so that the rules exist before anything is built on them, but nothing
reads or writes a ledger.
