import { expect, test, Page, Route, Request } from '@playwright/test';
import en from '../../src/i18n/messages/en';
import fr from '../../src/i18n/messages/fr';
import { compileMessage, renderMessage } from '../../src/i18n/format';
import {
  ApiMatch, Json, ProviderStatusPayload, SyncTaskPayload, baseDayPayload, baseMatches, baseStatus,
  neverRunTask, registerAuthHandler, stubBackend, watchForProblems,
} from '../support/api-stub';

/**
 * A MATCH WHOSE RESULT NEVER ARRIVED, AND WHAT THE READER IS TOLD ABOUT IT.
 *
 * ── THE DEFECT THIS FILE HOLDS SHUT ─────────────────────────────────────────────────────────
 *
 * `status` and `minute` are the last thing a provider said about a fixture, not a reading of the
 * clock. When a final score never arrives nothing corrects them, so they go on saying it. Measured
 * against the live database on 2026-09-24 at 21:27 UTC: Andorra v Malta rendering LIVE at HT five
 * and a half hours after kickoff, and three fixtures rendering SCHEDULED between twelve and
 * seventeen hours after theirs. A reader was being told, in the present tense, that a match was at
 * half time when it had finished before lunch.
 *
 * ── THE TWO STATES, AND WHY BOTH ARE TESTED SEPARATELY ──────────────────────────────────────
 *
 *   OVERDUE   the result is past the deadline the backend itself works to. Read off the clock; the
 *             backend is still asking.
 *   UNRESOLVED  the backend's recovery sweep reached one of its own limits — answered attempts, or
 *             age — and stopped asking. Recorded on the row (`match_metadata.recovery`) with the
 *             moment. It is a fact about our asking, never a finding that no result exists.
 *
 * A build that collapsed them into one "unknown" would pass a test that only looked for a warning.
 * So each is asserted for its own words, and each is asserted NOT to carry the other's.
 *
 * ── AND WHAT UNRESOLVED MAY NOT SAY ─────────────────────────────────────────────────────────
 *
 * The backend records a `gave_up_reason` beside the moment. It is English prose written for
 * whoever runs the sweep, and one version of it told readers "this competition's archive answers
 * nothing" — a provider limitation the evidence did not show. So the reader is never shown it, in
 * either language: `WHAT UNRESOLVED MAY NOT SAY` feeds the page that exact sentence and asserts it
 * never arrives, and that nothing in the notice calls a result unavailable or non-existent.
 *
 * ── AND THE THIRD THING A READER MUST TELL APART ────────────────────────────────────────────
 *
 * "We could not reach the provider" is neither of the two states above, and it is not the same
 * finding as "the provider answered without a result". The API carries it in two places, and both
 * are asserted: per fixture, as the recovery record's `last_outcome` ("provider_error" against
 * "fresh_unanswered"), and for the whole site, as the provider chain's failed request and the
 * scheduler's failing `recover` task in `/data-providers/status`. The fixture stays OVERDUE
 * throughout, because an outage is not a reason to stop asking.
 *
 * ── AND THE FOURTH, WHICH IS NOBODY'S FAILURE ───────────────────────────────────────────────
 *
 * `last_outcome: deferred` is a check WE did not make, because our own request allowance was
 * spent — including, since the backend moved it there, a refusal by our own daily ceiling. No
 * request went out, so nothing was unreachable and nothing failed, and a page that said "could
 * not reach the provider" about it would be blaming the provider for a limit of ours. `THE FOUR
 * THINGS A READER CAN BE TOLD` puts all four on one screen — still asking, could not reach, held
 * back, stopped asking — with a live match and a tie in extra time beside them, and asserts each
 * says its own sentence and none of the others'. `cached`, `recovered`, and a value this build
 * has never seen are covered too, so every `last_outcome` the API can serve
 * (backend/app/services/match_registry.py `RecoveryOutcome`, passed through verbatim by
 * backend/app/schemas/matches.py `serialize_recovery`) has a test saying what the page does with
 * it.
 *
 * ALL OF THIS IS MOCKED. Every payload here is a stub built in this file; nothing is read from the
 * running backend or the database.
 *
 * ── AND THE RISK THAT MATTERS MORE THAN EITHER ──────────────────────────────────────────────
 *
 * Turning a working live score into a warning. The whole change is a suppression, and a
 * suppression with its boundary one step out silently removes the running minute from every match
 * in play. `THE MATCH THAT IS GENUINELY IN PLAY` below is the test that fails if that happens: a
 * fixture 63 minutes past kickoff, inside the window, must still show LIVE and 63'.
 *
 * And `A TIE PLAYED PAST THE DEADLINE` is the harder half of the same risk, because the deadline
 * is not a whistle. A knockout tie level at 90 plays extra time and may then take penalties, so it
 * is still being played hours after a 90-minute match's result would have been due — and a
 * national-team knockout is precisely what this installation's national-team competitions are made
 * of. Those rows must keep their minute and their scoreline at every width and in both languages,
 * on the same screen as a stuck fixture that loses both.
 *
 * ── VIEWPORTS AND LANGUAGES ─────────────────────────────────────────────────────────────────
 *
 * playwright.config.ts runs this file at 1440 (mocked-desktop), 390 (mocked-mobile) and 360
 * (mocked-mobile-360), so every assertion below is made three times at three widths. Each one runs
 * in English and in French, and each asserts the sentence the catalogue actually holds — rendered
 * here through the application's own `compileMessage`/`renderMessage`, so a message that changes
 * changes the assertion with it rather than leaving a stale literal behind.
 *
 * ── COST ────────────────────────────────────────────────────────────────────────────────────
 *
 * Every /api/v1 route is intercepted. Nothing reaches a provider, and the last test asserts that
 * no request this file drives carries `refresh=true`.
 */

type Language = 'en' | 'fr';

const LANGUAGE_KEY = 'sp.language.v1';

/**
 * The instant every clock in this file is fixed at, and the local day that follows from it.
 *
 * 23:30 UTC is 19:30 in America/New_York, which playwright.config.ts puts the context on, so all
 * three fixtures below sit inside ONE local calendar day however far back their kickoffs are —
 * the day list would otherwise be asserting about a fixture that belongs to yesterday.
 */
const NOW = new Date('2026-09-24T23:30:00Z');
const LOCAL_DAY = '2026-09-24';

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

/**
 * The backend's own grace between a kickoff and a result being expected: `UNSETTLED_GRACE` in
 * app/services/match_registry.py, served per fixture as `result_expected_by`.
 *
 * Reproduced here because these payloads stand in for the backend's, and a stub that invented its
 * own deadline would be testing the stub. The application never computes it — that is the point of
 * serving it — so if this number and the backend's ever diverge, the backend's is the one on the
 * page.
 */
const GRACE_MS = 150 * MINUTE;

const at = (offsetMs: number): string => new Date(NOW.getTime() + offsetMs).toISOString();

/**
 * How long ago each of the two deadlines passed, and why these particular numbers.
 *
 * `relativeTime` rounds to minutes below 90 minutes and to hours above it, so an instant placed an
 * hour back renders as "60 minutes" and not "1 hour". Both offsets here sit well clear of that
 * boundary, so the phrase this file reproduces from the catalogue is the phrase the page builds —
 * without this file having to own a second copy of the rounding rule.
 */
/** How long ago the OVERDUE fixture's result fell due (its kickoff is 2.5 hours before that). */
const OVERDUE_LATE_HOURS = 3;
const GAVE_UP_HOURS = 2;

/** A fixture from the capture, re-timed and renamed, with its result state spelled out. */
function fixture(spec: {
  id: string;
  home: string;
  away: string;
  kickoffMs: number;
  status: string;
  minute?: string | null;
  score?: Json | null;
  recovery?: Json | null;
}): ApiMatch {
  const match = JSON.parse(JSON.stringify(baseMatches()[0])) as ApiMatch;
  match.id = spec.id;
  match.kickoff_utc = at(spec.kickoffMs);
  match.status = spec.status;
  match.minute = spec.minute ?? null;
  match.score = spec.score ?? null;
  match.result_expected_by = at(spec.kickoffMs + GRACE_MS);
  match.recovery = spec.recovery ?? null;
  if (match.home) { match.home.name = spec.home; match.home.short_name = spec.home; }
  if (match.away) { match.away.name = spec.away; match.away.short_name = spec.away; }
  return match;
}

/**
 * Half time, five and a half hours ago — the fixture measured on the live database.
 *
 * It CARRIES A SCORE, deliberately. A 0-0 that arrived before the feed went quiet is the most
 * dangerous thing on the row: it is a real number the provider really sent, and it is not the
 * result of the match, because nobody has said the match ended or ended there. A build that keeps
 * the warning and keeps the digits has fixed nothing, and `no score is presented` below is what
 * catches that.
 */
const OVERDUE = fixture({
  id: 'overdue-halftime-fixture',
  home: 'Andorra',
  away: 'Malta',
  kickoffMs: -(5 * HOUR + 30 * MINUTE),
  status: 'halftime',
  minute: 'HT',
  score: { home: 0, away: 0, ht_home: 0, ht_away: 0 },
});

/** Seventeen and a half hours past kickoff, still SCHEDULED, and given up on two hours ago. */
const GIVEN_UP = fixture({
  id: 'given-up-scheduled-fixture',
  home: 'Solomon Islands',
  away: 'Vanuatu',
  kickoffMs: -(17 * HOUR + 30 * MINUTE),
  status: 'scheduled',
  recovery: {
    attempts: 3,
    last_attempt_at: at(-GAVE_UP_HOURS * HOUR),
    gave_up_at: at(-GAVE_UP_HOURS * HOUR),
    gave_up_reason: 'no result after 3 attempts',
  },
});

/** 63 minutes in, inside the window, genuinely being played. Nothing here may change for it. */
const IN_PLAY = fixture({
  id: 'genuinely-in-play-fixture',
  home: 'Roving Athletic',
  away: 'Harbour Town',
  kickoffMs: -63 * MINUTE,
  status: 'live',
  minute: '63',
  score: { home: 2, away: 1, ht_home: 1, ht_away: 0 },
});

/**
 * A TIE IN EXTRA TIME, PAST THE DEADLINE, AND STILL BEING PLAYED.
 *
 * The deadline is when a result becomes overdue. It is not when football stops, and a knockout tie
 * level at 90 minutes — which is what a national-team knockout is — plays another half hour after
 * it. This one kicked off 2h35m ago, so its result fell due five minutes ago, and it is at 105
 * minutes with a goal each: every word of its row is current, and there is a television showing
 * it. A build that reads the clock and nothing else takes the minute and the scoreline off it and
 * says in prose that no score is claimed, which is the same defect as the one above with the sign
 * reversed — the page refusing to say what it does know.
 */
const EXTRA_TIME = fixture({
  id: 'extra-time-fixture',
  home: 'Cape Verde',
  away: 'Guinea',
  kickoffMs: -(2 * HOUR + 35 * MINUTE),
  status: 'live',
  minute: '105',
  score: { home: 1, away: 1, ht_home: 0, ht_away: 1 },
});

/**
 * The same tie a shootout later: 2h55m past kickoff, at the spot, and reported as such.
 *
 * Penalties are the part of a tie with no clock on them at all, so this row is the furthest any
 * genuinely live fixture gets from its kickoff — and the last moment at which a reader most wants
 * the score that is on the row.
 */
const SHOOTOUT = fixture({
  id: 'penalty-shootout-fixture',
  home: 'Zambia',
  away: 'Namibia',
  kickoffMs: -(2 * HOUR + 55 * MINUTE),
  status: 'live',
  minute: 'PEN',
  score: { home: 2, away: 2, ht_home: 1, ht_away: 0 },
});

/**
 * Called off, and long past the deadline a played fixture would have had.
 *
 * A postponed match is not late for a result: it is not being played, and nobody is waiting on a
 * score. `postponed` and `cancelled` are settled words, and a build that measured every fixture
 * against the clock without asking what its status MEANS would put "Result overdue" over a match
 * that was called off — replacing one wrong statement with a different wrong statement.
 */
const CALLED_OFF = fixture({
  id: 'called-off-fixture',
  home: 'Ashfield United',
  away: 'Port Meadow',
  kickoffMs: -(8 * HOUR),
  status: 'postponed',
});

/**
 * The same stuck half-time fixture from a backend that does not serve `result_expected_by`.
 *
 * This is the state every other spec in this suite is in, and it is why they were untouched by
 * this change: with no deadline from the backend there is nothing to measure against, and the
 * browser may not choose a number of its own — 150 minutes is a constant of this installation's
 * scheduler, not a property of football. So the row goes on saying exactly what it always said.
 */
const NO_DEADLINE: ApiMatch = (() => {
  const copy = JSON.parse(JSON.stringify(OVERDUE)) as ApiMatch;
  copy.id = 'no-deadline-fixture';
  if (copy.home) { copy.home.name = 'Kestrel City'; copy.home.short_name = 'Kestrel City'; }
  if (copy.away) { copy.away.name = 'Wold Rovers'; copy.away.short_name = 'Wold Rovers'; }
  delete copy.result_expected_by;
  return copy;
})();

/**
 * THE UNRESOLVED STATE THE OWNER CHECKED, as the local API serves it.
 *
 * `GET /api/v1/matches/9b7320ae-abbb-437a-9dad-d88344d7f7a7` on 2026-09-25: UEFA Nations League,
 * Andorra v Malta, `halftime`, minute `HT`, 1-1 at the interval, and a recovery record with three
 * answered attempts, `gave_up_at` set and `gave_up_reason` "no result after 3 attempts". Re-timed
 * like every fixture here — kickoff 7h29m before the fixed clock, as 16:01 was before 23:30 — and
 * otherwise as served, down to the half-time score it must not show.
 *
 * The recovery object is in the shape `serialize_recovery` in the working tree emits, which is
 * wider than what the running process served that morning: the extra fields are filled from the
 * same stored row (`last_outcome` "fresh_unanswered" at the moment of giving up, no provider
 * errors, nothing about the archive recorded). `GIVEN_UP` above keeps the narrower shape, so both
 * are exercised.
 *
 * `stopped_by` is null because that is what the row holds: the three-attempts rule that made this
 * stop predates the field and never wrote it, and the serializer serves null rather than name a
 * policy that did not make the stop. The page must therefore not describe it as the retry
 * budget's — `BUDGET_STOPPED` below is the stop that is.
 */
const OWNER_CHECKED = fixture({
  id: 'owner-checked-unresolved-fixture',
  home: 'Andorra',
  away: 'Malta',
  kickoffMs: -(7 * HOUR + 29 * MINUTE),
  status: 'halftime',
  minute: 'HT',
  score: { home: 1, away: 1, ht_home: 1, ht_away: 1 },
  recovery: {
    attempts: 3,
    last_attempt_at: at(-GAVE_UP_HOURS * HOUR),
    gave_up_at: at(-GAVE_UP_HOURS * HOUR),
    gave_up_reason: 'no result after 3 attempts',
    stopped_by: null,
    last_outcome: 'fresh_unanswered',
    last_outcome_at: at(-GAVE_UP_HOURS * HOUR),
    provider_errors: 0,
    last_provider_error_at: null,
    next_ask_after: null,
    reopened_at: null,
    archive: null,
  },
});

/**
 * STOPPED BY THE RETRY BUDGET — the only stop the backend still makes.
 *
 * `stopped_by: "retry_budget"`, with `gave_up_reason` in the form `_stop_reason`
 * (backend/app/services/match_registry.py) writes it. That reason is operator prose and must not
 * reach the page either; what the page may say is the catalogue's own sentence for a budget stop.
 */
const BUDGET_STOPPED = fixture({
  id: 'budget-stopped-fixture',
  home: 'Wetherby Cross',
  away: 'Yarm Athletic',
  kickoffMs: -(15 * 24 * HOUR),
  status: 'halftime',
  minute: 'HT',
  score: { home: 2, away: 2, ht_home: 2, ht_away: 2 },
  recovery: {
    attempts: 11,
    last_attempt_at: at(-GAVE_UP_HOURS * HOUR),
    gave_up_at: at(-GAVE_UP_HOURS * HOUR),
    gave_up_reason: 'We asked the results provider 11 times, most recently 2026-09-25 21:30 UTC, and '
      + 'each answer it gave held no result for this match. We stopped at the 14-day results horizon '
      + 'of our request budget: a limit on what we spend, not evidence that no result exists.',
    stopped_by: 'retry_budget',
    last_outcome: 'fresh_unanswered',
    last_outcome_at: at(-GAVE_UP_HOURS * HOUR),
    provider_errors: 0,
    last_provider_error_at: null,
    deferrals: 0,
    last_deferred_because: null,
    next_ask_after: null,
    reopened_at: null,
    archive: { state: 'empty', rows: 0, asked_at: at(-GAVE_UP_HOURS * HOUR) },
  },
});

/** How long before the fixed clock the most recent recovery pass ran, for the two below. */
const LAST_CHECK_MINUTES = 10;

/**
 * OVERDUE, AND THE LAST CHECK REACHED NOBODY.
 *
 * The recovery record `serialize_recovery` emits for a fixture the sweep is still asking about
 * during an outage: no attempt counted (a pass that reached nobody is not one), two provider
 * errors, `last_outcome` "provider_error" ten minutes ago, the next ask scheduled. The fixture
 * itself is the Andorra v Malta row's shape — stuck at a minute the clock has walked away from —
 * under invented names.
 */
const OVERDUE_UNREACHABLE = fixture({
  id: 'overdue-unreachable-fixture',
  home: 'Harrow Vale',
  away: 'Linton Park',
  kickoffMs: -(4 * HOUR),
  status: 'live',
  minute: '52',
  score: { home: 1, away: 0, ht_home: 1, ht_away: 0 },
  recovery: {
    attempts: 0,
    last_attempt_at: null,
    gave_up_at: null,
    gave_up_reason: null,
    stopped_by: null,
    last_outcome: 'provider_error',
    last_outcome_at: at(-LAST_CHECK_MINUTES * MINUTE),
    provider_errors: 2,
    last_provider_error_at: at(-LAST_CHECK_MINUTES * MINUTE),
    next_ask_after: at(20 * MINUTE),
    reopened_at: null,
    archive: null,
  },
});

/**
 * OVERDUE, AND THE PROVIDER ANSWERED WITHOUT IT — the other half of the distinction.
 *
 * One answered attempt ten minutes ago, `last_outcome` "fresh_unanswered", and the archive's own
 * answer for the competition and date recorded as `empty`: the shape the working-tree serializer
 * emits for a fixture whose date returned no rows when it was asked. That is what the archive
 * held at that moment and nothing more.
 */
const OVERDUE_ANSWERED = fixture({
  id: 'overdue-answered-fixture',
  home: 'Colbeck',
  away: 'Stannard',
  kickoffMs: -(4 * HOUR + 10 * MINUTE),
  status: 'halftime',
  minute: 'HT',
  score: { home: 0, away: 0, ht_home: 0, ht_away: 0 },
  recovery: {
    attempts: 1,
    last_attempt_at: at(-LAST_CHECK_MINUTES * MINUTE),
    gave_up_at: null,
    gave_up_reason: null,
    stopped_by: null,
    last_outcome: 'fresh_unanswered',
    last_outcome_at: at(-LAST_CHECK_MINUTES * MINUTE),
    provider_errors: 0,
    last_provider_error_at: null,
    next_ask_after: at(20 * MINUTE),
    reopened_at: null,
    archive: { state: 'empty', rows: 0, asked_at: at(-LAST_CHECK_MINUTES * MINUTE) },
  },
});

/**
 * Given up on by AGE, with no answered attempt at all, carrying the sentence that must never reach
 * a reader.
 *
 * `gave_up_reason` is copied from `_past_horizon_reason` in backend/app/services/match_registry.py
 * as it stood when this was written, with its numbers filled in for an eight-hour-old kickoff. It
 * asserts that the competition's archive answers nothing, which the saved evidence contradicts
 * (docs/evidence/livescore-archive-observations.json: past national tournaments DO answer, and
 * nothing establishes that any competition lacks an archive) — so it is the right thing to feed
 * the page: if any surface ever prints the backend's prose again, this is the sentence it prints.
 *
 * `attempts: 0` is the other half. Nothing answered, so no count may be claimed.
 */
const ARCHIVE_CLAIM =
  'kickoff is 8 hours old and no endpoint still carries it: this competition\'s archive answers '
  + 'nothing and the live feed\'s reach is the live window, so nothing was asked after 6 hours';
const AGED_OUT = fixture({
  id: 'aged-out-fixture',
  home: 'Northmoor',
  away: 'Eastvale',
  kickoffMs: -(8 * HOUR),
  status: 'live',
  minute: '67',
  score: { home: 0, away: 2, ht_home: 0, ht_away: 1 },
  recovery: {
    attempts: 0,
    last_attempt_at: null,
    gave_up_at: at(-GAVE_UP_HOURS * HOUR),
    gave_up_reason: ARCHIVE_CLAIM,
  },
});

/**
 * A full recovery record in the working-tree serializer's shape, still being asked about.
 *
 * Each fixture below overrides only the fields its state is about, so the difference between two
 * of them is exactly the difference the page has to put into words.
 */
const askingRecord = (overrides: Json): Json => ({
  attempts: 1,
  last_attempt_at: at(-3 * HOUR),
  gave_up_at: null,
  gave_up_reason: null,
  stopped_by: null,
  last_outcome: 'fresh_unanswered',
  last_outcome_at: at(-LAST_CHECK_MINUTES * MINUTE),
  provider_errors: 0,
  last_provider_error_at: null,
  next_ask_after: at(20 * MINUTE),
  reopened_at: null,
  archive: null,
  ...overrides,
});

/**
 * OVERDUE, AND OUR LAST CHECK WAS HELD BACK BY OUR OWN ALLOWANCE — `last_outcome: deferred`.
 *
 * The record `record_recovery_outcome(DEFERRED)` leaves: no attempt spent by the deferral, no
 * provider error counted (none happened), the fixture still due — `next_ask_after` is the moment
 * of the deferral itself, because a deferred fixture stays due. The row carries a 2-1 from the
 * 71st minute, which is exactly as much a result as the half-time 0-0 above: not one.
 */
const OVERDUE_HELD_BACK = fixture({
  id: 'overdue-held-back-fixture',
  home: 'Brackley Town',
  away: 'Oxley Wanderers',
  kickoffMs: -(4 * HOUR),
  status: 'live',
  minute: '71',
  score: { home: 2, away: 1, ht_home: 1, ht_away: 1 },
  recovery: askingRecord({
    last_outcome: 'deferred',
    last_outcome_at: at(-LAST_CHECK_MINUTES * MINUTE),
    deferrals: 1,
    last_deferred_because: ['our_allowance'],
    next_ask_after: at(-LAST_CHECK_MINUTES * MINUTE),
  }),
});

/**
 * DEFERRED, BUT NOT BY US — the other causes `last_deferred_because` records.
 *
 * Every one of these is `last_outcome: deferred` exactly like the row above, and on a page that
 * read only `last_outcome` all four said "held back by our own request allowance". They are:
 *
 *   * the provider's own reported limit (`provider_allowance`: a `ProviderRequestNotSent` with
 *     `refused_by: provider`). Listed beside `not_configured`, which a second provider in the
 *     chain records when it has no key: the external cause is the one named.
 *   * a cool-down after an EARLIER request went out and failed (`cooling_down`). This check went
 *     nowhere; it did not fail. The failure it waited on is a different, earlier call.
 *   * a deferral from a backend that predates the field: nothing is known about why, so the page
 *     says only that the check was not sent.
 */
const deferredRecord = (because: string[] | undefined): Json => {
  const record = askingRecord({
    last_outcome: 'deferred',
    last_outcome_at: at(-LAST_CHECK_MINUTES * MINUTE),
    deferrals: 1,
    next_ask_after: at(-LAST_CHECK_MINUTES * MINUTE),
  });
  if (because !== undefined) record.last_deferred_because = because;
  return record;
};
const OVERDUE_PROVIDER_LIMIT = fixture({
  id: 'overdue-provider-limit-fixture',
  home: 'Cawood',
  away: 'Dunmere',
  kickoffMs: -(4 * HOUR),
  status: 'live',
  minute: '64',
  score: { home: 0, away: 1, ht_home: 0, ht_away: 0 },
  recovery: deferredRecord(['provider_allowance', 'not_configured']),
});
const OVERDUE_COOLING = fixture({
  id: 'overdue-cooling-fixture',
  home: 'Elsdon',
  away: 'Farndale',
  kickoffMs: -(4 * HOUR),
  status: 'halftime',
  minute: 'HT',
  score: { home: 1, away: 1, ht_home: 1, ht_away: 1 },
  recovery: deferredRecord(['cooling_down']),
});
const OVERDUE_DEFERRED_UNSTATED = fixture({
  id: 'overdue-deferred-unstated-fixture',
  home: 'Gilling',
  away: 'Hawes',
  kickoffMs: -(4 * HOUR),
  status: 'live',
  minute: '80',
  score: { home: 3, away: 0, ht_home: 2, ht_away: 0 },
  recovery: deferredRecord(undefined),
});

/**
 * OVERDUE, AND OUR LAST CHECK READ OUR OWN STORED COPY — `last_outcome: cached`.
 *
 * The day came out of the results cache, so the pass asked nobody. The copy held no result for
 * this fixture (one that did would have settled it), and that is all the page may say about it.
 */
const OVERDUE_STORED_COPY = fixture({
  id: 'overdue-stored-copy-fixture',
  home: 'Fenwick Albion',
  away: 'Greyhope',
  kickoffMs: -(4 * HOUR + 20 * MINUTE),
  status: 'halftime',
  minute: 'HT',
  score: { home: 0, away: 1, ht_home: 0, ht_away: 1 },
  recovery: askingRecord({ last_outcome: 'cached' }),
});

/**
 * ONE OF THE EIGHT, PUT BACK UNDER THE RETRY SCHEDULE.
 *
 * The live database on 2026-09-25 holds eight fixtures stopped at 2026-09-24 22:54 UTC under a
 * three-attempts rule that no longer exists, each with `attempts` 3 and `last_outcome`
 * "fresh_unanswered". The backend is putting them back under the current schedule, which removes
 * `gave_up_at`, `gave_up_reason` and `stopped_by` and keeps the count and the last finding. What
 * is left is a row that WAS stopped and is being asked about again — and it must read as overdue
 * and still being asked, not as Unresolved. `reopened_at` is set and `next_ask_after` is not,
 * because `reopen_retired` writes the first and the next pass writes the second: the page must not
 * need the second to know the fixture is being asked about.
 */
const PUT_BACK = fixture({
  id: 'put-back-halftime-fixture',
  home: 'Andorra',
  away: 'Malta',
  kickoffMs: -(7 * HOUR + 29 * MINUTE),
  status: 'halftime',
  minute: 'HT',
  score: { home: 1, away: 1, ht_home: 1, ht_away: 1 },
  recovery: askingRecord({
    attempts: 3,
    last_attempt_at: at(-GAVE_UP_HOURS * HOUR),
    last_outcome: 'fresh_unanswered',
    last_outcome_at: at(-GAVE_UP_HOURS * HOUR),
    next_ask_after: null,
    reopened_at: at(-5 * MINUTE),
  }),
});

/**
 * `last_outcome` values the page gives no sentence of their own, each on a row still overdue.
 *
 * `recovered` on a row that reads unsettled again is the record and the status disagreeing; the
 * page repeats neither. A value this build has never heard of is carried and not put into words.
 * Both are still asked about — the record exists and nobody stopped — so both say so.
 */
const RECOVERED_BUT_UNSETTLED = fixture({
  id: 'recovered-but-unsettled-fixture',
  home: 'Hollins Park',
  away: 'Ivel Rangers',
  kickoffMs: -(5 * HOUR),
  status: 'live',
  minute: '88',
  score: { home: 3, away: 3, ht_home: 1, ht_away: 2 },
  recovery: askingRecord({ last_outcome: 'recovered' }),
});
const UNKNOWN_OUTCOME = fixture({
  id: 'unknown-outcome-fixture',
  home: 'Jarrow Vale',
  away: 'Kirkby Moor',
  kickoffMs: -(5 * HOUR),
  status: 'scheduled',
  recovery: askingRecord({ last_outcome: 'some_outcome_this_build_never_heard_of' }),
});

const ALL = [GIVEN_UP, OVERDUE, IN_PLAY];

/* ------------------------------------------------------------------ what the catalogue says */

const catalogue = (language: Language): Record<keyof typeof en, string> =>
  (language === 'fr' ? fr : en) as Record<keyof typeof en, string>;

const say = (
  language: Language,
  key: keyof typeof en,
  params: Record<string, string | number> = {},
): string => renderMessage(compileMessage(catalogue(language)[key]), language, params);

/**
 * The rounded phrase the page puts in these sentences, reproduced from the same catalogue entries
 * `relativeTime` builds it from.
 *
 * Deterministic because the browser clock is fixed: an instant three hours back rounds to "3
 * hours" on the `relativeTime` boundaries and cannot drift with the hour the suite is run.
 */
const agoPhrase = (language: Language, hours: number): string =>
  say(language, 'time.ago', { duration: say(language, 'duration.hours', { count: hours }) });

/** The same, in minutes, for the most recent check — below the 90 minutes `relativeTime` rounds to hours at. */
const minutesAgoPhrase = (language: Language, minutes: number): string =>
  say(language, 'time.ago', { duration: say(language, 'duration.minutes', { count: minutes }) });

/**
 * "A result was due 3 hours ago; none has reached us." — the row's short form.
 *
 * THE PHRASE MEASURES THE DEADLINE, NOT THE KICKOFF, and OVERDUE_LATE_HOURS is named for the
 * deadline for that reason: this fixture kicked off five and a half hours ago and its result was
 * due three. A sentence that put the deadline's number against the word "kicked off" would be the
 * page correcting one false statement with another, so the wording and this expectation agree on
 * which event is being measured.
 */
const overdueShort = (language: Language): string =>
  say(language, 'fixture.result.overdueShort', { due: agoPhrase(language, OVERDUE_LATE_HOURS) });

/** The match page's full sentence for the same fixture. */
const overdueDetail = (language: Language): string =>
  say(language, 'fixture.result.overdueDetail', { due: agoPhrase(language, OVERDUE_LATE_HOURS) });

const givenUpDetail = (language: Language): string =>
  say(language, 'fixture.result.givenUpDetail', { when: agoPhrase(language, GAVE_UP_HOURS) });

/**
 * Words that would turn "we stopped asking" into a claim about the result itself.
 *
 * None of them is in any sentence the catalogue gives these states, so any of them appearing in a
 * notice or a row means something other than the catalogue is speaking — which is exactly how the
 * backend's "archive answers nothing" reached the page. "Exists" is not listed: the policy sentence
 * says, in both languages, that stopping does NOT mean no result exists, and that is the one place
 * the word belongs.
 */
const OVERCLAIM = /unavailable|indisponible|archive|endpoint|does not exist|n’existe pas|n'existe pas|cannot|impossible|never be|jamais disponible/i;

/** The backend's operator prose, in any of the forms it has been written. */
const OPERATOR_PROSE = /no result after|\d+ attempts|kickoff is|Recorded reason|Motif enregistré/i;

/**
 * The vocabulary of a call that went out and failed, in both languages.
 *
 * A check held back by our own allowance may use none of it: no request went out, so nothing was
 * unreachable and nothing failed. `\breach\b` is a whole word so that "none has reached us" — a
 * true statement about the RESULT on every overdue fixture — is not mistaken for a claim about
 * the provider. The catalogue test below proves the pattern can see red: the two unreachable
 * sentences must match it.
 */
const FAILURE_WORDS = /could not|couldn|fail|error|unreachable|\breach\b|n’a pas pu|n'a pas pu|échou|erreur|joindre|injoignable/i;

/* ------------------------------------------------------- a provider the backend cannot reach */

/** A scheduler task as `/data-providers/status` serves it, timed against the fixed clock. */
function taskAt(
  intervalSeconds: number, successMsAgo: number, dueMsAhead: number,
  overrides: Partial<SyncTaskPayload> = {},
): SyncTaskPayload {
  return {
    ...neverRunTask(intervalSeconds),
    never_run: false,
    last_run_at: at(-successMsAgo),
    last_success_at: at(-successMsAgo),
    last_duration_ms: 812,
    runs: 4,
    next_due_at: at(dueMsAhead),
    due_now: false,
    reason_not_due: `next due at ${at(dueMsAhead)}`,
    ...overrides,
  };
}

/**
 * What httpx says when the provider's host cannot be resolved, wrapped the way
 * `ProviderHttpClient.get_json` wraps it (backend/app/services/providers/http.py). The text after
 * "network error:" is macOS's own resolver message for a machine with no network.
 */
const NETWORK_ERROR = 'livescore: network error: [Errno 8] nodename nor servname provided, or not known';

/**
 * The provider unreachable, as the status endpoint reports it during an outage.
 *
 * Two places carry it, and both are reproduced. The provider chain's active entry has a failed
 * request newer than its last success — which is what the site banner reads. And the scheduler's
 * `recover` task failed its last pass with the sentence `_run_recovery`
 * (backend/app/services/sync_scheduler.py) writes when no stranded fixture got an answer, with
 * `backoff_seconds` null and the next pass one interval on, because `recover` is the one task kept
 * on its cadence through an outage (`NO_BACKOFF_TASKS`). Every timestamp is measured from the fixed
 * clock, so "updated 40 minutes ago" is what the page says whatever hour the suite runs.
 */
function providerUnreachableStatus(): ProviderStatusPayload {
  const status = baseStatus();
  for (const entry of status.chain || []) {
    entry.last_success_at = at(-40 * MINUTE);
    entry.last_error_at = at(-4 * MINUTE);
    entry.last_error = NETWORK_ERROR;
  }
  status.scheduler = {
    ...status.scheduler!,
    enabled_tasks: ['fixtures', 'live', 'results', 'recover', 'forecasts'],
    tasks: {
      fixtures: taskAt(21_600, 2 * HOUR, 4 * HOUR),
      live: taskAt(120, 40 * MINUTE, 1 * MINUTE),
      results: taskAt(1800, 40 * MINUTE, 20 * MINUTE),
      recover: taskAt(1800, 70 * MINUTE, 26 * MINUTE, {
        last_run_at: at(-4 * MINUTE),
        last_error_at: at(-4 * MINUTE),
        last_error: `reached no provider with an answer about any of the 1 stranded fixtures: ${NETWORK_ERROR}`,
        failures: 1,
        consecutive_failures: 1,
        backoff_seconds: null,
      }),
      forecasts: taskAt(21_600, 2 * HOUR, 4 * HOUR),
    },
  };
  return status;
}

/* --------------------------------------------------------------------------- the stubbed day */

interface Asked {
  days: string[];
  refreshed: string[];
}

async function stubDay(
  page: Page, language: Language, matches: ApiMatch[] = ALL, status?: ProviderStatusPayload,
): Promise<Asked> {
  const asked: Asked = { days: [], refreshed: [] };

  await page.clock.install({ time: NOW });
  // Jumped, never stopped: a frozen clock would also freeze what this file is not about.
  await page.clock.resume();
  await page.addInitScript(([key, value]) => {
    window.localStorage.setItem(key, value);
  }, [LANGUAGE_KEY, language] as const);

  await stubBackend(page, {
    /*
     * The fixtures are returned whatever day is asked for, and the day asked for is RECORDED so a
     * test can still hold the page to its own calendar. Re-timing them onto the requested date
     * (which `dayPayload` does) would destroy the very thing under test: these kickoffs are hours
     * and hours in the past on purpose.
     */
    day: (isoDate, params) => {
      asked.days.push(isoDate);
      if (params.get('refresh') === 'true') asked.refreshed.push(isoDate);
      return { ...baseDayPayload(), date: isoDate, matches };
    },
    matchById: id => matches.find(match => match.id === id) ?? null,
    status,
  });
  return asked;
}

const row = (page: Page, matchId: string) =>
  page.locator(`[data-testid="fixture-row"][data-match-id="${matchId}"]`);

/* ================================================================================ THE DAY LIST */

for (const language of ['en', 'fr'] as const) {
  test(`[${language}] the day list says a result is overdue where the kickoff time would be`, async ({ page }) => {
    const problems = watchForProblems(page);
    await stubDay(page, language);
    await page.goto('/matches');

    const late = row(page, OVERDUE.id);
    await expect(late).toBeVisible();

    const label = late.getByTestId('result-delay-label');
    await expect(label, 'the row must name the state where its status would be')
      .toHaveText(say(language, 'fixture.result.overdue'));
    await expect(label).toHaveAttribute('data-result-delay', 'overdue');
    await expect(late.getByTestId('result-delay-line')).toHaveText(overdueShort(language));

    /*
     * The hover and screen-reader text behind that one short word. The column holds neither the
     * fixture nor the deadline, so both belong here: the fixture because "Result overdue" on its
     * own does not say which match, and the exact deadline because it is what a reader checks the
     * claim against. The clock pattern is asserted rather than a formatted instant — the format is
     * the reader's locale's business, and having a time in there at all is the thing that was
     * missing.
     */
    const title = await label.getAttribute('title');
    expect(title, 'the label offers no title at all').not.toBeNull();
    expect(title).toContain(say(language, 'fixture.versus', { home: 'Andorra', away: 'Malta' }));
    expect(title).toContain(say(language, 'fixture.result.overdue'));
    expect(title, 'the title names no time, so the claim cannot be checked').toMatch(/\d{1,2}:\d{2}/);

    /*
     * The three things the row must no longer say. Each was on screen before this change: the
     * word LIVE, the minute HT, and a 0-0 the provider sent at half time and nobody has since
     * called a result.
     */
    await expect(late, 'a match past its deadline may not be called live')
      .not.toContainText(say(language, 'fixture.live'));
    await expect(late, 'the stored minute is not the minute a stopped match is at')
      .not.toContainText('HT');
    await expect(late.getByTestId('fixture-row-score'),
      'no score is presented for a match whose result never arrived').toHaveCount(0);
    await expect(late, 'nothing here is full time').not.toContainText(say(language, 'fixture.ft'));

    // And it is the overdue wording, not the other state's.
    await expect(late).not.toContainText(say(language, 'fixture.result.givenUp'));

    expect(problems.consoleErrors, 'the page logged errors').toEqual([]);
  });

  test(`[${language}] the day list distinguishes a fixture that has been given up on`, async ({ page }) => {
    await stubDay(page, language);
    await page.goto('/matches');

    const abandoned = row(page, GIVEN_UP.id);
    await expect(abandoned).toBeVisible();

    const label = abandoned.getByTestId('result-delay-label');
    await expect(label).toHaveText(say(language, 'fixture.result.givenUp'));
    await expect(label).toHaveAttribute('data-result-delay', 'given_up');

    // "We stopped asking two hours ago" — the fact that separates this row from the one above, and
    // the one fact that cannot be worked out from a clock.
    await expect(abandoned.getByTestId('result-delay-line'))
      .toHaveText(say(language, 'fixture.result.givenUpShort',
        { when: agoPhrase(language, GAVE_UP_HOURS) }));
    await expect(abandoned, 'an abandoned fixture must not be described as merely late')
      .not.toContainText(say(language, 'fixture.result.overdue'));

    /*
     * A SCHEDULED row's kickoff time is the other half of the defect: seventeen hours after the
     * match was due, the column still offered it as though it were about to start. 02:00 is that
     * kickoff in the context's own zone.
     */
    await expect(abandoned, 'a kickoff time that has passed is not a fixture to come')
      .not.toContainText('02:00');
    await expect(abandoned.getByTestId('fixture-row-score')).toHaveCount(0);
  });

  test(`[${language}] THE MATCH THAT IS GENUINELY IN PLAY keeps its running minute and its score`, async ({ page }) => {
    await stubDay(page, language);
    await page.goto('/matches');

    const playing = row(page, IN_PLAY.id);
    await expect(playing).toBeVisible();

    await expect(playing, 'a match inside the live window is live')
      .toContainText(say(language, 'fixture.live'));
    await expect(playing, 'and shows the minute it is at').toContainText('63');
    await expect(playing.getByTestId('fixture-row-score'),
      'both sides of a live scoreline are still shown').toHaveCount(2);
    await expect(playing.getByTestId('result-delay-label'),
      'a live match is not overdue for anything').toHaveCount(0);
    await expect(playing.getByTestId('result-delay-line')).toHaveCount(0);
  });

  test(`[${language}] A TIE PLAYED PAST THE DEADLINE KEEPS ITS MINUTE AND ITS SCORE`, async ({ page }) => {
    const problems = watchForProblems(page);
    // The stuck fixture is on the same screen on purpose: these three rows are all past the
    // deadline, and the row that has stopped moving is the only one that may be quietened.
    await stubDay(page, language, [EXTRA_TIME, SHOOTOUT, OVERDUE]);
    await page.goto('/matches');

    for (const [playing, minute, home, away] of [
      [row(page, EXTRA_TIME.id), '105', '1', '1'],
      [row(page, SHOOTOUT.id), 'PEN', '2', '2'],
    ] as const) {
      await expect(playing).toBeVisible();
      await expect(playing, 'a match reporting play in progress is in play, whatever the clock says')
        .toContainText(say(language, 'fixture.live'));
      await expect(playing, 'the minute it is at belongs to the reader').toContainText(minute);
      const scores = playing.getByTestId('fixture-row-score');
      await expect(scores, 'both sides of a running scoreline are still shown').toHaveCount(2);
      await expect(scores.first()).toHaveText(home);
      await expect(scores.last()).toHaveText(away);
      await expect(playing.getByTestId('result-delay-label'),
        'a result is not overdue for a match that is being played').toHaveCount(0);
      await expect(playing.getByTestId('result-delay-line')).toHaveCount(0);
    }

    // And the fixture that really did stop is still caught, on the same screen and the same clock.
    await expect(row(page, OVERDUE.id).getByTestId('result-delay-label'))
      .toHaveText(say(language, 'fixture.result.overdue'));

    expect(problems.consoleErrors, 'the page logged errors').toEqual([]);
  });
}

/* ============================================== AN OUTAGE AND AN EMPTY ANSWER ARE NOT ONE THING */

for (const language of ['en', 'fr'] as const) {
  test(`[${language}] the day list tells an unreachable provider apart from an empty answer`, async ({ page }) => {
    const problems = watchForProblems(page);
    await stubDay(page, language, [OVERDUE_UNREACHABLE, OVERDUE_ANSWERED, IN_PLAY]);
    await page.goto('/matches');

    // Both are overdue — the label is the same, because both results are late and still asked for.
    const unreachable = row(page, OVERDUE_UNREACHABLE.id);
    const answered = row(page, OVERDUE_ANSWERED.id);
    for (const late of [unreachable, answered]) {
      await expect(late.getByTestId('result-delay-label')).toHaveText(say(language, 'fixture.result.overdue'));
      await expect(late.getByTestId('fixture-row-score')).toHaveCount(0);
      await expect(late, 'still being asked about, so not unresolved')
        .not.toContainText(say(language, 'fixture.result.givenUp'));
      expect(await late.innerText()).not.toMatch(OVERCLAIM);
    }

    // And the line under each says which of the two it is.
    await expect(unreachable.getByTestId('result-delay-line')).toHaveAttribute('data-last-check', 'unreachable');
    await expect(unreachable.getByTestId('result-delay-line'))
      .toHaveText(say(language, 'fixture.result.unreachableShort', { due: agoPhrase(language, 2) }));
    await expect(answered.getByTestId('result-delay-line')).toHaveAttribute('data-last-check', 'answered_empty');
    await expect(answered.getByTestId('result-delay-line'))
      .toHaveText(say(language, 'fixture.result.overdueShort', { due: agoPhrase(language, 2) }));

    // The live match on the same screen is untouched by either.
    const playing = row(page, IN_PLAY.id);
    await expect(playing).toContainText(say(language, 'fixture.live'));
    await expect(playing).toContainText('63');
    await expect(playing.getByTestId('fixture-row-score')).toHaveCount(2);

    expect(problems.consoleErrors, 'the page logged errors').toEqual([]);
  });

  test(`[${language}] the match page says what the last check found, and only what it found`, async ({ page }) => {
    await stubDay(page, language, [OVERDUE_UNREACHABLE, OVERDUE_ANSWERED]);

    await page.goto(`/match/${OVERDUE_ANSWERED.id}`);
    let notice = page.getByTestId('result-delay-notice');
    await expect(notice).toHaveAttribute('data-result-delay', 'overdue');
    await expect(notice.getByTestId('result-delay-last-check')).toHaveAttribute('data-last-check', 'answered_empty');
    await expect(notice.getByTestId('result-delay-last-check')).toHaveText(
      say(language, 'fixture.result.lastCheckEmpty', { when: minutesAgoPhrase(language, LAST_CHECK_MINUTES) }));
    await expect(notice.getByTestId('result-delay-asking')).toHaveText(say(language, 'fixture.result.stillAsking'));
    await expect(notice.getByTestId('result-delay-policy'), 'still asking, so nothing to explain').toHaveCount(0);
    expect(await notice.innerText()).not.toMatch(OVERCLAIM);

    await page.goto(`/match/${OVERDUE_UNREACHABLE.id}`);
    notice = page.getByTestId('result-delay-notice');
    await expect(notice).toHaveAttribute('data-result-delay', 'overdue');
    await expect(notice.getByTestId('result-delay-last-check')).toHaveAttribute('data-last-check', 'unreachable');
    await expect(notice.getByTestId('result-delay-last-check')).toHaveText(
      say(language, 'fixture.result.lastCheckUnreachable', { when: minutesAgoPhrase(language, LAST_CHECK_MINUTES) }));
    // An outage is not a reason to stop, and the notice says we have not.
    await expect(notice.getByTestId('result-delay-asking')).toHaveText(say(language, 'fixture.result.stillAsking'));
    // An outage is not an answer: nothing here says the provider had no result.
    await expect(notice).not.toContainText(say(language, 'fixture.result.lastCheckEmpty', {
      when: minutesAgoPhrase(language, LAST_CHECK_MINUTES),
    }));
    await expect(notice.getByTestId('result-delay-attempts')).toHaveCount(0);
    expect(await page.getByTestId('match-scoreline').innerText(), 'the 1-0 at 52 minutes is not a result')
      .not.toMatch(/\d/);
  });
}

/* ===================================================== THE FOUR THINGS A READER CAN BE TOLD */

/**
 * Every sentence these states can put on a page, in one language, with representative values.
 *
 * Rendered through the application's own formatter from the application's own catalogue, so this
 * is the text a reader gets and not a copy of it.
 */
function everyDelaySentence(language: Language): Record<string, string> {
  const due = agoPhrase(language, 2);
  const when = minutesAgoPhrase(language, LAST_CHECK_MINUTES);
  return {
    overdue: say(language, 'fixture.result.overdue'),
    givenUp: say(language, 'fixture.result.givenUp'),
    overdueShort: say(language, 'fixture.result.overdueShort', { due }),
    unreachableShort: say(language, 'fixture.result.unreachableShort', { due }),
    heldBackShort: say(language, 'fixture.result.heldBackShort', { due }),
    heldBackProviderShort: say(language, 'fixture.result.heldBackProviderShort', { due }),
    heldBackCoolingShort: say(language, 'fixture.result.heldBackCoolingShort', { due }),
    heldBackOtherShort: say(language, 'fixture.result.heldBackOtherShort', { due }),
    givenUpShort: say(language, 'fixture.result.givenUpShort', { when }),
    overdueDetail: say(language, 'fixture.result.overdueDetail', { due }),
    givenUpDetail: say(language, 'fixture.result.givenUpDetail', { when }),
    stillAsking: say(language, 'fixture.result.stillAsking'),
    lastCheckUnreachable: say(language, 'fixture.result.lastCheckUnreachable', { when }),
    lastCheckEmpty: say(language, 'fixture.result.lastCheckEmpty', { when }),
    lastCheckHeldBack: say(language, 'fixture.result.lastCheckHeldBack', { when }),
    lastCheckHeldBackProvider: say(language, 'fixture.result.lastCheckHeldBackProvider', { when }),
    lastCheckHeldBackCooling: say(language, 'fixture.result.lastCheckHeldBackCooling', { when }),
    lastCheckHeldBackOther: say(language, 'fixture.result.lastCheckHeldBackOther', { when }),
    lastCheckStoredCopy: say(language, 'fixture.result.lastCheckStoredCopy', { when }),
    attempts: say(language, 'fixture.result.attempts', { count: 3 }),
    givenUpPolicy: say(language, 'fixture.result.givenUpPolicy'),
    givenUpOtherPolicy: say(language, 'fixture.result.givenUpOtherPolicy'),
  };
}

/**
 * The words that attribute a limit to US — "our own request allowance", in both languages.
 *
 * Only a check held back by our own allowance, and only a stop the retry budget made, may use
 * them. The provider's limit is not ours, a cool-down is not a limit, and a stop made by a rule
 * that has since been removed was not made by the allowance.
 */
const OUR_ALLOWANCE = /our own request allowance|own request allowance|notre propre quota/i;

for (const language of ['en', 'fr'] as const) {
  test(`[${language}] no sentence in the catalogue says a result cannot exist, and a held-back check names no failure`, () => {
    const said = everyDelaySentence(language);

    for (const [key, sentence] of Object.entries(said)) {
      expect(sentence, `${key} is empty in ${language}`).not.toEqual('');
      expect(sentence, `${key} claims more than we know`).not.toMatch(OVERCLAIM);
      expect(sentence, `${key} carries operator prose`).not.toMatch(OPERATOR_PROSE);
    }

    // Held back by our own allowance: not a failure, and not worded as one.
    expect(said.heldBackShort).not.toMatch(FAILURE_WORDS);
    expect(said.lastCheckHeldBack).not.toMatch(FAILURE_WORDS);
    // Not sent because of the PROVIDER's limit, or for a reason not stated: no failure either.
    for (const key of ['heldBackProviderShort', 'lastCheckHeldBackProvider',
      'heldBackOtherShort', 'lastCheckHeldBackOther'] as const) {
      expect(said[key], `${key} words a check that never left as a failure`).not.toMatch(FAILURE_WORDS);
    }
    // Only our own allowance is worded as ours - for checks and for stops alike.
    expect(said.heldBackShort).toMatch(OUR_ALLOWANCE);
    expect(said.lastCheckHeldBack).toMatch(OUR_ALLOWANCE);
    expect(said.givenUpPolicy).toMatch(OUR_ALLOWANCE);
    for (const key of ['heldBackProviderShort', 'lastCheckHeldBackProvider', 'heldBackCoolingShort',
      'lastCheckHeldBackCooling', 'heldBackOtherShort', 'lastCheckHeldBackOther',
      'givenUpOtherPolicy'] as const) {
      expect(said[key], `${key} calls a limit that was not ours our own`).not.toMatch(OUR_ALLOWANCE);
    }
    // And the pattern that says so can see a failure when there is one.
    expect(said.unreachableShort).toMatch(FAILURE_WORDS);
    expect(said.lastCheckUnreachable).toMatch(FAILURE_WORDS);
    // Still asking is not a failure either, and neither is stopping.
    expect(said.stillAsking).not.toMatch(FAILURE_WORDS);
    expect(said.givenUpPolicy).not.toMatch(FAILURE_WORDS);

    // The four row lines are four different sentences — no two states share words on the row.
    const rowLines = [said.overdueShort, said.unreachableShort, said.heldBackShort, said.heldBackProviderShort,
      said.heldBackCoolingShort, said.heldBackOtherShort, said.givenUpShort];
    expect(new Set(rowLines).size, 'two states share a row sentence').toBe(rowLines.length);
    // And the four last-check findings likewise.
    const findings = [said.lastCheckUnreachable, said.lastCheckEmpty, said.lastCheckHeldBack,
      said.lastCheckHeldBackProvider, said.lastCheckHeldBackCooling, said.lastCheckHeldBackOther,
      said.lastCheckStoredCopy];
    expect(new Set(findings).size, 'two findings share a sentence').toBe(findings.length);
  });

  test(`[${language}] THE FOUR THINGS A READER CAN BE TOLD, on one day list beside a live match and a tie in extra time`, async ({ page }) => {
    const problems = watchForProblems(page);
    await stubDay(page, language,
      [OVERDUE_ANSWERED, OVERDUE_UNREACHABLE, OVERDUE_HELD_BACK, OWNER_CHECKED, IN_PLAY, EXTRA_TIME]);
    await page.goto('/matches');
    const said = everyDelaySentence(language);

    /*
     * One row per state, each with its own label, its own sentence and its own marker. The three
     * overdue rows share the label — all three results are late and still asked for — and differ
     * in the one thing the row has room to say: what the last check found.
     */
    const cases = [
      { match: OVERDUE_ANSWERED, state: 'overdue', check: 'answered_empty', line: said.overdueShort },
      { match: OVERDUE_UNREACHABLE, state: 'overdue', check: 'unreachable', line: said.unreachableShort },
      { match: OVERDUE_HELD_BACK, state: 'overdue', check: 'held_back', line: said.heldBackShort },
      {
        match: OWNER_CHECKED, state: 'given_up', check: 'answered_empty',
        line: say(language, 'fixture.result.givenUpShort', { when: agoPhrase(language, GAVE_UP_HOURS) }),
      },
    ] as const;

    for (const { match, state, check, line } of cases) {
      const stuck = row(page, match.id);
      await expect(stuck).toBeVisible();
      await expect(stuck.getByTestId('result-delay-label'))
        .toHaveText(state === 'given_up' ? said.givenUp : said.overdue);
      await expect(stuck.getByTestId('result-delay-label')).toHaveAttribute('data-result-delay', state);
      await expect(stuck.getByTestId('result-delay-line'), `${match.id} says the wrong sentence`).toHaveText(line);
      await expect(stuck.getByTestId('result-delay-line')).toHaveAttribute('data-last-check', check);
      // Each row says its own sentence and no other row's.
      for (const other of cases) {
        if (other.line !== line) await expect(stuck).not.toContainText(other.line);
      }
      await expect(stuck.getByTestId('fixture-row-score'), 'a late row carries no score').toHaveCount(0);
      await expect(stuck).not.toContainText(say(language, 'fixture.live'));
      const text = await stuck.innerText();
      expect(text).not.toMatch(OVERCLAIM);
      expect(text).not.toMatch(OPERATOR_PROSE);
      // The club names stay on the row at this width: the sentence may wrap, not push them out.
      await expect(stuck.getByText(match.home!.name, { exact: true })).toBeVisible();
      await expect(stuck.getByText(match.away!.name, { exact: true })).toBeVisible();
    }

    // The held-back row in particular names no failure, and the unreachable row does.
    expect(await row(page, OVERDUE_HELD_BACK.id).getByTestId('result-delay-line').innerText())
      .not.toMatch(FAILURE_WORDS);
    expect(await row(page, OVERDUE_UNREACHABLE.id).getByTestId('result-delay-line').innerText())
      .toMatch(FAILURE_WORDS);

    // The match being played and the tie in extra time keep everything they had.
    for (const [playing, minute, home, away] of [
      [row(page, IN_PLAY.id), '63', '2', '1'],
      [row(page, EXTRA_TIME.id), '105', '1', '1'],
    ] as const) {
      await expect(playing).toContainText(say(language, 'fixture.live'));
      await expect(playing, 'the running minute belongs to a running match').toContainText(minute);
      const scores = playing.getByTestId('fixture-row-score');
      await expect(scores).toHaveCount(2);
      await expect(scores.first()).toHaveText(home);
      await expect(scores.last()).toHaveText(away);
      await expect(playing.getByTestId('result-delay-label')).toHaveCount(0);
      await expect(playing.getByTestId('result-delay-line')).toHaveCount(0);
    }

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, 'the day list scrolls sideways at this width').toBeLessThanOrEqual(0);
    expect(problems.consoleErrors, 'the page logged errors').toEqual([]);
  });

  test(`[${language}] a check held back by our own allowance is said as ours, and not as the provider's failure`, async ({ page }) => {
    const problems = watchForProblems(page);
    await stubDay(page, language, [OVERDUE_HELD_BACK]);
    await page.goto(`/match/${OVERDUE_HELD_BACK.id}`);
    const said = everyDelaySentence(language);

    const notice = page.getByTestId('result-delay-notice');
    await expect(notice).toHaveAttribute('data-result-delay', 'overdue');
    await expect(notice.getByTestId('result-delay-detail')).toHaveText(said.overdueDetail);
    await expect(notice.getByTestId('result-delay-asking'), 'a deferred fixture stays due')
      .toHaveText(said.stillAsking);
    const check = notice.getByTestId('result-delay-last-check');
    await expect(check).toHaveAttribute('data-last-check', 'held_back');
    await expect(check).toHaveText(said.lastCheckHeldBack);
    expect(await check.innerText(), 'a held-back check is worded as a failure').not.toMatch(FAILURE_WORDS);

    // None of the outage's words, anywhere on the page, and nothing about stopping.
    await expect(page.locator('body')).not.toContainText(said.lastCheckUnreachable);
    await expect(page.locator('body')).not.toContainText(said.unreachableShort);
    await expect(notice).not.toContainText(said.givenUp);
    await expect(notice.getByTestId('result-delay-policy'), 'nothing was stopped').toHaveCount(0);
    await expect(notice.getByTestId('result-delay-attempts')).toHaveCount(0);
    expect(await notice.innerText()).not.toMatch(OVERCLAIM);

    expect(await page.getByTestId('match-scoreline').innerText(), 'the 2-1 at 71 minutes is not a result')
      .not.toMatch(/\d/);
    expect(problems.consoleErrors, 'the page logged errors').toEqual([]);
  });

  test(`[${language}] a check that never left is worded by WHY it never left: only our own allowance is called ours`, async ({ page }) => {
    const problems = watchForProblems(page);
    const cases = [
      { match: OVERDUE_HELD_BACK, short: 'fixture.result.heldBackShort', sentence: 'fixture.result.lastCheckHeldBack', ours: true },
      { match: OVERDUE_PROVIDER_LIMIT, short: 'fixture.result.heldBackProviderShort', sentence: 'fixture.result.lastCheckHeldBackProvider', ours: false },
      { match: OVERDUE_COOLING, short: 'fixture.result.heldBackCoolingShort', sentence: 'fixture.result.lastCheckHeldBackCooling', ours: false },
      { match: OVERDUE_DEFERRED_UNSTATED, short: 'fixture.result.heldBackOtherShort', sentence: 'fixture.result.lastCheckHeldBackOther', ours: false },
    ] as const;
    await stubDay(page, language, cases.map((c) => c.match));
    await page.goto('/matches');
    // Each kicked off four hours ago, so its deadline (kickoff + 150 min) was 90 minutes ago,
    // which `relativeTime` rounds to 2 hours - as for the four-hour rows above.
    const due = agoPhrase(language, 2);
    const when = minutesAgoPhrase(language, LAST_CHECK_MINUTES);

    // The row: one sentence per cause, each the catalogue's, and none borrowing another's.
    for (const { match, short, ours } of cases) {
      const line = row(page, match.id).getByTestId('result-delay-line');
      await expect(line).toHaveAttribute('data-last-check', 'held_back');
      await expect(line, `${match.id} says the wrong sentence`).toHaveText(say(language, short, { due }));
      const text = await line.innerText();
      if (ours) expect(text).toMatch(OUR_ALLOWANCE);
      else expect(text, `${match.id} calls a limit that was not ours our own`).not.toMatch(OUR_ALLOWANCE);
      await expect(row(page, match.id).getByTestId('fixture-row-score'), 'a late row carries no score').toHaveCount(0);
    }

    // The page: the same cause, in the full sentence, with the fixture still due.
    for (const { match, sentence, ours } of cases) {
      await page.goto(`/match/${match.id}`);
      const notice = page.getByTestId('result-delay-notice');
      await expect(notice).toHaveAttribute('data-result-delay', 'overdue');
      await expect(notice.getByTestId('result-delay-asking'), 'a deferred fixture stays due')
        .toHaveText(say(language, 'fixture.result.stillAsking'));
      const check = notice.getByTestId('result-delay-last-check');
      await expect(check).toHaveAttribute('data-last-check', 'held_back');
      await expect(check).toHaveText(say(language, sentence, { when }));
      const text = await notice.innerText();
      if (!ours) expect(text, `${match.id}: the notice credits the limit to us`).not.toMatch(OUR_ALLOWANCE);
      // Not an outage: the outage's own sentence is nowhere, and nothing was stopped.
      await expect(notice).not.toContainText(say(language, 'fixture.result.lastCheckUnreachable', { when }));
      await expect(notice.getByTestId('result-delay-policy')).toHaveCount(0);
      expect(text).not.toMatch(OVERCLAIM);
      expect(await page.getByTestId('match-scoreline').innerText(), 'an in-play score is not a result')
        .not.toMatch(/\d/);
    }
    expect(problems.consoleErrors, 'the page logged errors').toEqual([]);
  });

  test(`[${language}] a stop the retry budget made says it was our allowance; the backend's prose stays off the page`, async ({ page }) => {
    await stubDay(page, language, [BUDGET_STOPPED]);
    await page.goto(`/match/${BUDGET_STOPPED.id}`);

    const notice = page.getByTestId('result-delay-notice');
    await expect(notice).toHaveAttribute('data-result-delay', 'given_up');
    await expect(notice.getByTestId('result-delay-detail')).toHaveText(givenUpDetail(language));
    await expect(notice.getByTestId('result-delay-attempts'))
      .toHaveText(say(language, 'fixture.result.attempts', { count: 11 }));
    await expect(notice.getByTestId('result-delay-policy'))
      .toHaveText(say(language, 'fixture.result.givenUpPolicy'));
    await expect(notice.getByTestId('result-delay-asking'), 'we stopped, so we are not still asking')
      .toHaveCount(0);
    const text = await notice.innerText();
    expect(text).not.toMatch(OPERATOR_PROSE);
    expect(text).not.toMatch(OVERCLAIM);
    await expect(page.locator('body')).not.toContainText('14-day results horizon');
    expect(await page.getByTestId('match-scoreline').innerText(), 'the 2-2 at half time is not a result')
      .not.toMatch(/\d/);
  });

  test(`[${language}] a check that read our own stored copy says so, and claims no call`, async ({ page }) => {
    await stubDay(page, language, [OVERDUE_STORED_COPY]);
    await page.goto(`/match/${OVERDUE_STORED_COPY.id}`);
    const said = everyDelaySentence(language);

    const notice = page.getByTestId('result-delay-notice');
    await expect(notice).toHaveAttribute('data-result-delay', 'overdue');
    await expect(notice.getByTestId('result-delay-asking')).toHaveText(said.stillAsking);
    const check = notice.getByTestId('result-delay-last-check');
    await expect(check).toHaveAttribute('data-last-check', 'stored_copy');
    await expect(check).toHaveText(said.lastCheckStoredCopy);
    expect(await check.innerText()).not.toMatch(FAILURE_WORDS);
    // Not an answer from the provider either: this pass asked nobody.
    await expect(notice).not.toContainText(said.lastCheckEmpty);
    await expect(notice.getByTestId('result-delay-policy')).toHaveCount(0);
    expect(await notice.innerText()).not.toMatch(OVERCLAIM);
  });

  test(`[${language}] a fixture put back under the retry schedule reads overdue and still asked about, not Unresolved`, async ({ page }) => {
    const problems = watchForProblems(page);
    await stubDay(page, language, [PUT_BACK, IN_PLAY]);
    await page.goto('/matches');
    const said = everyDelaySentence(language);

    // Its kickoff was 7h29m ago, so its result fell due 4h59m ago: "5 hours ago" on the row.
    const back = row(page, PUT_BACK.id);
    await expect(back.getByTestId('result-delay-label')).toHaveText(said.overdue);
    await expect(back.getByTestId('result-delay-label')).toHaveAttribute('data-result-delay', 'overdue');
    await expect(back.getByTestId('result-delay-line'))
      .toHaveText(say(language, 'fixture.result.overdueShort', { due: agoPhrase(language, 5) }));
    await expect(back, 'a fixture being asked about again is not unresolved').not.toContainText(said.givenUp);
    await expect(back.getByTestId('fixture-row-score')).toHaveCount(0);
    await expect(back).not.toContainText('HT');

    const playing = row(page, IN_PLAY.id);
    await expect(playing).toContainText('63');
    await expect(playing.getByTestId('fixture-row-score')).toHaveCount(2);

    await page.goto(`/match/${PUT_BACK.id}`);
    const notice = page.getByTestId('result-delay-notice');
    await expect(notice).toHaveAttribute('data-result-delay', 'overdue');
    await expect(notice.getByTestId('result-delay-detail'))
      .toHaveText(say(language, 'fixture.result.overdueDetail', { due: agoPhrase(language, 5) }));
    await expect(notice.getByTestId('result-delay-asking'), 'it is being asked about again')
      .toHaveText(said.stillAsking);
    await expect(notice.getByTestId('result-delay-last-check'))
      .toHaveText(say(language, 'fixture.result.lastCheckEmpty', { when: agoPhrase(language, GAVE_UP_HOURS) }));
    // Nothing about stopping survives the stop being undone.
    await expect(notice).not.toContainText(said.givenUp);
    await expect(notice.getByTestId('result-delay-policy')).toHaveCount(0);
    await expect(notice.getByTestId('result-delay-attempts')).toHaveCount(0);
    const text = await notice.innerText();
    expect(text).not.toMatch(OVERCLAIM);
    expect(text).not.toMatch(OPERATOR_PROSE);
    expect(await page.getByTestId('match-scoreline').innerText()).not.toMatch(/\d/);
    expect(problems.consoleErrors, 'the page logged errors').toEqual([]);
  });

  test(`[${language}] an outcome with no sentence of its own adds none, and the overdue statement stands`, async ({ page }) => {
    await stubDay(page, language, [RECOVERED_BUT_UNSETTLED, UNKNOWN_OUTCOME]);
    const said = everyDelaySentence(language);

    for (const match of [RECOVERED_BUT_UNSETTLED, UNKNOWN_OUTCOME]) {
      await page.goto(`/match/${match.id}`);
      const notice = page.getByTestId('result-delay-notice');
      await expect(notice).toHaveAttribute('data-result-delay', 'overdue');
      await expect(notice.getByTestId('result-delay-asking')).toHaveText(said.stillAsking);
      await expect(notice.getByTestId('result-delay-last-check'),
        `${match.id}: an outcome given no words got some`).toHaveCount(0);
      await expect(notice).not.toContainText('some_outcome_this_build_never_heard_of');
      await expect(notice).not.toContainText(/recovered/i);
      expect(await notice.innerText()).not.toMatch(OVERCLAIM);
      expect(await page.getByTestId('match-scoreline').innerText(), 'a record saying "recovered" is not a score')
        .not.toMatch(/\d/);
    }
  });
}

/* =========================================================================== THE MATCH PAGE */

for (const language of ['en', 'fr'] as const) {
  test(`[${language}] the match page states an overdue result instead of a scoreline`, async ({ page }) => {
    await stubDay(page, language);
    await page.goto(`/match/${OVERDUE.id}`);

    const notice = page.getByTestId('result-delay-notice');
    await expect(notice).toBeVisible();
    await expect(notice).toHaveAttribute('data-result-delay', 'overdue');
    await expect(notice.getByTestId('result-delay-detail')).toHaveText(overdueDetail(language));

    // Nothing was chased, so nothing about chasing is claimed — and nothing was stopped, so the
    // sentence about why we stop has nothing to explain.
    await expect(notice.getByTestId('result-delay-attempts')).toHaveCount(0);
    await expect(notice.getByTestId('result-delay-policy')).toHaveCount(0);
    /*
     * And no claim about asking, either way. This row carries NO recovery record, and the backend
     * does not start on every such fixture (one older than its retry horizon never gets one), so
     * "we are still asking" would be a guess — and "we stopped" would be false.
     */
    await expect(notice.getByTestId('result-delay-asking')).toHaveCount(0);

    /*
     * The scoreline block is the element that used to carry a green 0-0 under a pulsing LIVE
     * badge. It may hold the state's name and no digits at all.
     */
    const scoreline = page.getByTestId('match-scoreline');
    await expect(scoreline).toContainText(say(language, 'fixture.result.overdue'));
    expect(await scoreline.innerText(), 'the scoreline block still contains a number')
      .not.toMatch(/\d/);
    await expect(page.getByTestId('match-score-period')).toHaveCount(0);
  });

  test(`[${language}] the match page says how often the provider answered, and does not credit a removed rule's stop to our allowance`, async ({ page }) => {
    await stubDay(page, language);
    await page.goto(`/match/${GIVEN_UP.id}`);

    const notice = page.getByTestId('result-delay-notice');
    await expect(notice).toBeVisible();
    await expect(notice).toHaveAttribute('data-result-delay', 'given_up');
    await expect(notice.getByTestId('result-delay-detail')).toHaveText(givenUpDetail(language));
    await expect(notice.getByTestId('result-delay-attempts'))
      .toHaveText(say(language, 'fixture.result.attempts', { count: 3 }));
    /*
     * This row is in the narrow shape of a backend that predates `stopped_by`, stopped by the
     * three-attempts rule. That rule was not the retry budget, so the sentence names no policy.
     */
    await expect(notice.getByTestId('result-delay-policy'))
      .toHaveText(say(language, 'fixture.result.givenUpOtherPolicy'));
    expect(await notice.innerText()).not.toMatch(OUR_ALLOWANCE);
    await expect(notice.getByTestId('result-delay-asking'), 'we stopped, so we are not still asking')
      .toHaveCount(0);

    /*
     * The backend's `gave_up_reason` — "no result after 3 attempts" on this row — is operator
     * prose in English, and it is not on the page in either language. The count above is the same
     * fact, read from a number and said in the reader's words.
     */
    await expect(notice.getByTestId('result-delay-reason')).toHaveCount(0);
    expect(await notice.innerText()).not.toMatch(OPERATOR_PROSE);

    const scoreline = page.getByTestId('match-scoreline');
    await expect(scoreline).toContainText(say(language, 'fixture.result.givenUp'));
    expect(await scoreline.innerText()).not.toMatch(/\d/);
  });

  test(`[${language}] THE UNRESOLVED STATE THE OWNER CHECKED reads Unresolved on its row and its page`, async ({ page }) => {
    const problems = watchForProblems(page);
    await stubDay(page, language, [OWNER_CHECKED, IN_PLAY]);
    await page.goto('/matches');

    // The row: the state's name where LIVE and HT used to be, and no 1-1 anywhere on it.
    const stuck = row(page, OWNER_CHECKED.id);
    await expect(stuck).toBeVisible();
    await expect(stuck.getByTestId('result-delay-label')).toHaveText(say(language, 'fixture.result.givenUp'));
    await expect(stuck.getByTestId('result-delay-line'))
      .toHaveText(say(language, 'fixture.result.givenUpShort', { when: agoPhrase(language, GAVE_UP_HOURS) }));
    await expect(stuck.getByTestId('fixture-row-score')).toHaveCount(0);
    await expect(stuck).not.toContainText(say(language, 'fixture.live'));
    await expect(stuck).not.toContainText('HT');
    expect(await stuck.innerText()).not.toMatch(OVERCLAIM);
    expect(await stuck.innerText()).not.toMatch(OPERATOR_PROSE);

    // And the match being played beside it keeps everything it had.
    const playing = row(page, IN_PLAY.id);
    await expect(playing).toContainText(say(language, 'fixture.live'));
    await expect(playing).toContainText('63');
    await expect(playing.getByTestId('fixture-row-score')).toHaveCount(2);

    // The page: every line of the notice, and nothing beside it.
    await page.goto(`/match/${OWNER_CHECKED.id}`);
    const notice = page.getByTestId('result-delay-notice');
    await expect(notice).toHaveAttribute('data-result-delay', 'given_up');
    await expect(notice.getByTestId('result-delay-detail')).toHaveText(givenUpDetail(language));
    await expect(notice.getByTestId('result-delay-attempts'))
      .toHaveText(say(language, 'fixture.result.attempts', { count: 3 }));
    // `stopped_by: null` — the three-attempts rule made this stop, not the retry budget.
    await expect(notice.getByTestId('result-delay-policy'))
      .toHaveText(say(language, 'fixture.result.givenUpOtherPolicy'));
    // The last pass was an empty answer, and the attempts line already says that with a count.
    await expect(notice.getByTestId('result-delay-last-check')).toHaveCount(0);
    await expect(notice.getByTestId('result-delay-asking'), 'we stopped, so we are not still asking')
      .toHaveCount(0);
    const said = await notice.innerText();
    expect(said, 'the notice repeats operator prose').not.toMatch(OPERATOR_PROSE);
    expect(said, 'the notice claims more than that we stopped asking').not.toMatch(OVERCLAIM);

    const scoreline = page.getByTestId('match-scoreline');
    await expect(scoreline).toContainText(say(language, 'fixture.result.givenUp'));
    expect(await scoreline.innerText(), 'the half-time 1-1 is not a result').not.toMatch(/\d/);
    await expect(page.getByTestId('match-score-period')).toHaveCount(0);

    expect(problems.consoleErrors, 'the page logged errors').toEqual([]);
  });

  test(`[${language}] WHAT UNRESOLVED MAY NOT SAY: the backend's claim about an archive never reaches the page`, async ({ page }) => {
    await stubDay(page, language, [AGED_OUT]);
    await page.goto('/matches');

    const aged = row(page, AGED_OUT.id);
    await expect(aged.getByTestId('result-delay-label')).toHaveText(say(language, 'fixture.result.givenUp'));
    expect(await aged.innerText()).not.toMatch(OVERCLAIM);
    await expect(aged).not.toContainText(ARCHIVE_CLAIM);

    await page.goto(`/match/${AGED_OUT.id}`);
    const notice = page.getByTestId('result-delay-notice');
    await expect(notice).toHaveAttribute('data-result-delay', 'given_up');
    await expect(notice.getByTestId('result-delay-detail')).toHaveText(givenUpDetail(language));
    // Retired by the age rule, since removed — not a stop the retry budget made.
    await expect(notice.getByTestId('result-delay-policy'))
      .toHaveText(say(language, 'fixture.result.givenUpOtherPolicy'));
    // Retired by age with nothing answered: no count of a chase that did not happen.
    await expect(notice.getByTestId('result-delay-attempts')).toHaveCount(0);

    // Not in the notice, and not anywhere else on the page either.
    await expect(page.locator('body')).not.toContainText('archive answers nothing');
    await expect(page.locator('body')).not.toContainText('no endpoint still carries it');
    expect(await notice.innerText()).not.toMatch(OVERCLAIM);
  });

  test(`[${language}] the match page of a live fixture is untouched by any of this`, async ({ page }) => {
    await stubDay(page, language);
    await page.goto(`/match/${IN_PLAY.id}`);

    await expect(page.getByTestId('result-delay-notice')).toHaveCount(0);
    const scoreline = page.getByTestId('match-scoreline');
    await expect(scoreline).toContainText('2 - 1');
    await expect(scoreline, 'the running minute belongs to a running match').toContainText('63');
  });

  test(`[${language}] the match page of a tie in extra time shows the tie, not a warning`, async ({ page }) => {
    await stubDay(page, language, [EXTRA_TIME, SHOOTOUT]);
    await page.goto(`/match/${EXTRA_TIME.id}`);

    await expect(page.getByTestId('result-delay-notice'),
      'nothing is overdue while the football is still being played').toHaveCount(0);
    const scoreline = page.getByTestId('match-scoreline');
    await expect(scoreline).toContainText('1 - 1');
    await expect(scoreline, 'the 105th minute is where this tie actually is').toContainText('105');
  });

  test(`[${language}] a provider we cannot reach is said at the top of the page, and the fixture stays overdue`, async ({ page }) => {
    const problems = watchForProblems(page);
    await stubDay(page, language, [OVERDUE_UNREACHABLE], providerUnreachableStatus());
    await page.goto(`/match/${OVERDUE_UNREACHABLE.id}`);

    /*
     * THE THREE THINGS, ON ONE SCREEN, EACH IN ITS OWN PLACE.
     *
     * "We could not reach the provider" is about our connection and belongs to the whole site, so
     * it is the banner and the refresh block. "A result is overdue" is about this fixture and is
     * the notice. "We stopped asking" is NOT on this page, because an outage is not a reason to
     * stop: a pass that reached nobody learned nothing about the fixture.
     */
    await expect(page.getByTestId('provider-status-banner')).toContainText(
      say(language, 'banner.lastRequestFailed', { provider: 'livescore', reason: NETWORK_ERROR }));

    const note = page.getByTestId('data-freshness').getByTestId('freshness-note');
    const failedPrefix = say(language, 'freshness.line.failed', {
      task: say(language, 'sync.task.recover'), reason: '\u0000',
    }).split('\u0000')[0];
    await expect(note, 'the repair that failed is named, in the reader\'s language')
      .toContainText(failedPrefix);
    await expect(note, 'a scheduler task name is not a word a reader knows').not.toContainText(/\brecover\b/);

    const notice = page.getByTestId('result-delay-notice');
    await expect(notice).toHaveAttribute('data-result-delay', 'overdue');
    await expect(notice.getByTestId('result-delay-detail')).toHaveText(
      say(language, 'fixture.result.overdueDetail', { due: agoPhrase(language, 2) }));
    // And the fixture's own record agrees with the page: its last check reached nobody.
    await expect(notice.getByTestId('result-delay-last-check')).toHaveAttribute('data-last-check', 'unreachable');
    await expect(notice.getByTestId('result-delay-policy'), 'nothing was stopped').toHaveCount(0);
    await expect(notice).not.toContainText(say(language, 'fixture.result.givenUp'));
    expect(await notice.innerText()).not.toMatch(OVERCLAIM);

    expect(problems.consoleErrors, 'the page logged errors').toEqual([]);
  });
}

/* ======================================================= THE PERSONAL FEED, AND THE ALLOWANCE */

const READER: Json = {
  user_id: '00000000-0000-4000-8000-0000000000e1',
  email: 'qa.overdue@predictions-local.dev',
  full_name: 'QA Overdue',
  role: 'regular',
  is_active: true,
  is_verified: true,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-05T09:00:00Z',
};

/** Opaque strings that never leave the browser context; the stub accepts anything. */
const ACCESS_TOKEN = 'e2e-overdue-access-token';
const REFRESH_TOKEN = 'e2e-overdue-refresh-token';

const savedEntry = (match: ApiMatch): Json => ({
  match_id: match.id,
  note: null,
  saved_at: at(-2 * HOUR),
  updated_at: at(-2 * HOUR),
  match,
});

/**
 * `GET /me/saved-matches`, bucketed the way the backend buckets it — BY STORED STATUS.
 *
 * That is the honest stub and it is also the trap: the backend files this fixture under `live`,
 * because `live` is what the row says, and the dashboard used to render that bucket under a
 * heading reading "In play now". The frontend has to draw the distinction the bucket cannot.
 */
function savedMatches(matches: ApiMatch[]): Json {
  const live = matches.filter(m => m.status === 'live' || m.status === 'halftime');
  const finished = matches.filter(m => m.status === 'finished');
  const upcoming = matches.filter(m => !live.includes(m) && !finished.includes(m));
  return {
    upcoming: upcoming.map(savedEntry),
    live: live.map(savedEntry),
    finished: finished.map(savedEntry),
    counts: {
      upcoming: upcoming.length, live: live.length, finished: finished.length, total: matches.length,
    },
  };
}

async function signInReader(page: Page, matches: ApiMatch[]): Promise<void> {
  const handler = (route: Route, request: Request): Promise<void> => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/auth/, '');
    if (path === '/me') return json(READER);
    if (path === '/refresh') {
      return json({ access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN, token_type: 'bearer' });
    }
    return json({ detail: 'Not found' }, 404);
  };
  registerAuthHandler(page, handler);
  await page.route('**/api/v1/auth/**', handler);

  await page.route('**/api/v1/me/**', async (route: Route, request: Request) => {
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/me/, '');
    const body: Json = path === '/favourites'
      ? {
        teams: [], leagues: [], team_ids: [], league_ids: [],
        unresolved: { teams: [], leagues: [] },
        saved_matches: savedMatches(matches),
        limits: { teams: 10, leagues: 5 },
      }
      : path === '/saved-matches' ? savedMatches(matches) : {};
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });

  await page.addInitScript(([accessKey, refreshKey, access, refresh]) => {
    window.localStorage.setItem(accessKey, access);
    window.localStorage.setItem(refreshKey, refresh);
  }, ['access_token', 'refresh_token', ACCESS_TOKEN, REFRESH_TOKEN] as const);
}

test('a saved fixture whose result never arrived is not filed under "In play now"', async ({ page }) => {
  const asked = await stubDay(page, 'en');
  await signInReader(page, [OVERDUE, IN_PLAY]);
  await page.goto('/dashboard');

  const stuck = page.locator(`[data-testid="saved-match"][data-match-id="${OVERDUE.id}"]`);
  await expect(stuck).toBeVisible();
  await expect(stuck, 'the stuck fixture is under the group that describes it')
    .toHaveAttribute('data-feed-phase', 'unresolved');
  await expect(page.getByTestId('feed-group-unresolved')).toBeVisible();

  // The genuinely live one keeps the live group, which is what makes the group meaningful.
  await expect(page.locator(`[data-testid="saved-match"][data-match-id="${IN_PLAY.id}"]`))
    .toHaveAttribute('data-feed-phase', 'live');

  // The group headed "In play now" must hold the live fixture and only it.
  const inPlayGroup = page.getByTestId('feed-group-live');
  await expect(inPlayGroup.locator('[data-testid="saved-match"]')).toHaveCount(1);
  await expect(inPlayGroup.locator(`[data-testid="saved-match"][data-match-id="${OVERDUE.id}"]`))
    .toHaveCount(0);

  /*
   * AND THE TILE AT THE TOP OF THE PAGE COUNTS THE SAME FIXTURES.
   *
   * The backend buckets both of these saves as live — that is what their rows say, and the stub
   * reproduces it faithfully — so a count taken from the bucket reads "2 in play now" directly
   * above a feed that has just filed one of the two under "Awaiting a result". One screen, two
   * answers, and the wrong one in the larger type.
   */
  await expect(page.getByTestId('dashboard-live-count'))
    .toHaveText(say('en', 'reader.dashboard.liveCount', { count: 1 }));
  await expect(page.getByTestId('dashboard-my-matches'),
    'the saved total is what the reader saved, and both of these are saved')
    .toContainText(say('en', 'reader.dashboard.savedCount', { count: 2 }));

  /*
   * Nothing this file drives may ask the backend to spend a provider request. The day list is the
   * only route that can, and the dashboard does not use it.
   */
  expect(asked.refreshed, 'the dashboard asked for a provider refresh').toEqual([]);
});

test('with nothing actually in play the dashboard says nothing about anything being in play', async ({ page }) => {
  await stubDay(page, 'en');
  await signInReader(page, [OVERDUE]);
  await page.goto('/dashboard');

  // The save is there, and it is the one the backend files under `live`.
  await expect(page.locator(`[data-testid="saved-match"][data-match-id="${OVERDUE.id}"]`))
    .toBeVisible();
  await expect(page.getByTestId('dashboard-live-count'),
    'one stuck fixture is not one match in play').toHaveCount(0);
  await expect(page.getByTestId('feed-group-live')).toHaveCount(0);
});

test('the day list this file drives asks for its own local day and spends nothing extra', async ({ page }) => {
  const asked = await stubDay(page, 'en');
  await page.goto('/matches');
  await expect(row(page, OVERDUE.id)).toBeVisible();

  expect(asked.days.length, 'the page asked for no day at all').toBeGreaterThan(0);
  expect([...new Set(asked.days)],
    'the workspace asked for a day other than the reader’s own').toEqual([LOCAL_DAY]);
});

/* ============================================================== THE TWO BOUNDARIES OF THE CLAIM */

test('a fixture that was called off is never described as late for a result', async ({ page }) => {
  await stubDay(page, 'en', [CALLED_OFF]);
  await page.goto('/matches');

  const off = row(page, CALLED_OFF.id);
  await expect(off).toBeVisible();
  await expect(off, 'a match nobody is playing is not waiting on a score')
    .toContainText(say('en', 'fixture.postponed'));
  await expect(off.getByTestId('result-delay-label')).toHaveCount(0);
  await expect(off.getByTestId('result-delay-line')).toHaveCount(0);

  await page.goto(`/match/${CALLED_OFF.id}`);
  await expect(page.getByTestId('result-delay-notice')).toHaveCount(0);
});

test('a payload that carries no deadline produces no claim, and the row says what it always said', async ({ page }) => {
  await stubDay(page, 'en', [NO_DEADLINE]);
  await page.goto('/matches');

  const untouched = row(page, NO_DEADLINE.id);
  await expect(untouched).toBeVisible();
  await expect(untouched.getByTestId('result-delay-label'),
    'a deadline the backend never sent must not be invented here').toHaveCount(0);
  await expect(untouched.getByTestId('result-delay-line')).toHaveCount(0);

  // Which means the stored status still speaks, exactly as it did before any of this existed.
  await expect(untouched).toContainText(say('en', 'fixture.live'));
  await expect(untouched).toContainText('HT');
  await expect(untouched.getByTestId('fixture-row-score')).toHaveCount(2);
});
