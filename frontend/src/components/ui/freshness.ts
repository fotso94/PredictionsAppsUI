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

/** What each scheduled task keeps current, in the reader's terms rather than the scheduler's. */
export const SYNC_TASK_LABEL: Record<string, string> = {
  fixtures: 'Fixtures and kick-off times',
  live: 'Live scores',
  results: 'Final results',
  forecasts: 'Model forecasts',
};

/** A task name this build has never heard of still reaches the reader, readably. */
export function syncTaskLabel(name: string): string {
  return SYNC_TASK_LABEL[name] ?? name.replace(/_/g, ' ');
}

/** The order the tasks read best in: what is on, then what is happening, then how it ended. */
const TASK_ORDER = ['fixtures', 'live', 'results', 'forecasts'];

/**
 * How each fixture provider is named on screen.
 *
 * One vocabulary, shared with DataSourceNotice, so the same provider is never called two
 * different things on one page. `sample` names itself as not real, because it is not.
 */
export const FIXTURE_PROVIDER_LABEL: Record<string, string> = {
  livescore: 'Live Score API',
  api_football: 'API-Football (fallback)',
  thesportsdb: 'TheSportsDB (fallback)',
  sample: 'sample data (not real fixtures)',
};

/** The display name for a fixture provider, falling back to the raw key rather than hiding it. */
export function fixtureProviderLabel(provider: string | null | undefined): string {
  return FIXTURE_PROVIDER_LABEL[provider ?? ''] ?? provider ?? 'no provider';
}

const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? '' : 's'}`;

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
  if (!iso) return null;
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? null : at.toLocaleString();
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

  if (seconds < 45) return past ? 'just now' : 'in under a minute';
  if (seconds < 90 * 60) {
    const minutes = Math.max(1, Math.round(seconds / 60));
    return past ? `${plural(minutes, 'minute')} ago` : `in ${plural(minutes, 'minute')}`;
  }
  if (seconds < 36 * 3600) {
    const hours = Math.round(seconds / 3600);
    return past ? `${plural(hours, 'hour')} ago` : `in ${plural(hours, 'hour')}`;
  }
  const days = Math.round(seconds / 86400);
  return past ? `${plural(days, 'day')} ago` : `in ${plural(days, 'day')}`;
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
  return `Our daily request allowance is counted per UTC day, so it resets at 00:00 UTC${when ? ` — ${when}` : ''}.`;
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
  /** True when the task has never completed a run: no time exists, and none is invented. */
  neverRun: boolean;
  /** The backend's own reason for the pause or the failure. Null when neither applies. */
  reason: string | null;
  /** When it comes back — the sentence that makes a pause useful instead of merely alarming. */
  resume: string | null;
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
function cadenceNote(task: SyncTaskState): string | null {
  if (!task.interval_seconds) return null;
  const hours = task.interval_seconds / 3600;
  return hours >= 1
    ? `Scheduled every ${plural(Math.round(hours), 'hour')}.`
    : `Scheduled every ${plural(Math.round(task.interval_seconds / 60), 'minute')}.`;
}

/** Everything the reader needs about one task, in the backend's words wherever it supplied them. */
export function describeTask(name: string, task: SyncTaskState, now: number = Date.now()): TaskFreshness {
  const label = syncTaskLabel(name);

  if (!task.enabled) {
    return {
      name, label, text: 'switched off', tone: 'unknown', exact: null,
      paused: false, failing: false, neverRun: Boolean(task.never_run), reason: null, resume: null,
      detail: ['This task is not switched on for this installation, so nothing refreshes it automatically.'],
    };
  }

  const paused = Boolean(task.last_skip_reason);
  const failing = task.consecutive_failures > 0;
  const reason = paused
    ? task.last_skip_reason
    : failing
      ? (task.last_error ?? 'The backend did not report why the last attempt failed.')
      : null;

  /*
   * The resume statement, which is the whole point of showing a pause at all. "Paused" tells a
   * reader nothing they can do anything with; "updates resume after 00:00 UTC, in about 7 hours"
   * does. The allowance sentence is added only when the backend's own reason says the allowance
   * is what stopped it — never as a general explanation for every pause.
   */
  const resumeParts: string[] = [];
  if (paused && isAllowanceSkip(task.last_skip_reason)) resumeParts.push(allowanceResetNote(now));
  const nextDue = relativeTime(task.next_due_at, now);
  if (nextDue) resumeParts.push(`The next attempt is ${nextDue}.`);
  if (task.backoff_seconds) {
    resumeParts.push(`After ${plural(task.consecutive_failures, 'failure')} in a row it is waiting `
      + `${plural(Math.max(1, Math.round(task.backoff_seconds / 60)), 'minute')} before trying again.`);
  }
  const resume = resumeParts.length > 0 ? resumeParts.join(' ') : null;

  const behind = taskIsBehind(task, now);
  const detail: string[] = [];
  const add = (line: string | null | undefined) => {
    const text = (line ?? '').trim();
    if (text && !detail.includes(text)) detail.push(text);
  };
  if (paused) add(sentence(`Paused: ${reason}`));
  if (failing) add(sentence(`Last attempt failed: ${reason}`));
  if (behind && !paused && !failing) add('This task is more than a full interval past due.');
  add(resume);
  add(cadenceNote(task));

  // A task that has never run has no timestamp, and none is borrowed from anywhere else.
  if (task.never_run || !task.last_success_at) {
    return {
      name,
      label,
      text: paused ? 'has never run — paused' : 'has never run',
      tone: failing ? 'problem' : paused ? 'ageing' : 'unknown',
      exact: null,
      paused,
      failing,
      neverRun: true,
      reason,
      resume,
      detail,
    };
  }

  return {
    name,
    label,
    text: `updated ${relativeTime(task.last_success_at, now) ?? absoluteTime(task.last_success_at)}`,
    tone: failing ? 'problem' : (paused || behind) ? 'ageing' : 'ok',
    exact: absoluteTime(task.last_success_at),
    paused,
    failing,
    neverRun: false,
    reason,
    resume,
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
   * The task `note` is about, when it is about one.
   *
   * Only so the detail rows can avoid printing the same pause twice; it is never used to suppress
   * a DIFFERENT task's lines, which is how a real problem would end up hidden behind a coincidence
   * of identical wording.
   */
  noteTask: string | null;
  /** True when the backend reported a scheduler at all. */
  scheduled: boolean;
}

/** The phrase every branch opens with. Nothing on any page is live, and it never pretends to be. */
const STORED = 'Stored data';

/**
 * How current this page is, in one line.
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
 *  - everything else: the most recent success across the enabled tasks, with a pause or a failure
 *    as its own clause rather than folded into the headline.
 */
export function freshnessSummary(
  status: ProviderStatus | null | undefined,
  now: number = Date.now(),
): FreshnessSummary {
  if (!status) {
    return {
      text: `${STORED} · how current it is cannot be stated`,
      tone: 'unknown',
      note: 'The status service could not be reached, so when this was last refreshed is unknown.',
      noteTask: null,
      scheduled: false,
    };
  }

  const scheduler = status.scheduler;
  if (!scheduler) {
    return {
      text: `${STORED} · no scheduled refresh is reported`,
      tone: 'unknown',
      note: 'This installation reports no refresh schedule, so stored data changes only when a page asks the provider for new data.',
      noteTask: null,
      scheduled: false,
    };
  }
  if (!scheduler.enabled) {
    return {
      text: `${STORED} · scheduled refresh is switched off`,
      tone: 'ageing',
      note: 'Automatic refreshes are switched off here. What is stored stays as it is until somebody refreshes it.',
      noteTask: null,
      scheduled: true,
    };
  }
  if (!scheduler.state_store_available) {
    return {
      text: `${STORED} · when it last refreshed is unknown`,
      tone: 'unknown',
      note: 'The scheduler cannot reach its state store, so it cannot report when any task last ran.',
      noteTask: null,
      scheduled: true,
    };
  }

  const active = describeTasks(scheduler, now).filter(task => scheduler.tasks[task.name]?.enabled !== false);

  const successes = active
    .map(task => Date.parse(scheduler.tasks[task.name]?.last_success_at ?? ''))
    .filter(value => !Number.isNaN(value));

  const paused = active.filter(task => task.paused);
  const failing = active.filter(task => task.failing);
  const behind = active.filter(task => taskIsBehind(scheduler.tasks[task.name], now));

  /*
   * A pause and a failure are different states and get different sentences. A failure leads,
   * because it is the one that means something is wrong; a pause is expected behaviour on a trial
   * plan and reads as such, with the time it comes back attached.
   */
  const names = (list: TaskFreshness[]) => list.map(task => task.label).join(' and ');
  const failNote = failing.length > 0
    ? sentence(`${names(failing)}: last attempt failed — ${failing[0].reason}`)
    : null;
  const pauseNote = paused.length > 0
    ? [sentence(`${names(paused)}: paused — ${paused[0].reason}`), paused[0].resume]
      .filter(Boolean).join(' ')
    : null;
  /*
   * A task that is simply late is the third case, and it needs a sentence of its own. Without one
   * the line would turn amber with nothing to explain it, which is the worst of both: enough
   * signal to worry a reader and not enough to tell them what about.
   */
  const behindNote = behind.length > 0
    ? `${names(behind)} ${behind.length === 1 ? 'is' : 'are'} more than a full interval past due, `
      + 'so what is stored may be older than the schedule intends.'
    : null;

  // Which task the note speaks for, so its detail row does not repeat it a few pixels below.
  const noteTask = failNote ? failing[0].name
    : pauseNote ? paused[0].name
      : behindNote ? behind[0].name : null;

  if (successes.length === 0) {
    return {
      text: `${STORED} · no scheduled refresh has run yet`,
      tone: failing.length > 0 ? 'problem' : paused.length > 0 ? 'ageing' : 'unknown',
      note: failNote ?? pauseNote ?? behindNote
        ?? 'The scheduler is running but no task has completed a pass yet, so there is no refresh time to report.',
      noteTask: noteTask,
      scheduled: true,
    };
  }

  const latest = new Date(Math.max(...successes)).toISOString();
  return {
    text: `${STORED} · last refreshed ${relativeTime(latest, now)}`,
    tone: failing.length > 0 ? 'problem' : (paused.length > 0 || behind.length > 0) ? 'ageing' : 'ok',
    note: failNote ?? pauseNote ?? behindNote,
    noteTask: noteTask,
    scheduled: true,
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
