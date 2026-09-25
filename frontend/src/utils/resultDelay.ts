/**
 * When a fixture's stored status has stopped being able to speak for itself.
 *
 * ── THE FACT THIS EXISTS FOR ────────────────────────────────────────────────────────────────
 *
 * `status` and `minute` are the last thing a provider told us, not a reading of the clock. When a
 * final score never arrives they are never corrected, so they keep saying whatever they said —
 * and what they say is a confident statement about a match in progress. Measured against the live
 * database on 2026-09-24 at 21:27 UTC: Andorra v Malta reading LIVE at HT five and a half hours
 * after kickoff, and three fixtures reading SCHEDULED between twelve and seventeen hours after
 * theirs. Nothing was wrong with the page's rendering. The page was rendering, faithfully, a
 * sentence that had stopped being true hours earlier.
 *
 * So a status is trusted only while it CAN be current, and this is the one place that line is
 * drawn. Every surface asks the same function, so the day list, the card, the match page and the
 * personal feed cannot disagree about whether a match is in play.
 *
 * ── AND THE DEADLINE IS NOT A WHISTLE ───────────────────────────────────────────────────────
 *
 * `resultExpectedBy` is when a result becomes OVERDUE. It is not when football stops. A knockout
 * tie level at 90 plays another half hour and may then take twenty minutes of penalties, so a
 * national-team tie is still being played well past a deadline built for a 90-minute match — and
 * measuring it against the clock alone withholds a running score from a match the reader can see
 * on television. The clock therefore only ever gets the last word where the row has nothing
 * better to say.
 *
 * The row's own minute is what it has to say. It is evidence of play, not of the calendar, and it
 * outlives its truth in exactly one way: it stops advancing. So the two are compared. Real time
 * since kickoff always runs ahead of the minute — intervals, stoppages and a shootout are not on
 * the clock the minute counts — but only by so much, and a minute the wall clock has run away from
 * is a minute nobody has updated for hours. That comparison is football's own arithmetic and needs
 * nothing from the backend, which is why it can answer the question the grace cannot: `HT` five
 * hours after kickoff is 45 minutes of football and 300 minutes of clock, and `105` at kickoff
 * plus 155 is a tie in extra time.
 *
 * ── TWO STATES, AND WHY THEY MAY NOT BE ONE ─────────────────────────────────────────────────
 *
 *   OVERDUE   we expected a result by now and have not got one. A reading of the clock against
 *             the backend's own deadline. Nothing has been recorded about us stopping.
 *   GIVEN UP  the backend's recovery sweep came to the end of its retry schedule and stopped
 *             asking — a limit on what we spend, `stopped_by: retry_budget` (`budgetStop`; a stop
 *             a removed rule made is served with no policy and is not worded as ours). This HAPPENED, at a
 *             moment, and is recorded on the row; it cannot be derived from anything. It is a
 *             statement about our asking and nothing else: it does not say the provider has no
 *             result, and a result that reaches the row by any other route settles the fixture,
 *             after which neither state applies. The backend can also undo it (`reopen_retired`,
 *             or a repair putting a fixture back under the schedule), and a row it has been undone
 *             on reads OVERDUE again, because it is being asked about again.
 *
 * Collapsing them into one "unknown" would be the comfortable choice and the dishonest one: a
 * reader whose result is still being asked for and a reader whose result no longer is are in
 * different positions, and only the second one needs telling that we have stopped.
 *
 * ── WHAT IS NEVER CONCLUDED HERE ────────────────────────────────────────────────────────────
 *
 * Neither state is a result, and neither implies one. A fixture caught here may well be carrying
 * a score — a half-time 0-0 that arrived before the feed went quiet — and that score is NOT the
 * result of the match: nobody has said the match ended, or ended there. The callers therefore
 * withhold the scoreline rather than relabelling it, in exactly the way `probability.ts` withholds
 * a market the source never published instead of rendering it as 0%.
 *
 * ── AND NOTHING IS CLAIMED WITHOUT THE BACKEND'S DEADLINE ───────────────────────────────────
 *
 * `resultExpectedBy` is served by `serialize_match`; it is the kickoff plus the grace the
 * backend's own polling works to. A browser cannot compute it — 150 minutes is a constant of this
 * installation's scheduler, not a property of football — so a payload that does not carry it
 * produces no claim at all here. That is also what keeps this quiet against an older backend
 * rather than inventing a deadline and calling every afternoon fixture overdue.
 *
 * Plain helpers, deliberately in a .ts file: a .tsx may export only components.
 */

import type { Match } from '@/types';

/**
 * Which of the two states a fixture is in.
 *
 * `given_up` outranks `overdue`: a fixture the backend has stopped asking about is both, and the
 * one worth saying is the one that will not change.
 */
export type ResultDelayState = 'overdue' | 'given_up';

/**
 * Every value the backend writes to `recovery.last_outcome`: `RecoveryOutcome` in
 * backend/app/services/match_registry.py, served verbatim by `serialize_recovery` in
 * backend/app/schemas/matches.py.
 *
 * Spelled out here so that `LAST_CHECK_KIND` below has to say something about each one — a new
 * member added there and not here is a type error, not a silent fall-through to "say nothing".
 */
export type RecoveryOutcome =
  | 'provider_error'
  | 'fresh_unanswered'
  | 'deferred'
  | 'cached'
  | 'recovered'
  | 'not_asked';

/**
 * What the backend's most recent pass over this fixture found, when it says.
 *
 *   UNREACHABLE    a results call covering it went out and got no usable answer from any
 *                  provider — `last_outcome: provider_error`: the network or the provider failed
 *                  or refused. Nothing was learned about the fixture.
 *   ANSWERED_EMPTY the provider answered and the answer carried no final result for this
 *                  fixture — `last_outcome: fresh_unanswered`. A statement about one answer, not
 *                  about what the provider holds or will hold.
 *   HELD_BACK      the fixture was due a check and no request was sent — `last_outcome:
 *                  deferred`. WHY is `heldBackBy` (see `deferralCauseOf`): a limit of ours (the
 *                  recovery allowance for the pass or the day, our daily ceiling, how many days
 *                  one pass may reopen), the provider's own reported limit, or a pause after an
 *                  EARLIER request failed. This check is not an outage and is never worded as
 *                  one: it went nowhere, so it neither failed nor found anyone unreachable. Only
 *                  the first cause is ours to name as ours. The fixture stays due.
 *   STORED_COPY    the day came out of our own store, so this pass asked nobody —
 *                  `last_outcome: cached`. The copy held no result for this fixture (a copy that
 *                  did would have settled it, and the outcome would be `recovered`), but WHEN that
 *                  copy was taken is not on the row, so the sentence says only that it was ours.
 *
 * Kept apart because they call for different patience: an outage and a held-back check say
 * nothing about the result, and an empty answer says the provider had not published one when it
 * was asked.
 */
export interface LastCheck {
  kind: 'unreachable' | 'answered_empty' | 'held_back' | 'stored_copy';
  /** When the pass happened, as the backend sent it. Always parses. */
  at: string;
  /** For `held_back` only: whose limit, or what wait, kept the check from leaving. */
  heldBackBy?: DeferralCause;
}

/**
 * WHOSE LIMIT HELD A CHECK BACK, which is not always ours.
 *
 * A deferred check is one that never left: no request went out, so nothing was unreachable. But
 * the backend defers for four different reasons, recorded per provider tried, and only one of
 * them is a limit this installation set. Calling every deferral "our own request allowance" would
 * tell a reader we chose not to ask when the provider had in fact refused us, or when we were
 * waiting out a failure - and the backend's own test for the provider's window insists that row
 * must never be worded as ours.
 *
 * Several providers can be tried in one pass, so the list is read with the EXTERNAL cause first:
 * the provider's own reported limit, then a cool-down after a failure, and only then our own
 * allowance. "Ours" is said only when nothing outside us was involved.
 */
export type DeferralCause = 'provider_allowance' | 'cooling_down' | 'our_allowance' | 'unknown'

export function deferralCauseOf(because: ReadonlyArray<string> | null | undefined): DeferralCause {
  const causes = new Set(because ?? [])
  if (causes.has('provider_allowance')) return 'provider_allowance'
  if (causes.has('cooling_down')) return 'cooling_down'
  if (causes.has('our_allowance')) return 'our_allowance'
  return 'unknown'
}

export interface ResultDelay {
  state: ResultDelayState;
  /** The backend's own deadline, as it sent it. */
  expectedBy: string;
  /** How far past that deadline we are now, in milliseconds. Always positive. */
  lateByMs: number;
  /** When the backend stopped asking. Always null on `overdue`, always set on `given_up`. */
  gaveUpAt: string | null;
  /**
   * True only when the row says the stop was made by the retry budget (`stopped_by:
   * retry_budget`), the one policy whose sentence can say "our own request allowance". False on
   * a stop a since-removed rule made, and on a backend that does not say: those get a sentence
   * that names no policy. Always false on `overdue`.
   */
  budgetStop: boolean;
  /** Passes in which the provider answered without a final result for this fixture. */
  attempts: number | null;
  /** The most recent pass's finding, or null when the payload does not state one. */
  lastCheck: LastCheck | null;
  /**
   * True when the row's own record shows the backend is still asking about it: it carries recovery
   * bookkeeping and no give-up. Always false on `given_up`.
   *
   * This is the backend's own selection rule, read off the row rather than guessed: the sweep
   * (`MatchRegistry.unsettled_before`) takes every unsettled fixture that carries a recovery record
   * and has not been given up on, however old. A fixture with NO record says nothing either way —
   * the backend does not start on one older than its retry horizon, and the browser does not know
   * that horizon — so it is false there, and the page makes no claim about asking in either
   * direction.
   */
  stillAsking: boolean;
}

/**
 * What each `last_outcome` is put into words as — every value the backend writes, and a null for
 * the ones given no sentence, each for its reason:
 *
 *   recovered   the pass SETTLED the fixture, and a settled fixture has no delay: `resultDelay`
 *               returns null before this is read. Met here only on a row that reads unsettled
 *               again, where the record and the status disagree, and the page repeats neither.
 *   not_asked   never written to a row (nothing happened to the fixture); listed so the table
 *               covers the backend's whole vocabulary.
 *
 * A value this build does not know at all is carried on the model and given no sentence either:
 * the overdue or unresolved statement around it is true without it.
 */
const LAST_CHECK_KIND: Readonly<Record<RecoveryOutcome, LastCheck['kind'] | null>> = {
  provider_error: 'unreachable',
  fresh_unanswered: 'answered_empty',
  deferred: 'held_back',
  cached: 'stored_copy',
  recovered: null,
  not_asked: null,
};

const isRecoveryOutcome = (value: unknown): value is RecoveryOutcome =>
  typeof value === 'string' && Object.prototype.hasOwnProperty.call(LAST_CHECK_KIND, value);

/** The backend's `last_outcome`, read only where it can be put into words and dated. */
function lastCheckOf(match: Match): LastCheck | null {
  const outcome = match.recovery?.lastOutcome;
  const kind = isRecoveryOutcome(outcome) ? LAST_CHECK_KIND[outcome] : null;
  const at = match.recovery?.lastOutcomeAt ?? null;
  if (!kind || !at || Number.isNaN(Date.parse(at))) return null;
  return kind === 'held_back'
    ? { kind, at, heldBackBy: deferralCauseOf(match.recovery?.lastDeferredBecause) }
    : { kind, at };
}

/**
 * The statuses that are claims about a match that has not finished.
 *
 * `finished`, `postponed` and `cancelled` are settled words — a postponed fixture is not late for
 * a result, it is not being played — and only these three can go on asserting something the clock
 * has already contradicted. They are the frontend's spelling of the backend's
 * `REGRESSIVE_STATUSES`, which is the same set the recovery sweep reopens.
 */
const UNSETTLED_STATUSES: ReadonlyArray<Match['status']> = ['scheduled', 'live', 'halftime'];

const MINUTE_MS = 60_000;

/**
 * Markers a source writes in the minute field to say the football is CONTINUING past 90.
 *
 * The frontend's spelling of the half of `BEYOND_REGULATION_MARKERS` (backend
 * app/services/providers/base.py) that describes a match still being played. Its other half —
 * "AET", "AP", and the plain "FT" beside them — says the opposite: those mark a tie that reached
 * the end of extra time or of a shootout, so they are absent here deliberately. A row claiming
 * both to be live and to have finished is contradicting itself, and the reading this file takes
 * from it is the one that asserts less.
 */
const PLAY_CONTINUES_MARKERS: ReadonlySet<string> = new Set([
  'et', 'extra', 'extratime', 'pen', 'pens', 'penalties', 'penalty', 'shootout',
]);

/**
 * Half time: the first half is complete and the second has not begun.
 *
 * "HT" is what Live Score API writes in `time` at the interval, and "half time" is the same fact
 * spelled out. Nothing else is listed, because a marker nobody sends is a guess dressed up as a
 * vocabulary — and a value this does not recognise attests to nothing, which past the deadline is
 * the same answer as 45 minutes and never a more generous one.
 */
const HALF_TIME_MARKERS: ReadonlySet<string> = new Set(['ht', 'halftime']);

/**
 * Minutes of football the row's own minute attests to, or null when it attests to none.
 *
 * The value is the FURTHEST point of the match the marker can stand for, because everything built
 * on it decides whether to keep showing a score and the cost of the two mistakes is not
 * symmetrical: reading a marker short withholds a real live score, reading it long leaves a stale
 * row saying "live" for a few minutes longer. "ET" is therefore 120 — a tie somewhere inside extra
 * time, and 120 is as far inside it as it can be — and a shootout is 120 for the same reason, its
 * own length being unclocked and counted below instead.
 *
 * Numerals carry stoppage the way a source writes it: "45+2" is 47 minutes played.
 *
 * A marker is recognised as a WHOLE word, or as the whole of a two-word value with the space taken
 * out ("extra time"), and never as a fragment of something longer. Matching fragments reads "pen"
 * out of "suspended" and turns a match the referee stopped into a shootout — the exact class of
 * mistake this module exists to stop, made by the code meant to stop it.
 */
function playedThrough(minute: string | null | undefined): number | null {
  if (typeof minute !== 'string') return null;
  const tokens = minute.toLowerCase().split(/[^a-z0-9+]+/).filter(Boolean);
  const words = tokens.map(token => token.replace(/[^a-z]/g, '')).filter(Boolean);
  const phrase = words.join('');
  const says = (markers: ReadonlySet<string>): boolean =>
    words.some(word => markers.has(word)) || markers.has(phrase);
  if (says(PLAY_CONTINUES_MARKERS)) return 120;
  if (says(HALF_TIME_MARKERS)) return 45;
  for (const token of tokens) {
    const numeric = /^(\d{1,3})(?:\+(\d{1,2}))?$/.exec(token);
    if (numeric) return Number(numeric[1]) + Number(numeric[2] ?? 0);
  }
  return null;
}

/**
 * Every minute between kickoff and the final whistle that the reported minute does not count.
 *
 * Football's own unclocked time, added up rather than guessed at: the half-time interval at its
 * 15-minute maximum, the interval before extra time and the change of ends inside it (about six),
 * stoppage played beyond the minute a source last published (generously, twenty across a match),
 * and a penalty shootout, which has no clock at all and can take twenty. Roughly seventy, and 75
 * is the round number above it that leaves room for the gap between a feed's poll and ours.
 *
 * It is deliberately the generous end of each. The figure decides how far a live score is trusted,
 * and the failure this file exists to prevent — a page asserting a match is in play when it ended
 * hours ago — is the one measured in HOURS of drift, not minutes. Andorra v Malta, the fixture
 * this was built against, was 45 minutes of football against five and a half hours of clock, and
 * doubling this number would still not reach it.
 */
const UNCLOCKED_ALLOWANCE_MS = 75 * MINUTE_MS;

/**
 * True when the row's own minute still accounts for the time that has passed since kickoff.
 *
 * The one thing a stranded fixture cannot do. Its minute froze when the feed went quiet, so the
 * clock walks away from it and keeps walking; a match genuinely in progress has a minute that
 * moved when the clock did, whether it is in stoppage time, in extra time or at the spot.
 *
 * `scheduled` is never in progress here whatever it carries: it is the row saying the match has
 * not started, and past the deadline that is not a claim the minute can rescue. A live row with no
 * minute at all attests to nothing either, and falls to the clock exactly as it did before this
 * existed.
 */
function reportsPlayInProgress(match: Match, now: number): boolean {
  if (match.status !== 'live' && match.status !== 'halftime') return false;
  const played = playedThrough(match.minute);
  if (played === null) return false;
  const kickoff = match.kickoffUtc ? Date.parse(match.kickoffUtc) : NaN;
  if (Number.isNaN(kickoff)) return false;
  return now - kickoff <= played * MINUTE_MS + UNCLOCKED_ALLOWANCE_MS;
}

/**
 * How late this fixture's result is, or null while its status can still be believed.
 *
 * Null covers every ordinary case and is the answer callers should expect: a fixture yet to kick
 * off, one genuinely in play — including a tie still being played past the deadline a 90-minute
 * match is measured by — one that finished, one called off, and one whose payload carries no
 * deadline to measure against.
 *
 * Nothing is ever withheld EARLIER than the backend's own deadline: the minute is asked only after
 * that deadline has passed, and it can only ever answer that a fixture is still being played. A
 * payload that carries no deadline still produces no claim at all.
 */
export function resultDelay(match: Match, now: number = Date.now()): ResultDelay | null {
  if (!UNSETTLED_STATUSES.includes(match.status)) return null;

  const expectedBy = match.resultExpectedBy;
  if (!expectedBy) return null;
  const due = Date.parse(expectedBy);
  if (Number.isNaN(due) || due > now) return null;

  const recovery = match.recovery ?? null;
  const gaveUpAt = recovery?.gaveUpAt ?? null;
  /*
   * A recorded give-up is a fact and no arithmetic overrules it: the backend stopped asking, at a
   * moment, and no reading of a minute changes that. So the minute is asked only where nothing has
   * been recorded, and a row that says "unresolved" always says it for the one reason no clock can
   * produce.
   */
  if (!gaveUpAt && reportsPlayInProgress(match, now)) return null;
  return {
    state: gaveUpAt ? 'given_up' : 'overdue',
    expectedBy,
    lateByMs: now - due,
    gaveUpAt,
    budgetStop: Boolean(gaveUpAt) && recovery?.stoppedBy === 'retry_budget',
    attempts: typeof recovery?.attempts === 'number' ? recovery.attempts : null,
    lastCheck: lastCheckOf(match),
    stillAsking: recovery !== null && !gaveUpAt,
  };
}

/**
 * True when this fixture may be shown as in play.
 *
 * The question every "live" list, badge and poll was really asking. `isMatchLive` answers a
 * narrower one — what the stored status says — and on a fixture whose result never arrived the
 * two answers differ, which is the whole defect.
 */
export function isPlayableNow(match: Match, now: number = Date.now()): boolean {
  return (match.status === 'live' || match.status === 'halftime') && resultDelay(match, now) === null;
}
