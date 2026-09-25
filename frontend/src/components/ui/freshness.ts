/**
 * Reading the backend's scheduled-refresh state into sentences a reader can act on.
 *
 * Everything this application shows is STORED data. Nothing on a page is live, and until the
 * backend gained a scheduler nothing refreshed unless somebody happened to load a page with
 * refresh on — so "how old is this?" had no answer at all. It has one now, and these helpers turn
 * `ProviderStatus.scheduler` into it.
 *
 * THE THREE FACTS THAT MUST STAY APART. They are three different claims and the interface may
 * never let one stand in for another:
 *
 *   1. WHEN THE PROVIDER'S MODEL RAN. A fact about the forecast itself, published per forecast
 *      (`modelRunAt`), and frequently not published at all. Nothing in this file states it: it is
 *      per-fixture, and ForecastProvenance / ProvenanceLine own it.
 *   2. WHEN WE LAST RETRIEVED ANYTHING. A fact about us talking to the provider — the chain's
 *      `last_success_at`. A successful retrieval says nothing about how old the provider's numbers
 *      already were when we got them.
 *   3. WHEN THE SCHEDULED REFRESH LAST SUCCEEDED. A fact about our own process. A task can
 *      succeed having made no provider call at all — the results task with nothing unsettled does
 *      exactly that — so this is not a retrieval either.
 *
 * AND THE FOURTH SEPARATION, ADDED AFTER A REVIEWER WAS MISLED BY ITS ABSENCE. Fixtures and model
 * forecasts refresh on different schedules, from different providers, under different allowances —
 * and on this installation they are routinely days apart. A single "last refreshed" line took the
 * most recent success across every task, so a live-score pass that ran a minute ago made a forecast
 * that had not been refreshed in two days read as current. That is not a rounding error; it is the
 * page asserting something nobody established. `freshnessReport` therefore answers the question
 * twice — once for the fixture side, once for forecasts — and neither answer is ever allowed to
 * cover for the other.
 *
 * AND THE STATES THAT ARE NOT TIMESTAMPS. A task that has NEVER RUN has no time to show, and
 * showing another task's time in its place would be a fabrication; a task that is SKIPPING because
 * the daily allowance is spent has neither succeeded nor failed. Both get their own wording.
 *
 * Nothing here is rendered from a guess: every sentence is built from a field the backend
 * published, or from the calendar (UTC midnight), and never from an assumption about either.
 *
 * Plain helpers, deliberately in a .ts file: a .tsx may export only components.
 */

import type { FreshnessTone } from '@/utils/brief';
import type { ProviderStatus, SchedulerStatus, SyncTaskState } from '@/services/match-data-source';
import type { MessageKey } from '@/i18n';
import { formatDateTime, t } from '@/i18n';

/**
 * What each scheduled task keeps current, in the reader's terms rather than the scheduler's.
 *
 * A map of message KEYS, resolved on every call. The map of finished strings it replaced was
 * built once at import time, which in a product where the reader can change language without
 * reloading means "built in whatever language happened to be active at boot".
 */
const SYNC_TASK_KEY: Record<string, MessageKey> = {
  fixtures: 'sync.task.fixtures',
  live: 'sync.task.live',
  results: 'sync.task.results',
  recover: 'sync.task.recover',
  forecasts: 'sync.task.forecasts',
};

/** A task name this build has never heard of still reaches the reader, readably. */
export function syncTaskLabel(name: string): string {
  const key = SYNC_TASK_KEY[name];
  return key ? t(key) : name.replace(/_/g, ' ');
}

/** The order the tasks read best in: what is on, then what is happening, then how it ended. */
const TASK_ORDER = ['fixtures', 'live', 'results', 'recover', 'forecasts'];

/**
 * Which tasks belong to the forecast clock.
 *
 * Everything NOT named here is the fixture side, so a task this build has never heard of is
 * reported rather than silently dropped out of both halves — which is how a broken task would
 * disappear from the interface entirely.
 */
const FORECAST_TASKS = ['forecasts'];

/**
 * How each fixture provider is named on screen.
 *
 * One vocabulary, shared with DataSourceNotice, so the same provider is never called two
 * different things on one page. `sample` names itself as not real, because it is not.
 */
const FIXTURE_PROVIDER_KEY: Record<string, MessageKey> = {
  livescore: 'fixtureProvider.livescore',
  api_football: 'fixtureProvider.apiFootball',
  thesportsdb: 'fixtureProvider.thesportsdb',
  sample: 'fixtureProvider.sample',
};

/**
 * The display name for a fixture provider, falling back to the raw key rather than hiding it.
 *
 * The product NAMES stay as they are in every language — "Live Score API" is a product, not a
 * word — and only what we add to them is translated: which one is a fallback, and that the
 * sample data is not real.
 */
export function fixtureProviderLabel(provider: string | null | undefined): string {
  const key = FIXTURE_PROVIDER_KEY[provider ?? ''];
  if (key) return t(key);
  return provider ?? t('fixtureProvider.none');
}

/**
 * A rounded duration in the reader's language, with that language's own plural rule.
 *
 * This replaced `${count} ${word}${count === 1 ? '' : 's'}`, which is English's rule written into
 * the code. French is singular at 0 AND 1 — "0 minute", "1 minute", "2 minutes" — so the English
 * rule produces a mistake in French on the first value it is given.
 */
type DurationUnit = 'minute' | 'hour' | 'day';
const DURATION_KEY: Record<DurationUnit, MessageKey> = {
  minute: 'duration.minutes',
  hour: 'duration.hours',
  day: 'duration.days',
};
const duration = (count: number, unit: DurationUnit): string => t(DURATION_KEY[unit], { count });

/**
 * Close a sentence built around a backend string.
 *
 * The backend's reasons arrive without terminal punctuation ("daily request budget for
 * gameforecast is spent (8/8 used)"), and running straight into the next sentence makes two facts
 * read as one. The text itself is never altered — only finished.
 */
const sentence = (text: string): string => (/[.!?]$/.test(text.trim()) ? text.trim() : `${text.trim()}.`);

/** A timestamp as the viewer's own locale string, or null when there is nothing to show. */
export function absoluteTime(iso: string | null | undefined): string | null {
  // In the reader's chosen zone, not the device's: every other time on the page is, and a
  // timestamp in a tooltip that disagreed with the one beside it would be worse than none.
  return formatDateTime(iso);
}

/**
 * "4 minutes ago", "in 22 minutes", "just now".
 *
 * Rounded, and never dressed up as precision: the exact timestamp always travels beside it as a
 * `title`, so a reader who needs the real value has it.
 */
export function relativeTime(iso: string | null | undefined, now: number = Date.now()): string | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return null;

  const deltaMs = at - now;
  const past = deltaMs <= 0;
  const seconds = Math.abs(deltaMs) / 1000;

  if (seconds < 45) return t(past ? 'time.justNow' : 'time.inUnderAMinute');

  // The duration first, then the language's own frame around it. English puts the frame at the
  // end ("2 hours ago") and French at the front ("il y a 2 heures"): assembling the sentence in
  // English order and translating the pieces would put "il y a" in the wrong place.
  const span = seconds < 90 * 60 ? duration(Math.max(1, Math.round(seconds / 60)), 'minute')
    : seconds < 36 * 3600 ? duration(Math.round(seconds / 3600), 'hour')
      : duration(Math.round(seconds / 86400), 'day');
  return t(past ? 'time.ago' : 'time.in', { duration: span });
}

/**
 * How far past due something is, as the tail of "The next attempt is …".
 *
 * `relativeTime` cannot answer this and must not be asked to. Its past branch describes a MOMENT
 * that has happened ("2 minutes ago"), and an attempt that is overdue is precisely one that has
 * NOT happened — so reading a moment phrase into that sentence produced "The next attempt is 2
 * minutes ago", which was live on the settle row and which any task on a two-minute cadence
 * renders for part of every cycle.
 *
 * Rounded on the same boundaries as `relativeTime`, so one instant is never described as two
 * different lengths of time within one block.
 */
function overdueSentence(seconds: number): string {
  if (seconds < 45) return t('freshness.nextAttempt.dueNow');
  if (seconds < 90 * 60) {
    return t('freshness.nextAttempt.overdueMinutes', { count: Math.max(1, Math.round(seconds / 60)) });
  }
  if (seconds < 36 * 3600) {
    return t('freshness.nextAttempt.overdueHours', { count: Math.round(seconds / 3600) });
  }
  return t('freshness.nextAttempt.overdueDays', { count: Math.round(seconds / 86400) });
}

/**
 * A backoff window, in the units the rest of this block already uses.
 *
 * Rounded on `relativeTime`'s boundaries for the same reason `overduePhrase` is: the forecasts
 * task backs off for 21600 seconds, and this sentence called that "360 minutes" one line above a
 * cadence line calling the identical span "6 hours". One duration, two numbers, in one paragraph.
 */
function backoffWindow(seconds: number): string {
  if (seconds < 90 * 60) return duration(Math.max(1, Math.round(seconds / 60)), 'minute');
  if (seconds < 36 * 3600) return duration(Math.round(seconds / 3600), 'hour');
  return duration(Math.round(seconds / 86400), 'day');
}

/**
 * When the scheduler will try this task again — or that it should already have.
 *
 * AN OVERDUE ATTEMPT IS A REAL STATE AND IS WORTH SAYING, so the sentence is not withheld once the
 * time has passed: a reader looking at a stuck refresh wants to be told it is late, not to watch
 * the line disappear. It was the tense that was wrong, not the fact. Both ends of the range have
 * to read as English — a task seconds past due is simply due, one hours past due is hours late.
 *
 * Null when the backend published no next attempt. Nothing is invented to fill it.
 */
export function nextAttemptSentence(
  iso: string | null | undefined,
  now: number = Date.now(),
): string | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return null;
  if (at > now) {
    const ahead = relativeTime(iso, now);
    return ahead ? t('freshness.nextAttempt.ahead', { when: ahead }) : null;
  }
  return overdueSentence((now - at) / 1000);
}

/**
 * True when the backend's skip reason is a spent request allowance rather than anything broken.
 *
 * Matched on the backend's own vocabulary ("daily request budget for gameforecast is spent").
 * A reason this build does not recognise falls through to the generic wording, which prints the
 * backend's sentence verbatim — so an unrecognised reason is still fully reported.
 */
export function isAllowanceSkip(reason: string | null | undefined): boolean {
  return /\ballowance\b|\bbudget\b|\bquota\b/i.test(reason ?? '');
}

/**
 * When the daily request allowance resets, stated as the calendar fact it is.
 *
 * `app/services/providers/budget.py` counts outbound requests "per provider per UTC day" — the
 * counter key carries the UTC date — so our local allowance resets at 00:00 UTC. That is the only
 * reason this sentence may be written: it is derived from how our counter is kept, not guessed
 * from how a provider's own plan might renew.
 */
export function allowanceResetNote(now: number = Date.now()): string {
  const at = new Date(now);
  const nextMidnightUtc = Date.UTC(at.getUTCFullYear(), at.getUTCMonth(), at.getUTCDate() + 1);
  const when = relativeTime(new Date(nextMidnightUtc).toISOString(), now);
  return when
    ? t('freshness.allowanceResetWhen', { when })
    : t('freshness.allowanceReset');
}

/** One scheduled task, described. */
export interface TaskFreshness {
  name: string;
  label: string;
  /** Short statement for the row: "updated 12 minutes ago", "has never run". */
  text: string;
  tone: FreshnessTone;
  /** The exact timestamp behind `text`, for a `title`. Null when there is none. */
  exact: string | null;
  /** True when the task is deliberately doing nothing right now. */
  paused: boolean;
  /** True when the last attempt failed and it has not recovered. */
  failing: boolean;
  /**
   * True when the task has never been ATTEMPTED — the backend's own `never_run`, and nothing else.
   *
   * It used to be set for any task with no successful pass, which made it false for the one state
   * it matters in: a task that has run and failed has certainly run. `neverSucceeded` is the other
   * claim and is kept apart from it, because the two are exactly what the row's wording turns on.
   */
  neverRun: boolean;
  /** True when no attempt has ever succeeded — which a task that ran and failed also is. */
  neverSucceeded: boolean;
  /** The backend's own reason for the pause. Null when the task is not paused. */
  pauseReason: string | null;
  /** The backend's own reason for the failure. Null when the last attempt did not fail. */
  failureReason: string | null;
  /**
   * The leading reason, pause before failure — kept for callers that want one sentence.
   *
   * A task can be BOTH paused and failing, and the two reasons come from two different fields, so
   * anything describing a specific state reads `pauseReason` or `failureReason` rather than this.
   */
  reason: string | null;
  /** When it comes back — the sentence that makes a pause useful instead of merely alarming. */
  resume: string | null;
  /**
   * The same answer as separate sentences, in the order `resume` joins them.
   *
   * A caller assembling a note for SEVERAL tasks needs the pieces rather than the paragraph: the
   * allowance reset is one calendar fact shared by every task waiting on it and must be said
   * once, while the next attempt and the backoff window are measured per task and must be said
   * for each. With only the joined string the choice was between printing the reset once per
   * task and dropping a task's own timings with it.
   */
  resumeParts: string[];
  /**
   * How the resume time was arrived at: the allowance's calendar and the backoff window.
   *
   * True, useful when something is stuck, and not what a reader came to the page for — so these
   * live in the opened detail rather than in the note. See the comment where they are built.
   */
  mechanicsParts: string[];
  /** Every sentence worth showing in the opened detail, in order, de-duplicated. */
  detail: string[];
}

/**
 * Whether a task is running later than it should be.
 *
 * Derived from the backend's own `next_due_at` and `interval_seconds`: a task is "behind" only
 * once it is a full interval past due, so a tick that has not landed yet is not reported as a
 * fault. With no interval published, nothing is claimed.
 */
export function taskIsBehind(task: SyncTaskState, now: number = Date.now()): boolean {
  if (!task.enabled || !task.next_due_at || !task.interval_seconds) return false;
  const due = Date.parse(task.next_due_at);
  if (Number.isNaN(due)) return false;
  return now - due > task.interval_seconds * 1000;
}

/** How often a task is meant to run, spelled out. */
/**
 * How often a task is meant to run, spelled out.
 *
 * `unit` travels with the duration because the words around it agree with it in French —
 * "toutes les 6 heures" but "tous les 2 jours" — and that agreement cannot be recovered from the
 * finished duration string. In English the parameter changes nothing, which is exactly why it
 * would never have been noticed without writing the French.
 */
function cadenceNote(task: SyncTaskState): string | null {
  if (!task.interval_seconds) return null;
  const hours = task.interval_seconds / 3600;
  return hours >= 1
    ? t('freshness.cadence', { duration: duration(Math.round(hours), 'hour'), unit: 'hour' })
    : t('freshness.cadence', {
      duration: duration(Math.round(task.interval_seconds / 60), 'minute'),
      unit: 'minute',
    });
}

/**
 * A provider's own refusal, in words a football reader can use.
 *
 * The backend passes the upstream message through verbatim, which is right for a diagnostic and
 * wrong for the first thing on a match page. On 2026-09-19 the live block read, above the
 * football: "Model forecasts: last attempt failed - skipped (recent failure: gameforecast: rate
 * limit or quota exceeded (HTTP 429): You have exceeded the DAILY quota for Requests on your
 * current plan, BASIC. Upgrade your plan at https://rapidapi.com/krnelstudio/api/game-forecast-api)."
 *
 * Three things are wrong with showing that to a visitor. It names the vendor and the plan tier,
 * which is our plumbing and not their business. It carries an HTTP status and a parenthetical
 * inside a parenthetical. And it ends in a link inviting somebody to buy something, which is an
 * advert we did not write and do not want on a public page.
 *
 * So the note says what it means for the reader and the verbatim message stays one disclosure
 * away, where anyone diagnosing it still has every word of it. Nothing is discarded, and nothing
 * is invented either: a message this does not recognise is passed through with only its URLs
 * removed, because an unrecognised message may be the one that matters.
 */
export function readableProviderReason(raw: string | null | undefined): string | null {
  const text = (raw ?? '').trim()
  if (!text) return null
  // Never show a vendor link to a visitor, whatever the message turns out to be.
  const withoutLinks = text.replace(/https?:\/\/\S+/g, '').replace(/\s{2,}/g, ' ').trim()
  const lower = withoutLinks.toLowerCase()
  if (lower.includes('quota') || lower.includes('rate limit') || lower.includes('429')) {
    return t('freshness.reason.quota')
  }
  if (lower.includes('budget') && lower.includes('spent')) {
    return t('freshness.reason.budget')
  }
  if (lower.includes('unauthor') || lower.includes('forbidden') || lower.includes('401')
      || lower.includes('403')) {
    return t('freshness.reason.credentials')
  }
  if (lower.includes('timeout') || lower.includes('timed out')) {
    /*
     * Deliberately names nobody. Not every timeout is a provider's: this branch was written as
     * "the provider did not answer in time" and a test caught it rendering that for
     * "settlement store: database timeout", which is our own database and not a provider at all.
     * A summary must not reassign blame that the message did not assign.
     */
    return t('freshness.reason.timeout')
  }
  /*
   * Unrecognised: say it as it came, minus the links, and let the disclosure carry the original.
   * NOT translated, in any language — this is the provider's own sentence, and paraphrasing a
   * source's words into another language is the one thing this package was told not to do. The
   * branches above are different: those are OUR summaries of a refusal we recognised.
   */
  return withoutLinks.replace(/[.\s]+$/, '')
}

/** Everything the reader needs about one task, in the backend's words wherever it supplied them. */
export function describeTask(name: string, task: SyncTaskState, now: number = Date.now()): TaskFreshness {
  const label = syncTaskLabel(name);

  if (!task.enabled) {
    return {
      name, label, text: t('freshness.task.switchedOff'), tone: 'unknown', exact: null,
      paused: false, failing: false,
      neverRun: Boolean(task.never_run), neverSucceeded: !task.last_success_at,
      pauseReason: null, failureReason: null, reason: null, resume: null, resumeParts: [],
      mechanicsParts: [],
      detail: [t('freshness.task.switchedOffDetail')],
    };
  }

  /*
   * PAUSED AND FAILING ARE NOT EXCLUSIVE, AND EACH HAS ITS OWN REASON.
   *
   * A task can have failed its last attempt and then be skipping while it waits for the allowance
   * to come back; the backend publishes the two reasons in two different fields. Reading one
   * `reason` for both printed the SKIP's wording under "last attempt failed", which attributes to
   * the failure a sentence the backend wrote about something else.
   */
  const paused = Boolean(task.last_skip_reason);
  const failing = task.consecutive_failures > 0;
  const pauseReason = paused ? task.last_skip_reason : null;
  const failureReason = failing
    ? (task.last_error ?? t('freshness.task.noFailureReason'))
    : null;
  const reason = pauseReason ?? failureReason;

  /*
   * The resume statement, which is the whole point of showing a pause at all. "Paused" tells a
   * reader nothing they can do anything with; "updates resume after 00:00 UTC, in about 7 hours"
   * does. The allowance sentence is added only when the backend's own reason says the allowance
   * is what stopped it — never as a general explanation for every pause.
   */
  const resumeParts: string[] = [];
  /*
   * MECHANICS ARE NOT THE ANSWER TO "WHEN DOES THIS COME BACK".
   *
   * "The next attempt is in 5 hours" is what a reader can act on. How our allowance is counted,
   * which calendar it resets on, and how long the backoff window is are how we arrived at that
   * number, and the reviewer counted them among the technical explanations filling the screen
   * above the football. They are kept, in full, one disclosure away — losing them would make a
   * stuck refresh undiagnosable — but they are no longer the first thing on a match page.
   */
  const mechanicsParts: string[] = [];
  if (paused && isAllowanceSkip(task.last_skip_reason)) mechanicsParts.push(allowanceResetNote(now));
  const nextAttempt = nextAttemptSentence(task.next_due_at, now);
  if (nextAttempt) resumeParts.push(nextAttempt);
  if (task.backoff_seconds) {
    /*
     * "AFTER 1 FAILURE IN A ROW" IS NOT ENGLISH, and it is what the live installation renders: the
     * forecasts task is one failure deep, so the note read "After 1 failure in a row it is waiting
     * 360 minutes before trying again." A run of one is not a run, and 360 minutes is the same six
     * hours the cadence line beside it already names.
     *
     * The count is never rounded up to make the phrase work. With no failure reported, nothing is
     * said about failures at all rather than a failure being asserted to fit the sentence.
     */
    const failures = task.consecutive_failures;
    const window = backoffWindow(task.backoff_seconds);
    mechanicsParts.push(
      failures > 1 ? t('freshness.backoff.afterMany', { count: failures, window })
        : failures === 1 ? t('freshness.backoff.afterOne', { window })
          : t('freshness.backoff.none', { window }),
    );
  }
  const resume = resumeParts.length > 0 ? resumeParts.join(' ') : null;

  const behind = taskIsBehind(task, now);
  const detail: string[] = [];
  const add = (line: string | null | undefined) => {
    const text = (line ?? '').trim();
    if (text && !detail.includes(text)) detail.push(text);
  };
  if (paused) add(sentence(t('freshness.task.pausedDetail', { reason: pauseReason })));
  if (failing) add(sentence(t('freshness.task.failedDetail', { reason: failureReason })));
  if (behind && !paused && !failing) add(t('freshness.task.behindDetail'));
  add(resume);
  add(cadenceNote(task));

  /*
   * A task with no successful pass has no timestamp, and none is borrowed from anywhere else.
   *
   * "Has never run" and "has run and never succeeded" are different claims, and the row must make
   * the same distinction the summary line above it makes. The live forecasts task has run once and
   * failed once: with one wording for both states this row read "has never run" three lines under
   * a summary saying "no refresh has succeeded yet", so the same block contradicted itself and the
   * row was the half that was false.
   */
  if (task.never_run || !task.last_success_at) {
    const base = t(task.never_run ? 'freshness.task.neverRun' : 'freshness.task.neverSucceeded');
    return {
      name,
      label,
      text: paused ? t('freshness.task.pausedSuffix', { state: base }) : base,
      tone: failing ? 'problem' : paused ? 'ageing' : 'unknown',
      exact: null,
      paused,
      failing,
      neverRun: Boolean(task.never_run),
      neverSucceeded: true,
      pauseReason,
      failureReason,
      reason,
      resume,
      resumeParts,
      mechanicsParts,
      detail,
    };
  }

  return {
    name,
    label,
    text: t('freshness.task.updated', {
      when: relativeTime(task.last_success_at, now) ?? absoluteTime(task.last_success_at),
    }),
    tone: failing ? 'problem' : (paused || behind) ? 'ageing' : 'ok',
    exact: absoluteTime(task.last_success_at),
    paused,
    failing,
    neverRun: false,
    neverSucceeded: false,
    pauseReason,
    failureReason,
    reason,
    resume,
    resumeParts,
    mechanicsParts,
    detail,
  };
}

/** Every task, in reading order, with any the backend added later kept at the end. */
export function describeTasks(scheduler: SchedulerStatus, now: number = Date.now()): TaskFreshness[] {
  const names = Object.keys(scheduler.tasks ?? {});
  names.sort((a, b) => {
    const ia = TASK_ORDER.indexOf(a);
    const ib = TASK_ORDER.indexOf(b);
    return (ia === -1 ? TASK_ORDER.length : ia) - (ib === -1 ? TASK_ORDER.length : ib) || a.localeCompare(b);
  });
  return names.map(name => describeTask(name, scheduler.tasks[name], now));
}

/** The single line a page leads with, and whether it should carry any weight. */
export interface FreshnessSummary {
  /** The statement itself, e.g. "Stored data · last refreshed 12 minutes ago". */
  text: string;
  tone: FreshnessTone;
  /** A second sentence when one is needed — a pause with its resume time, or an unknown. */
  note: string | null;
  /**
   * `note` as the separate statements it is built from: one per task it speaks for.
   *
   * Attribution alone was not enough to make a two-task note readable. Four measured sentences
   * running together in one paragraph are hard to parse even when each names its task, and a
   * reader scanning for "which refresh is stuck" should not have to. A caller that can lay them
   * out gets the pieces; `note` stays the joined form for callers that only want one string.
   */
  notes: string[];
  /**
   * How the resume time was worked out, one line per task, for the opened detail only.
   *
   * The allowance's calendar and the backoff window are true and worth keeping, and they are not
   * what a reader on a match page is there for. See where they are built in describeTask.
   */
  mechanics?: string[];
  /**
   * The "when it comes back" sentences `note` already carries. Null when it answers nothing.
   *
   * Exposed so a caller with a SECOND source for the same answer — the provider budget, which the
   * scheduler's task state knows nothing about — can tell whether the note already says it,
   * instead of guessing from its wording and either printing it twice or dropping it entirely.
   */
  resume: string | null;
  /**
   * The task `note` is about, when it is about one. The first of `noteTasks`.
   *
   * Only so the detail rows can avoid printing the same pause twice; it is never used to suppress
   * a DIFFERENT task's lines, which is how a real problem would end up hidden behind a coincidence
   * of identical wording.
   */
  noteTask: string | null;
  /**
   * Every task `note` speaks for.
   *
   * `note` can now describe more than one task — a failure and a pause on different tasks are two
   * facts and both are stated — so naming only the first left the others repeating themselves a
   * few pixels below.
   */
  noteTasks: string[];
  /** True when the backend reported a scheduler at all. */
  scheduled: boolean;
}


/** Worst wins, so a block holding two clocks takes the tone of the one in more trouble. */
const TONE_RANK: Record<FreshnessTone, number> = { ok: 0, unknown: 1, ageing: 2, problem: 3 };

/** The worse of two tones. 'unknown' outranks 'ok': not knowing is not the same as being fine. */
export function worseTone(a: FreshnessTone, b: FreshnessTone): FreshnessTone {
  return TONE_RANK[b] > TONE_RANK[a] ? b : a;
}

/** One group of scheduled tasks, read as a single clock. */
interface ClockState {
  /** "4 minutes ago" for the most recent success in the group; null when none has ever succeeded. */
  age: string | null;
  /**
   * True when no task in the group has ever been ATTEMPTED — a different claim from `age === null`,
   * which only says none has ever succeeded. A task that has run four times and failed four times
   * has certainly run, and telling a reader it never has would be a plain falsehood about the one
   * state that means something is wrong.
   */
  neverRan: boolean;
  tone: FreshnessTone;
  /** A pause, a failure or a late run, stated as its own sentence. */
  note: string | null;
  /** The same statements unjoined, one per task — see FreshnessSummary.notes. */
  notes: string[];
  /**
   * How the resume time was worked out, one line per task, for the opened detail only.
   *
   * The allowance's calendar and the backoff window are true and worth keeping, and they are not
   * what a reader on a match page is there for. See where they are built in describeTask.
   */
  mechanics?: string[];
  /** The "when it comes back" half of `note`, so a caller can tell that it is already answered. */
  resume: string | null;
  noteTask: string | null;
  noteTasks: string[];
  /** True when the group holds at least one enabled task, so it has something to speak for. */
  present: boolean;
}

/**
 * The state of one clock: the most recent success across `names`, with whatever is wrong with it.
 *
 * Split out of the summary so the fixture side and the forecast side are computed by exactly the
 * same rules — the whole point of separating them is that they are the same question asked of
 * different tasks, not two different questions.
 */
function clockState(scheduler: SchedulerStatus, names: string[], now: number): ClockState {
  const active = names
    .filter(name => scheduler.tasks[name]?.enabled !== false)
    .map(name => describeTask(name, scheduler.tasks[name], now));

  if (active.length === 0) {
    return {
      age: null, neverRan: true, tone: 'unknown',
      note: null, notes: [], resume: null, noteTask: null, noteTasks: [], present: false,
    };
  }

  const successes = active
    .map(task => Date.parse(scheduler.tasks[task.name]?.last_success_at ?? ''))
    .filter(value => !Number.isNaN(value));

  const paused = active.filter(task => task.paused);
  const failing = active.filter(task => task.failing);
  const behind = active.filter(task => taskIsBehind(scheduler.tasks[task.name], now));

  /*
   * ONE PARAGRAPH PER TASK, AND EVERY SENTENCE IN IT IS ABOUT THAT TASK.
   *
   * A pause and a failure are different states, they get different sentences, and BOTH are stated
   * when both are true — this used to be `failNote ?? pauseNote ?? behindNote`, which assumes a
   * task is in exactly one of the three states, and the failure branch silently ate the pause and
   * with it the only sentence saying when forecasts come back.
   *
   * Each reason is also the reason of the task it is printed under. Joining the labels and then
   * printing `failing[0]`'s reason states a fact measured about one task as though it were true of
   * the others: with `live` down on a network error and `results` down on a database timeout, the
   * block read "Live scores and Final results: last attempt failed — livescore: network error",
   * which is false of Final results.
   *
   * AND THE SENTENCES THAT SAY WHEN IT COMES BACK ARE PART OF THAT PARAGRAPH, not a pool at the
   * end of the note. Pooled, with two tasks in trouble, the block read "The next attempt is in 10
   * minutes. After 3 failures in a row it is waiting 10 minutes before trying again. The next
   * attempt is in 30 minutes. After 2 failures in a row it is waiting 30 minutes before trying
   * again." — four measured facts, none of them attached to the task it was measured on, so a
   * reader could not tell which refresh either pair described.
   *
   * With ONE task in trouble this emits exactly the string it emitted before, in the same order,
   * so the states pinned in freshness.spec.ts are unchanged and a healthy schedule still gets no
   * second sentence at all.
   */
  const speaking: TaskFreshness[] = [];
  for (const task of [...failing, ...paused, ...behind]) {
    if (!speaking.includes(task)) speaking.push(task);
  }

  /*
   * The one sentence that is NOT a fact about a task. Our allowance resets on the calendar, not on
   * any task's schedule, so several tasks waiting on it are all waiting on the same midnight and
   * printing it under each of them would read as several separate stoppages.
   */
  const allowance = allowanceResetNote(now);
  let allowanceSaid = false;

  const noteTasks: string[] = [];
  const resumes: string[] = [];
  const mechanics: string[] = [];
  const paragraphs: string[] = [];

  for (const task of speaking) {
    const lines: string[] = [];
    /*
     * The reason a READER needs, not the upstream string. The verbatim message is still carried
     * into the disclosure below, word for word, so nothing is lost to whoever is diagnosing it.
     */
    if (task.failing) {
      lines.push(sentence(t('freshness.line.failed', {
        task: task.label,
        reason: readableProviderReason(task.failureReason) ?? t('freshness.reason.unstated'),
      })));
    }
    if (task.paused) {
      lines.push(sentence(t('freshness.line.paused', {
        task: task.label,
        reason: readableProviderReason(task.pauseReason) ?? t('freshness.reason.unstated'),
      })));
    }
    /*
     * A task that is simply late is the third case, and it needs a sentence of its own. Without
     * one the line would turn amber with nothing to explain it, which is the worst of both:
     * enough signal to worry a reader and not enough to tell them what about.
     */
    if (behind.includes(task)) {
      lines.push(t('freshness.line.behind', { task: task.label }));
    }
    for (const part of task.resumeParts) {
      if (part === allowance) {
        if (allowanceSaid) continue;
        allowanceSaid = true;
      }
      lines.push(part);
      if (!resumes.includes(part)) resumes.push(part);
    }
    /*
     * The allowance reset is one calendar fact shared by every task waiting on it, so it is said
     * once however many tasks are waiting — de-duplicating whole paragraphs could not catch it,
     * because the paragraphs around it differ.
     */
    for (const part of task.mechanicsParts) {
      if (part === allowance) {
        if (allowanceSaid) continue;
        allowanceSaid = true;
      }
      /*
       * The mechanics sentence, filed under the task it was measured on. Its first letter is
       * lower-cased because it becomes a clause rather than a sentence — which works for both
       * languages here (English and French both write these words in lower case mid-sentence)
       * and is the line to revisit for a language that capitalises nouns.
       */
      const line = t('freshness.line.mechanics', {
        task: task.label,
        detail: `${part.charAt(0).toLowerCase()}${part.slice(1)}`,
      });
      if (!mechanics.includes(line)) mechanics.push(line);
    }
    noteTasks.push(task.name);
    paragraphs.push(lines.join(' '));
  }

  // Nothing is collected outside the loop above, so with no task in trouble both of these are
  // empty and the block keeps the one short line a healthy schedule has always had.
  const resume = resumes.length > 0 ? resumes.join(' ') : null;

  return {
    age: successes.length > 0 ? relativeTime(new Date(Math.max(...successes)).toISOString(), now) : null,
    neverRan: active.every(task => Boolean(scheduler.tasks[task.name]?.never_run)),
    tone: failing.length > 0 ? 'problem'
      : (paused.length > 0 || behind.length > 0) ? 'ageing'
        : successes.length > 0 ? 'ok' : 'unknown',
    note: paragraphs.length > 0 ? paragraphs.join(' ') : null,
    notes: paragraphs,
    mechanics,
    resume,
    // Which tasks the note speaks for, so their detail rows do not repeat it a few pixels below.
    noteTask: noteTasks[0] ?? null,
    noteTasks,
    present: true,
  };
}

/**
 * How current the FIXTURE side of this page is, in one line: what is on, when it kicks off, the
 * live score and the final result.
 *
 * Deliberately NOT the forecast clock. Model forecasts refresh on their own schedule under their
 * own allowance and are read separately by `forecastRefresh` — see the header of this file for the
 * bug that merging them caused.
 *
 * Every branch below is a different fact, and none of them is allowed to read as another:
 *
 *  - no status at all: we do not know. Not "up to date", not "out of date".
 *  - no scheduler block: this backend runs no scheduled refresh, so stored data only changes when
 *    somebody loads a page with refresh on. That is a real and important thing to say.
 *  - a scheduler that cannot reach its state store: it is running, but it cannot remember when
 *    anything ran, so no timestamp exists to show.
 *  - a scheduler where nothing has ever succeeded: "no scheduled refresh has run yet", never a
 *    borrowed time from somewhere else.
 *  - everything else: the most recent success across the enabled fixture tasks, with a pause or a
 *    failure as its own clause rather than folded into the headline.
 */
/*
 * The fixed statements used to be six `const`s here, so that each could be given once and then
 * both joined into `note` and listed in `notes` without the two copies drifting apart. They are
 * now catalogue keys (`freshness.note.*`), which keeps that guarantee — `t` of one key is one
 * string — and adds the one the constants could not have: they are produced in the reader's
 * language at the moment the panel renders, rather than in whichever language was active when
 * this module was first imported.
 */

export function freshnessSummary(
  status: ProviderStatus | null | undefined,
  now: number = Date.now(),
): FreshnessSummary {
  if (!status) {
    return {
      text: t('freshness.summary.unknown'),
      tone: 'unknown',
      note: t('freshness.note.noStatus'),
      notes: [t('freshness.note.noStatus')],
      resume: null,
      noteTask: null,
      noteTasks: [],
      scheduled: false,
    };
  }

  const scheduler = status.scheduler;
  if (!scheduler) {
    return {
      text: t('freshness.summary.noSchedule'),
      tone: 'unknown',
      note: t('freshness.note.noSchedule'),
      notes: [t('freshness.note.noSchedule')],
      resume: null,
      noteTask: null,
      noteTasks: [],
      scheduled: false,
    };
  }
  if (!scheduler.enabled) {
    return {
      text: t('freshness.summary.switchedOff'),
      tone: 'ageing',
      note: t('freshness.note.switchedOff'),
      notes: [t('freshness.note.switchedOff')],
      resume: null,
      noteTask: null,
      noteTasks: [],
      scheduled: true,
    };
  }
  if (!scheduler.state_store_available) {
    return {
      text: t('freshness.summary.noStateStore'),
      tone: 'unknown',
      note: t('freshness.note.noStateStore'),
      notes: [t('freshness.note.noStateStore')],
      resume: null,
      noteTask: null,
      noteTasks: [],
      scheduled: true,
    };
  }

  const fixtureNames = Object.keys(scheduler.tasks ?? {}).filter(name => !FORECAST_TASKS.includes(name));
  const state = clockState(scheduler, fixtureNames, now);

  if (!state.present) {
    // Every task this backend runs is a forecast task. Saying nothing about fixtures is the only
    // honest option: no task here refreshes them.
    return {
      text: t('freshness.summary.noFixtureTask'),
      tone: 'unknown',
      note: t('freshness.note.noFixtureTask'),
      notes: [t('freshness.note.noFixtureTask')],
      resume: null,
      noteTask: null,
      noteTasks: [],
      scheduled: true,
    };
  }

  return {
    text: state.age
      ? t('freshness.summary.refreshed', { age: state.age })
      : t(state.neverRan ? 'freshness.summary.neverRun' : 'freshness.summary.neverSucceeded'),
    tone: state.tone,
    note: state.note ?? (state.age ? null : t('freshness.note.noPassYet')),
    notes: state.notes.length > 0 ? state.notes : (state.age ? [] : [t('freshness.note.noPassYet')]),
    mechanics: state.mechanics ?? [],
    resume: state.resume,
    noteTask: state.noteTask,
    noteTasks: state.noteTasks,
    scheduled: true,
  };
}

/**
 * How current the MODEL FORECASTS are — the other clock, and on this installation usually the
 * older one.
 *
 * Null when the backend reports no per-task state at all, because then there is nothing to say
 * about forecasts SPECIFICALLY and the fixture line's "we do not know" already covers the page.
 * A forecast row that appeared with no task behind it could only be guessing.
 */
export function forecastRefresh(
  status: ProviderStatus | null | undefined,
  now: number = Date.now(),
): FreshnessSummary | null {
  const scheduler = status?.scheduler;
  if (!scheduler || !scheduler.enabled || !scheduler.state_store_available) return null;

  const names = FORECAST_TASKS.filter(name => scheduler.tasks?.[name]);
  if (names.length === 0) return null;

  const state = clockState(scheduler, names, now);
  if (!state.present) {
    return {
      text: t('freshness.forecasts.switchedOff'),
      tone: 'ageing',
      note: null,
      notes: [],
      resume: null,
      noteTask: null,
      noteTasks: [],
      scheduled: true,
    };
  }

  return {
    text: state.age
      ? t('freshness.forecasts.refreshed', { age: state.age })
      : t(state.neverRan ? 'freshness.forecasts.neverRun' : 'freshness.forecasts.neverSucceeded'),
    tone: state.tone,
    // No "nothing has completed a pass" fallback here: the fixture line above already carries it
    // when it applies, and the same sentence twice in one small block reads as two problems.
    note: state.note,
    notes: state.notes,
    mechanics: state.mechanics ?? [],
    resume: state.resume,
    noteTask: state.noteTask,
    noteTasks: state.noteTasks,
    scheduled: true,
  };
}

/** Both clocks, and the one tone and the one note the block as a whole should carry. */
export interface FreshnessReport {
  /** Fixtures, kick-off times, live scores and final results. */
  fixtures: FreshnessSummary;
  /** Model forecasts, on their own clock. Null when no per-task state exists to read. */
  forecasts: FreshnessSummary | null;
  /** The worse of the two, so the block never looks calmer than its unhappiest half. */
  tone: FreshnessTone;
  /**
   * The sentence a reader must see even if they never open the disclosure — a pause with its
   * resume time, a failure, or an "we do not know". De-duplicated: when both clocks are stopped
   * for the same reason it is stated once, because one fact printed twice reads as two faults.
   */
  note: string | null;
  /**
   * `note` as its separate statements, across both clocks and de-duplicated the same way.
   *
   * One per task in trouble, so a caller can lay them out as lines instead of one paragraph —
   * which is the difference between a two-task note being attributable and being readable.
   */
  notes: string[];
  /**
   * How the resume time was worked out, one line per task, for the opened detail only.
   *
   * The allowance's calendar and the backoff window are true and worth keeping, and they are not
   * what a reader on a match page is there for. See where they are built in describeTask.
   */
  mechanics?: string[];
  /**
   * The "when it comes back" sentences `note` already carries, across both clocks.
   *
   * A second source answers the same question — the provider budget, which the scheduler's task
   * state cannot see — and a caller holding both needs to know which sentences are already going
   * to be printed. Without it the choice is between saying it twice and saying it never, and the
   * block spent this round saying it never.
   */
  resume: string | null;
  noteTask: string | null;
  /** Every task `note` speaks for, across both clocks. */
  noteTasks: string[];
  scheduled: boolean;
}

/** The whole freshness answer for a page: two clocks, never merged into one. */
export function freshnessReport(
  status: ProviderStatus | null | undefined,
  now: number = Date.now(),
): FreshnessReport {
  const fixtures = freshnessSummary(status, now);
  const forecasts = forecastRefresh(status, now);

  // Statement by statement rather than clock by clock: two clocks stopped for the same reason
  // used to be de-duplicated only when their whole notes matched word for word.
  const notes: string[] = [];
  for (const note of [...fixtures.notes, ...(forecasts?.notes ?? [])]) {
    if (note && !notes.includes(note)) notes.push(note);
  }
  const mechanics: string[] = [];
  for (const line of [...(fixtures.mechanics ?? []), ...(forecasts?.mechanics ?? [])]) {
    if (line && !mechanics.includes(line)) mechanics.push(line);
  }
  const resumes: string[] = [];
  for (const resume of [fixtures.resume, forecasts?.resume ?? null]) {
    if (resume && !resumes.includes(resume)) resumes.push(resume);
  }

  return {
    fixtures,
    forecasts,
    tone: forecasts ? worseTone(fixtures.tone, forecasts.tone) : fixtures.tone,
    note: notes.length > 0 ? notes.join(' ') : null,
    notes,
    mechanics,
    resume: resumes.length > 0 ? resumes.join(' ') : null,
    noteTask: fixtures.noteTask ?? forecasts?.noteTask ?? null,
    noteTasks: [...new Set([...fixtures.noteTasks, ...(forecasts?.noteTasks ?? [])])],
    scheduled: fixtures.scheduled,
  };
}

/** What we last heard from the fixture provider itself — distinct from our own schedule. */
export interface RetrievalFact {
  /** The provider key at the head of the chain, e.g. "livescore". */
  provider: string;
  /** "12 minutes ago", or null when it has never answered. */
  relative: string | null;
  exact: string | null;
  /** The backend's wording for a pause on this provider, if any. */
  coolingDown: string | null;
}

/**
 * When the fixture provider last answered us.
 *
 * Read from the head of the provider chain, which is the one actually in use. Deliberately NOT
 * merged with the scheduler's success time: a scheduled pass can succeed without making a single
 * provider request, and a provider can answer a page load with no scheduled pass involved.
 */
export function retrievalFact(
  status: ProviderStatus | null | undefined,
  now: number = Date.now(),
): RetrievalFact | null {
  const active = status?.chain?.[0];
  if (!active) return null;
  return {
    provider: active.name,
    relative: relativeTime(active.last_success_at, now),
    exact: absoluteTime(active.last_success_at),
    coolingDown: active.cooling_down ?? null,
  };
}
