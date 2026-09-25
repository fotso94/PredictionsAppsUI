import { Page, Route, Request } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Read the captured payloads at run time rather than importing them: Playwright runs these files as
// ES modules, where a JSON import would need an import attribute, and the fixtures are data anyway.
const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');
const load = <T>(name: string): T => JSON.parse(readFileSync(join(FIXTURES, name), 'utf8')) as T;

const matchesDay = load<DayPayload>('matches-day.json');
const providerStatus = load<ProviderStatusPayload>('provider-status.json');
const coverage = load<Json>('coverage.json');
const leagues = load<LeaguesPayload>('leagues.json');

/**
 * Backend stubbing for the deterministic browser tests.
 *
 * The payloads in e2e/fixtures were captured from the real local backend and sanitised. Building
 * every scenario out of those captures means the tests assert against the shape the backend
 * actually serves, while never touching a provider or spending a trial request.
 */

/** Backend payloads are steered field by field here, so an index signature is the honest shape. */
export type Json = Record<string, unknown>;

export interface ForecastMarkets {
  match_result: boolean;
  btts: boolean;
  over_under_25: boolean;
  over_under_35: boolean;
  exact_score: boolean;
}

export interface ApiForecast extends Json {
  markets_available: ForecastMarkets;
  home_win_prob: number | null;
  draw_prob: number | null;
  away_win_prob: number | null;
  btts_yes_prob: number | null;
  btts_no_prob: number | null;
  total_goals_over_25_prob: number | null;
  total_goals_under_25_prob: number | null;
  total_goals_over_35_prob: number | null;
  total_goals_under_35_prob: number | null;
  exact_score: Record<string, number> | null;
  exact_score_other_prob: number | null;
  anomalies?: Array<{ severity: 'warning' | 'note'; code: string; message: string }>;
}

export interface ApiTeamRef extends Json {
  id: string;
  name: string;
  short_name: string | null;
  logo: string;
  country: string | null;
}

export interface ApiMatch extends Json {
  id: string;
  kickoff_utc: string;
  status: string;
  home?: ApiTeamRef;
  away?: ApiTeamRef;
  forecast: ApiForecast | null;
  forecast_state?: string;
  /**
   * The backend's own deadline for a result: the kickoff plus `UNSETTLED_GRACE`.
   *
   * Optional because the captured payloads predate it, which is deliberate rather than tolerated —
   * a fixture with no deadline is one the application makes no overdue claim about at all, so
   * every existing test keeps measuring what it always measured. e2e/mocked/overdue-results.spec.ts
   * sets it when that is what it is testing.
   */
  result_expected_by?: string | null;
  /** The stale sweep's record: what has been tried, and whether the backend has stopped asking. */
  recovery?: Json | null;
  /**
   * The full evidence brief, which only `GET /matches/{id}` carries (see matchDetail()). Typed as
   * plain Json here because the tests never build one: it is captured, and the shape it has to
   * keep is the backend's, in src/types/brief.ts.
   */
  brief?: Json | null;
}

export interface DayPayload extends Json {
  date: string;
  matches: ApiMatch[];
}

export interface ProviderBudgetPayload extends Json {
  provider: string;
  daily_limit: number;
  used_today: number;
  refused_today: number;
  remaining_today: number | null;
  enforced: boolean;
}

export interface ProviderChainEntryPayload extends Json {
  name: string;
  cooling_down: string | null;
  last_error: string | null;
  last_error_at: string | null;
  last_success_at: string | null;
}

/**
 * One scheduled refresh task, as `GET /data-providers/status` reports it.
 *
 * `never_run` with null timestamps and `last_skip_reason` with neither a success nor a failure are
 * both real states the backend publishes, and both have their own wording in the interface — so
 * the builders below construct them exactly, rather than approximating them with an old timestamp.
 */
export interface SyncTaskPayload extends Json {
  enabled: boolean;
  interval_seconds: number;
  never_run: boolean;
  last_run_at: string | null;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error: string | null;
  last_duration_ms: number | null;
  last_result: Json | null;
  last_skipped_at: string | null;
  last_skip_reason: string | null;
  runs: number;
  failures: number;
  consecutive_failures: number;
  backoff_seconds: number | null;
  next_due_at: string | null;
  due_now: boolean;
  reason_not_due: string | null;
}

export interface SchedulerPayload extends Json {
  enabled: boolean;
  running: boolean;
  tick_seconds: number;
  startup_delay_seconds: number;
  budget_reserve: number;
  enabled_tasks: string[];
  state_store_available: boolean;
  tasks: Record<string, SyncTaskPayload>;
}

export interface ProviderStatusPayload extends Json {
  chain: ProviderChainEntryPayload[];
  forecasts: {
    budget: ProviderBudgetPayload | null;
    cooling_down: string | null;
  } & Json;
  scheduler?: SchedulerPayload | null;
}

export interface LeaguesPayload extends Json {
  competitions?: Json[];
}

// ------------------------------------------------------------------- scheduled refresh (freshness)
/**
 * Scheduler payloads are built here rather than captured, because every interesting state is a
 * state of the CLOCK: "refreshed four minutes ago" and "next attempt in twenty minutes" have to be
 * relative to when the test runs or they decay into "two days ago" the moment the capture ages.
 */
const ago = (minutes: number): string => new Date(Date.now() - minutes * 60_000).toISOString();
const ahead = (minutes: number): string => new Date(Date.now() + minutes * 60_000).toISOString();

/** A task that has never completed a pass: no timestamps exist, and none may be invented. */
export function neverRunTask(intervalSeconds: number, overrides: Partial<SyncTaskPayload> = {}): SyncTaskPayload {
  return {
    enabled: true,
    interval_seconds: intervalSeconds,
    never_run: true,
    last_run_at: null,
    last_success_at: null,
    last_error_at: null,
    last_error: null,
    last_duration_ms: null,
    last_result: null,
    last_skipped_at: null,
    last_skip_reason: null,
    runs: 0,
    failures: 0,
    consecutive_failures: 0,
    backoff_seconds: null,
    next_due_at: null,
    due_now: true,
    reason_not_due: null,
    ...overrides,
  };
}

/** A task that last succeeded `minutesAgo` ago and is next due `minutesAhead` from now. */
export function healthyTask(
  intervalSeconds: number, minutesAgo: number, minutesAhead: number,
  overrides: Partial<SyncTaskPayload> = {},
): SyncTaskPayload {
  return {
    ...neverRunTask(intervalSeconds),
    never_run: false,
    last_run_at: ago(minutesAgo),
    last_success_at: ago(minutesAgo),
    last_duration_ms: 812,
    last_result: { days: {}, errors: [] },
    runs: 4,
    next_due_at: ahead(minutesAhead),
    due_now: false,
    reason_not_due: `next due at ${ahead(minutesAhead)}`,
    ...overrides,
  };
}

/**
 * A task that is deliberately doing nothing because the daily allowance is spent.
 *
 * Neither a success nor a failure: `last_skip_reason` is set, the counters stay at zero and
 * `next_due_at` says when it will try again. This is the real state of the forecasts task on the
 * local installation, which is why it has its own builder.
 */
export function pausedTask(
  intervalSeconds: number, minutesAhead: number, reason: string,
  overrides: Partial<SyncTaskPayload> = {},
): SyncTaskPayload {
  return {
    ...neverRunTask(intervalSeconds),
    last_skipped_at: ago(2),
    last_skip_reason: reason,
    next_due_at: ahead(minutesAhead),
    due_now: false,
    reason_not_due: `next due at ${ahead(minutesAhead)}`,
    ...overrides,
  };
}

/** Every task refreshing normally. This is what `baseStatus()` carries. */
export function healthyScheduler(overrides: Partial<SchedulerPayload> = {}): SchedulerPayload {
  return {
    enabled: true,
    running: true,
    tick_seconds: 60,
    startup_delay_seconds: 120,
    budget_reserve: 50,
    enabled_tasks: ['fixtures', 'live', 'results', 'forecasts'],
    state_store_available: true,
    tasks: {
      fixtures: healthyTask(21_600, 12, 348),
      live: healthyTask(120, 1, 1, {
        last_result: { live_window_open: false, live_polled: false, note: 'no covered match is in its live window; no provider request made' },
      }),
      results: healthyTask(1800, 8, 22),
      forecasts: healthyTask(21_600, 40, 320),
    },
    ...overrides,
  };
}

/** The scheduler is up, but not one task has ever completed a pass. */
export function neverRunScheduler(): SchedulerPayload {
  return healthyScheduler({
    tasks: {
      fixtures: neverRunTask(21_600),
      live: neverRunTask(120),
      results: neverRunTask(1800),
      forecasts: neverRunTask(21_600),
    },
  });
}

/** Fixtures and results are current; the forecast refresh is paused on a spent allowance. */
export function pausedScheduler(): SchedulerPayload {
  const scheduler = healthyScheduler();
  scheduler.tasks.forecasts = pausedTask(
    21_600, 95,
    'daily request budget for gameforecast is spent (8/8 used; 0 held back for page loads)',
  );
  return scheduler;
}

// ------------------------------------------------------------- the captured day, served as today
/**
 * THE CAPTURE IS ONE DAY OF FOOTBALL, AND IT IS SERVED AS TODAY'S.
 *
 * Every fixture in e2e/fixtures/matches-day.json kicks off on the day it was captured, and served
 * verbatim that date walks away from the day the suite is run. It is not a cosmetic drift: a
 * fixture reached through a follow is cut from the dashboard feed by `buildFeed` once its kick-off
 * is more than FEED_DAYS_BACK behind now (src/services/favourites.service.ts), and with nothing
 * left to show the feed's panel is replaced by an empty state. A test that walks that feed on a
 * verbatim capture therefore states something true of the days just after the capture and false
 * of every day after that, and turns red on the morning the gap crosses the boundary with nothing
 * changed but the calendar. A suite that expires by the date is not evidence for its own history.
 *
 * So the capture is moved onto the current day by a WHOLE NUMBER OF DAYS, the same day
 * `localDay(0)` hands the specs for their `?date=` parameters. Whole days is what keeps a capture
 * a capture: every fixture keeps the time of day it really kicked off at, and the order and the
 * gaps within the day are untouched. Nothing but the kick-offs and the day's own date is
 * rewritten. The rest of this file already states time this way — ago(), ahead() and isoDay() are
 * all relative to now — and the captured day was the one payload that was not.
 *
 * WHAT IS NOT MOVED, and why. `fetched_at`, the provider status and every timestamp inside a
 * brief EXCEPT the kick-off are the backend's own statements about when it looked and what it had
 * measured by then. Those are not properties of the fixture, and a test that needs one of them
 * recent builds it with ago() rather than asking the capture to pretend it was taken this morning.
 */
const CAPTURED_DAY = matchesDay.date;

/**
 * Whole days from the captured day to today's, in milliseconds.
 *
 * Fixed on first use rather than recomputed per call, so that a run which crosses local midnight
 * serves one self-consistent day throughout instead of moving its fixtures under itself.
 */
let capturedDayShift: number | null = null;
const captureShiftMs = (): number => {
  if (capturedDayShift === null) {
    const days = Math.round(
      (Date.parse(`${localDay(0)}T00:00:00Z`) - Date.parse(`${CAPTURED_DAY}T00:00:00Z`)) / 86_400_000,
    );
    capturedDayShift = days * 86_400_000;
  }
  return capturedDayShift;
};

/**
 * An instant moved by the whole-day shift, in the `...:00Z` spelling the capture writes.
 *
 * The captured kick-offs are whole minutes, so dropping the `.000` `toISOString` adds loses
 * nothing; an unreadable value is handed back untouched rather than turned into a guess.
 */
const shifted = (iso: string): string => {
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return iso;
  return new Date(at + captureShiftMs()).toISOString().replace(/\.000Z$/, 'Z');
};

/**
 * One captured fixture with its kick-off on today's date.
 *
 * The brief's `known.kickoff_utc` is the same fixture's kick-off stated a second time, so it moves
 * with it; nothing else in the brief does. Mutates in place, and every caller below hands it a
 * fresh deep copy of the capture.
 */
const onToday = (match: ApiMatch): ApiMatch => {
  if (captureShiftMs() === 0) return match;
  match.kickoff_utc = shifted(match.kickoff_utc);
  const known = (match.brief as { known?: { kickoff_utc?: string | null } } | null | undefined)?.known;
  if (known && typeof known.kickoff_utc === 'string') known.kickoff_utc = shifted(known.kickoff_utc);
  return match;
};

/** The date the captured day is served under: its own, moved onto today's. */
const capturedDayIso = (): string =>
  new Date(Date.parse(`${CAPTURED_DAY}T00:00:00Z`) + captureShiftMs()).toISOString().slice(0, 10);

/**
 * The captured fixtures AS A LIST PAYLOAD SERVES THEM — which is to say without the full brief.
 *
 * `build_match_payloads(..., full_brief=False)` is what answers `GET /matches`: every fixture in a
 * list carries the compact brief and none of them carries the full one, which is added only by the
 * detail endpoint. Dropping it here is what keeps that true of the stub, and it also keeps the
 * derived fixtures honest: withoutMarkets(), withInconsistentNumbers() and the rest edit a
 * forecast, and a brief assembled from the forecast BEFORE that edit would then contradict it —
 * the brief is the backend's finished statement about a payload, not something a test may reshape.
 * A test that wants the detail payload asks for it by name, with matchDetail().
 *
 * Kick-offs are on today's date, by the whole-day move CAPTURED_DAY describes.
 */
export const baseMatches = (): ApiMatch[] => (JSON.parse(JSON.stringify(matchesDay.matches)) as ApiMatch[])
  .map(match => { delete match.brief; return onToday(match); });

export const baseDayPayload = (): DayPayload => {
  const payload = JSON.parse(JSON.stringify(matchesDay)) as DayPayload;
  payload.date = capturedDayIso();
  payload.matches = baseMatches();
  return payload;
};

/**
 * One captured fixture AS `GET /matches/{id}` SERVES IT: the same payload plus the full brief,
 * which is the only endpoint that carries it (`full_brief=True`).
 *
 * Only the first captured fixture has a brief — the capture predates them, and one brief is what
 * a test of the evidence panel needs; the others would only be the same shape again. It was built
 * on 2026-09-19 by `app/services/match_brief.py::build_brief` from that fixture's own payload and
 * forecast, with `now` fixed at the capture's `fetched_at`, so nothing in it is invented: its
 * sentences are the builder's, and its reliability block carries the scoring position this
 * installation actually held (4 of 4 eligible predictions scored, no source and market at the
 * minimum of 30, so no figure published). Rebuild it the same way if the builder changes.
 *
 * WHY THIS IS OPT-IN rather than the default answer of the detail route. A brief changes the
 * geometry of the match page: attaching this one moves the model forecast table from 1,191px to
 * 1,462px down a 390px phone — both measured — because the panel gains the brief's headline, its
 * markets-not-published row and the backend's own accuracy sentence.
 * e2e/mocked/clutter.spec.ts bounds that distance at 1,280px, and
 * that bound is a real guard against the clutter creeping back, so a test either asks for the
 * detail payload deliberately, with `matchById: matchDetail`, or it measures the page the rest of
 * the suite measures. Neither is the wrong page; they are different pages, and which one a test
 * stands on should be visible in the test.
 */
export const matchDetail = (id: string): ApiMatch | null => {
  const captured = (JSON.parse(JSON.stringify(matchesDay.matches)) as ApiMatch[]).find(m => m.id === id);
  return captured ? onToday(captured) : null;
};

/**
 * A healthy baseline. The capture was taken with the GameForecast daily allowance already spent, so
 * the pause is cleared here; quotaExhaustedStatus() puts it back when a test wants that state.
 */
export const baseStatus = (): ProviderStatusPayload => {
  const status = JSON.parse(JSON.stringify(providerStatus));
  status.forecasts.cooling_down = null;
  if (status.forecasts.budget) {
    status.forecasts.budget = { ...status.forecasts.budget, used_today: 2, refused_today: 0, remaining_today: 6 };
  }
  for (const entry of status.chain || []) {
    entry.cooling_down = null;
    entry.last_error = null;
    entry.last_error_at = null;
    // The capture predates the scheduler, so its success time is a day old. A healthy baseline
    // needs a recent one, or every page would open saying the provider has not answered in a day.
    entry.last_success_at = ago(12);
  }
  // The capture predates the scheduler entirely; a healthy baseline carries a healthy one.
  status.scheduler = healthyScheduler();
  return status;
};

/** The capture exactly as it came off the local backend, pause and all. */
export const capturedStatus = (): ProviderStatusPayload => JSON.parse(JSON.stringify(providerStatus)) as ProviderStatusPayload;
export const baseCoverage = (): Json => JSON.parse(JSON.stringify(coverage)) as Json;
export const baseLeagues = (): LeaguesPayload => JSON.parse(JSON.stringify(leagues)) as LeaguesPayload;

/** A day payload whose matches are rescheduled onto `isoDate`, so "today" always has content. */
export function dayPayload(isoDate: string, matches?: ApiMatch[]): DayPayload {
  const payload = baseDayPayload();
  const list = matches ?? baseMatches();
  payload.date = isoDate;
  payload.matches = list.map((match, index) => ({
    ...match,
    kickoff_utc: `${isoDate}T${String(12 + (index % 8)).padStart(2, '0')}:00:00Z`,
  }));
  return payload;
}

export function emptyDayPayload(isoDate: string): DayPayload {
  const payload = baseDayPayload();
  payload.date = isoDate;
  payload.matches = [];
  return payload;
}

/**
 * A captured fixture rescheduled onto `kickoffUtc` and renamed, so a test can look for it on the
 * page by club name. Everything else — competition, forecast, status — is the real captured shape.
 */
export function fixtureAt(kickoffUtc: string, homeName: string, awayName: string, id?: string): ApiMatch {
  const match = JSON.parse(JSON.stringify(baseMatches()[0])) as ApiMatch;
  match.id = id ?? `${homeName}-${awayName}-${kickoffUtc}`.replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase();
  match.kickoff_utc = kickoffUtc;
  match.status = 'scheduled';
  if (match.home) { match.home.name = homeName; match.home.short_name = homeName; }
  if (match.away) { match.away.name = awayName; match.away.short_name = awayName; }
  return match;
}

/**
 * The backend's own day-selection rule, applied to a fixed pool of fixtures.
 *
 * `backend/app/api/v1/endpoints/matches.py::local_day_window` selects the half-open UTC window
 * ``[local midnight, next local midnight)`` from the caller's `tz_offset` (minutes east of UTC at
 * local midnight) and `tz_offset_end` (the offset at the NEXT local midnight — they differ by an
 * hour on a daylight-saving transition, when the local day is 23 or 25 hours rather than 24).
 * Reimplementing exactly that here means a test can assert what the VIEWER ends up seeing: if the
 * client sent offsets that do not bound its own calendar day, an edge-of-day fixture drops out of
 * the response and disappears from the page.
 *
 * A request with no `tz_offset` is answered by the UTC calendar day, which is what the backend
 * falls back to — so a client that stops sending the offsets fails these tests rather than
 * silently reverting to UTC bucketing.
 */
export function selectLocalDay(pool: ApiMatch[], isoDate: string, params: URLSearchParams): DayPayload {
  const midnightUtc = Date.parse(`${isoDate}T00:00:00Z`);
  const DAY_MS = 24 * 60 * 60 * 1000;
  const rawStart = params.get('tz_offset');
  const rawEnd = params.get('tz_offset_end');
  const startOffset = rawStart === null ? 0 : Number(rawStart);
  const endOffset = rawEnd === null ? startOffset : Number(rawEnd);

  let from = midnightUtc - startOffset * 60_000;
  let to = midnightUtc + DAY_MS - endOffset * 60_000;
  // The backend ignores a nonsensical pair rather than returning an empty day; mirror that.
  if (!(to > from)) to = from + DAY_MS;
  if (Number.isNaN(from) || Number.isNaN(to)) { from = midnightUtc; to = midnightUtc + DAY_MS; }

  const payload = baseDayPayload();
  payload.date = isoDate;
  payload.matches = pool.filter(match => {
    const kickoff = Date.parse(match.kickoff_utc);
    return kickoff >= from && kickoff < to;
  });
  return payload;
}

/** Strip named markets from a forecast so the UI must show "unavailable" rather than 0%. */
export function withoutMarkets(match: ApiMatch, markets: Array<'match_result' | 'btts' | 'over_under_25' | 'over_under_35' | 'exact_score'>): ApiMatch {
  const copy = JSON.parse(JSON.stringify(match)) as ApiMatch;
  const forecast = copy.forecast;
  if (!forecast) return copy;
  for (const market of markets) {
    forecast.markets_available[market] = false;
    if (market === 'match_result') {
      forecast.home_win_prob = null;
      forecast.draw_prob = null;
      forecast.away_win_prob = null;
    }
    if (market === 'btts') {
      forecast.btts_yes_prob = null;
      forecast.btts_no_prob = null;
    }
    if (market === 'over_under_25') {
      forecast.total_goals_over_25_prob = null;
      forecast.total_goals_under_25_prob = null;
    }
    if (market === 'over_under_35') {
      forecast.total_goals_over_35_prob = null;
      forecast.total_goals_under_35_prob = null;
    }
    if (market === 'exact_score') {
      forecast.exact_score = null;
      forecast.exact_score_other_prob = null;
    }
  }
  return copy;
}

/** A forecast whose numbers do not hold together: the reader must be cautioned. */
export function withInconsistentNumbers(match: ApiMatch): ApiMatch {
  const copy = JSON.parse(JSON.stringify(match)) as ApiMatch;
  copy.forecast!.home_win_prob = 0.7;
  copy.forecast!.draw_prob = 0.3;
  copy.forecast!.away_win_prob = 0.22;
  copy.forecast!.anomalies = [
    { severity: 'warning', code: 'sum_out_of_tolerance', message: 'match result probabilities sum to 122.0%' },
  ];
  return copy;
}

/** Bookkeeping the backend recorded, which says nothing about whether the forecast is sound. */
export function withHarmlessNote(match: ApiMatch): ApiMatch {
  const copy = JSON.parse(JSON.stringify(match)) as ApiMatch;
  copy.forecast!.anomalies = [
    { severity: 'note', code: 'score_zero_dropped', message: 'a scoreline the provider gave a 0% chance was left out' },
  ];
  return copy;
}

/** The regression this whole parser change exists for: a genuine 1% must never read as 100%. */
export function withOnePercentFavourite(match: ApiMatch): ApiMatch {
  const copy = JSON.parse(JSON.stringify(match)) as ApiMatch;
  copy.forecast.home_win_prob = 0.01;
  copy.forecast.draw_prob = 0.01;
  copy.forecast.away_win_prob = 0.98;
  copy.forecast.exact_score = { '0-3': 0.01, '0-2': 0.02 };
  copy.forecast.exact_score_other_prob = 0.97;
  return copy;
}

export function withoutForecast(match: ApiMatch): ApiMatch {
  const copy = JSON.parse(JSON.stringify(match)) as ApiMatch;
  copy.forecast = null;
  copy.forecast_state = 'unavailable';
  return copy;
}

/** Provider status describing a spent daily allowance: refreshes are paused, not broken. */
export function quotaExhaustedStatus(): ProviderStatusPayload {
  const status = baseStatus();
  status.forecasts.budget = {
    provider: 'gameforecast', daily_limit: 8, used_today: 8, refused_today: 2,
    remaining_today: 0, enforced: true,
  };
  status.forecasts.cooling_down = 'daily request allowance for gameforecast is spent';
  // The scheduler is the half of this state that says when it comes back.
  status.scheduler = pausedScheduler();
  return status;
}

/** A backend that runs no scheduler at all: nothing refreshes unless a page asks for it. */
export function noSchedulerStatus(): ProviderStatusPayload {
  const status = baseStatus();
  delete status.scheduler;
  return status;
}

/** The scheduler is up and has never completed a pass. */
export function neverRunSchedulerStatus(): ProviderStatusPayload {
  const status = baseStatus();
  status.scheduler = neverRunScheduler();
  // Nothing has been retrieved either: a scheduler that has never run has fetched nothing.
  for (const entry of status.chain || []) entry.last_success_at = null;
  return status;
}

/** Fixtures current, forecast refresh paused on a spent allowance with a next-due time. */
export function pausedSchedulerStatus(): ProviderStatusPayload {
  const status = baseStatus();
  status.scheduler = pausedScheduler();
  return status;
}

// ------------------------------------------------------------------- the measured record
/**
 * `GET /api/v1/performance/sources`.
 *
 * Built rather than captured for the same reason as the scheduler: the local database has nothing
 * scored, so a capture could only ever produce the empty case. The wording of every definition,
 * rule and refusal below is copied verbatim from `backend/app/services/settlement.py`, so a test
 * that asserts on it is asserting on the sentence the backend really serves.
 */
export interface MeasuredMarketPayload extends Json {
  market: string;
  rule: string;
  scored: number;
  hits: number;
  pushes: number;
  voids: number;
  not_scored: number;
  hit_rate: number | null;
  hit_rate_available: boolean;
  hit_rate_sample: number;
  hit_rate_unavailable_reason: string | null;
  hit_rate_definition: string;
  brier_score: number | null;
  brier_available: boolean;
  brier_unavailable_reason: string | null;
  brier_definition: string;
  brier_baseline: number | null;
  brier_sample: number;
  mean_probability_of_actual: number | null;
  mean_probability_of_actual_definition: string;
  mean_probability_of_actual_sample: number;
}

export interface MeasuredSourcePayload extends Json {
  source_type: string;
  source_id: string;
  source_label: string;
  eligible: number;
  scored: number;
  pending: number;
  void: number;
  not_scored: number;
  not_scored_reasons: Array<{ reason: string; count: number }>;
  markets: MeasuredMarketPayload[];
  measured: boolean;
  not_measured_reason: string | null;
}

export interface PerformancePayload extends Json {
  window: { start: string; end: string; basis: string };
  minimum_sample: number;
  minimum_sample_rationale: string;
  rules: Json;
  sources: MeasuredSourcePayload[];
  sources_measured: number;
  not_measured_reason: string | null;
  measured_at: string;
}

/** The backend's minimum before any headline figure is published. */
export const MINIMUM_SAMPLE = 30;

const MINIMUM_SAMPLE_RATIONALE =
  'An accuracy figure is only published once at least 30 predictions from that source have been '
  + 'scored. At a hit rate near 50% the standard error is 0.5/sqrt(n), so a rate computed from '
  + 'fewer than 30 results carries a 95% interval wider than +/- 18 percentage points and would '
  + 'mislead. The counts behind it are published either way.';

const HIT_RATE_DEFINITION =
  'Share of scored predictions whose single most likely published outcome was the outcome that '
  + 'occurred. Voids, pushes and markets the source did not publish are excluded from both the '
  + 'numerator and the denominator.';

const BRIER_DEFINITION =
  'Brier score, the mean squared error of the published probabilities against what happened. '
  + '0 is perfect, lower is better.';

const MATCH_RESULT_RULE =
  '1X2 on the regulation-time score. Hit test: the single highest of the three published '
  + 'probabilities is compared with the outcome that occurred.';

const RULES: Json = {
  version: 'soccer-regulation-time-v1',
  basis: 'Regulation time only: the score after 90 minutes plus stoppage time, as published by the '
    + 'data provider that supplied the result.',
  void: 'A fixture that was postponed, cancelled or abandoned is VOID for every market. A void is '
    + 'never a loss, never a win, and never enters a hit rate or a Brier score.',
  unsupplied_market: 'A market the source did not publish is not scored at all. It is never counted '
    + 'as a loss and never read as a zero probability.',
  prematch_only: 'Only evidence that existed before kickoff is scored.',
  markets: { match_result: MATCH_RESULT_RULE },
  probability_of_actual: 'The probability the source itself published for the outcome that actually occurred.',
  brier: BRIER_DEFINITION,
  brier_baselines: { match_result: 0.6667 },
  hit_rate: HIT_RATE_DEFINITION,
  minimum_sample: MINIMUM_SAMPLE,
  minimum_sample_rationale: MINIMUM_SAMPLE_RATIONALE,
};

const isoDay = (offsetDays: number): string =>
  new Date(Date.now() + offsetDays * 86_400_000).toISOString().slice(0, 10);

/** A 1X2 market row. Below `MINIMUM_SAMPLE` the backend withholds both figures, so this does too. */
export function measuredMarket(scored: number, hits: number): MeasuredMarketPayload {
  const enough = scored >= MINIMUM_SAMPLE;
  return {
    market: 'match_result',
    rule: MATCH_RESULT_RULE,
    scored,
    hits,
    pushes: 0,
    voids: 0,
    not_scored: 0,
    hit_rate: enough ? Math.round((hits / scored) * 10_000) / 10_000 : null,
    hit_rate_available: enough,
    hit_rate_sample: scored,
    hit_rate_unavailable_reason: enough
      ? null
      : `${scored} scored prediction(s) is below the minimum of ${MINIMUM_SAMPLE}. ${MINIMUM_SAMPLE_RATIONALE}`,
    hit_rate_definition: HIT_RATE_DEFINITION,
    brier_score: enough ? 0.5981 : null,
    brier_available: enough,
    brier_unavailable_reason: enough
      ? null
      : `${scored} prediction(s) carry a computable Brier score, below the minimum of ${MINIMUM_SAMPLE}. `
        + MINIMUM_SAMPLE_RATIONALE,
    brier_definition: BRIER_DEFINITION,
    brier_baseline: 0.6667,
    brier_sample: scored,
    mean_probability_of_actual: enough ? 0.4123 : null,
    mean_probability_of_actual_definition:
      'The probability the source itself published for the outcome that actually occurred.',
    mean_probability_of_actual_sample: scored,
  };
}

/** One scored source. `scored` below `MINIMUM_SAMPLE` still counts — it just publishes no rate. */
export function measuredSource(label: string, scored: number, hits: number): MeasuredSourcePayload {
  return {
    source_type: 'model_provider',
    source_id: label,
    source_label: label,
    eligible: scored + 3,
    scored,
    pending: 2,
    void: 1,
    not_scored: 0,
    not_scored_reasons: [],
    markets: [measuredMarket(scored, hits)],
    measured: true,
    not_measured_reason: null,
  };
}

function performanceEnvelope(sources: MeasuredSourcePayload[], notMeasuredReason: string | null): PerformancePayload {
  return {
    window: { start: isoDay(-90), end: isoDay(0), basis: 'kickoff date in UTC, both ends included' },
    minimum_sample: MINIMUM_SAMPLE,
    minimum_sample_rationale: MINIMUM_SAMPLE_RATIONALE,
    rules: RULES,
    sources,
    sources_measured: sources.filter(source => source.measured).length,
    not_measured_reason: notMeasuredReason,
    measured_at: new Date().toISOString(),
  };
}

/** The state of the local installation today: nothing has reached a result, so nothing is scored. */
export function nothingMeasuredPerformance(): PerformancePayload {
  return performanceEnvelope([], 'no match in this window has reached a terminal status yet, so '
    + 'there is nothing to score');
}

/** A source with fewer scored predictions than the minimum: counts yes, headline figure no. */
export function belowMinimumPerformance(): PerformancePayload {
  return performanceEnvelope([measuredSource('gameforecast', 7, 4)], null);
}

/** A source with enough scored predictions for a published figure. */
export function measuredPerformance(): PerformancePayload {
  return performanceEnvelope([measuredSource('gameforecast', 106, 50)], null);
}

/**
 * The vendor's own refusal text, recorded verbatim.
 *
 * Read on 2026-09-19 from `GET /api/v1/data-providers/status` on the local backend, where it is
 * what stopped the forecast provider: `forecasts.cooling_down` held
 *
 *   gameforecast: rate limit or quota exceeded (HTTP 429): You have exceeded the DAILY quota for
 *   Requests on your current plan, BASIC. Upgrade your plan at
 *   https://rapidapi.com/krnelstudio/api/game-forecast-api
 *
 * Everything after the second colon is the vendor's, not ours:
 * `app/services/providers/http.py::_upstream_message` takes up to 160 characters of the provider's
 * own error body, rewrites nothing but a credential, and hands it on. It does that identically for
 * every provider in the chain, which is why the excerpt is reused below for a fixture provider —
 * what any of this is testing is what a 53-character unbreakable token does to the layout of the
 * slot that prints it, and that is a property of the slot rather than of who filled it.
 */
export const VENDOR_UPGRADE_URL = 'https://rapidapi.com/krnelstudio/api/game-forecast-api';
export const VENDOR_REFUSAL_EXCERPT =
  'You have exceeded the DAILY quota for Requests on your current plan, BASIC. '
  + `Upgrade your plan at ${VENDOR_UPGRADE_URL}`;

/**
 * The fixture provider paused after the vendor refused it, in the backend's own composed wording.
 *
 * `ProviderHttpClient.get_json` raises `f"{provider}: rate limit or quota exceeded (HTTP 429)"`
 * followed by the excerpt above, and that whole string is what lands in the chain entry — so the
 * site-wide banner prints a line ending in an unbreakable URL. That is the widest thing this
 * application can be asked to fit on a 360px screen, and the state that produced the sideways
 * scroll the header work was about.
 */
export function vendorRefusalStatus(): ProviderStatusPayload {
  const status = baseStatus();
  const refusal = `${status.chain[0].name}: rate limit or quota exceeded (HTTP 429): ${VENDOR_REFUSAL_EXCERPT}`;
  status.chain[0].cooling_down = refusal;
  status.chain[0].last_error = refusal;
  status.chain[0].last_error_at = new Date().toISOString();
  status.chain[0].last_success_at = null;
  return status;
}

/** Provider status describing an expired or rejected trial. */
export function expiredTrialStatus(): ProviderStatusPayload {
  const status = baseStatus();
  status.chain[0].cooling_down = 'This API key and secret do not have access to our data enabled';
  status.chain[0].last_error = 'This API key and secret do not have access to our data enabled';
  status.chain[0].last_error_at = new Date().toISOString();
  status.chain[0].last_success_at = null;
  return status;
}

export interface StubOptions {
  /**
   * Answer `GET /matches`. The second argument is the whole query string, so a test that cares
   * about the timezone contract can apply the backend's own rule with selectLocalDay().
   */
  day?: (isoDate: string, params: URLSearchParams) => DayPayload;
  status?: ProviderStatusPayload;
  coverage?: Json | null;
  /** Answer `GET /performance/sources`. Defaults to the honest local state: nothing scored. */
  performance?: PerformancePayload;
  matchById?: (id: string) => ApiMatch | null;
  /** Answer `GET /teams/search`; the default is an empty result set. */
  teamSearch?: (query: string) => { teams: Json[]; competitions: Json[] };
  /** Return a status code to make that route fail instead of answering. */
  fail?: (url: string) => number | null;
}

/**
 * Sign-in stubbing, registered by e2e/support/auth.ts.
 *
 * It lives here rather than in a page.route() of its own so that the order of the two setup calls
 * cannot matter: whichever handler Playwright reaches first, the /auth/* answers come from the
 * same place. Without a signed-in session the auth endpoints answer 401, which is what a signed-out
 * browser really gets — so a test that forgets to sign in lands on the login page instead of
 * quietly being handed an empty object.
 */
export type AuthHandler = (route: Route, request: Request) => Promise<void> | void;
const authHandlers = new WeakMap<Page, AuthHandler>();
export const registerAuthHandler = (page: Page, handler: AuthHandler): void => { authHandlers.set(page, handler); };
export const authHandlerFor = (page: Page): AuthHandler | undefined => authHandlers.get(page);

/**
 * Intercept every backend call. Anything not explicitly modelled answers with an empty, valid
 * shape rather than failing, so a test only ever exercises what it set out to exercise.
 */
export async function stubBackend(page: Page, options: StubOptions = {}): Promise<void> {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  await page.route('**/api/v1/**', async (route: Route, request: Request) => {
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, '');

    const failWith = options.fail?.(url.toString());
    if (failWith) {
      return json(route, { detail: 'Simulated backend failure' }, failWith);
    }

    if (path.startsWith('/auth/')) {
      const handler = authHandlerFor(page);
      if (handler) return handler(route, request);
      // Nobody signed in: answer the way the real backend answers an anonymous caller.
      return json(route, { detail: 'Not authenticated' }, 401);
    }

    if (path === '/data-providers/status') {
      return json(route, options.status ?? baseStatus());
    }
    if (path === '/data-providers/coverage') {
      return json(route, options.coverage ?? baseCoverage());
    }
    if (path === '/performance/sources') {
      return json(route, options.performance ?? nothingMeasuredPerformance());
    }
    if (path === '/performance/rules') {
      return json(route, RULES);
    }
    if (path === '/matches') {
      const date = url.searchParams.get('date') || new Date().toISOString().slice(0, 10);
      const answer = options.day ?? ((d: string) => dayPayload(d));
      return json(route, answer(date, url.searchParams));
    }
    if (path === '/matches/live') {
      return json(route, { matches: [], provider: 'livescore', source: 'provider', stale: false, errors: [] });
    }
    if (path.startsWith('/matches/')) {
      const id = path.split('/')[2];
      // The list-shaped fixture by default; `matchById: matchDetail` is how a test asks for the
      // detail payload with its brief. See matchDetail().
      const found = options.matchById?.(id) ?? baseMatches().find(m => m.id === id) ?? null;
      return found ? json(route, found) : json(route, { detail: 'Match not found' }, 404);
    }
    if (path === '/leagues') {
      return json(route, options.coverage === null ? { competitions: [] } : baseLeagues());
    }
    if (path.startsWith('/leagues/')) {
      if (path.endsWith('/standings')) return json(route, { competition: baseLeagues().competitions?.[0] ?? null, standings: [], errors: [] });
      if (path.endsWith('/matches')) return json(route, { competition: baseLeagues().competitions?.[0] ?? null, matches: baseMatches().slice(0, 4), errors: [] });
      return json(route, baseLeagues().competitions?.[0] ?? { detail: 'not found' });
    }
    if (path.startsWith('/teams/search')) {
      const query = url.searchParams.get('q') || '';
      return json(route, options.teamSearch?.(query) ?? { teams: [], competitions: [] });
    }
    if (path.startsWith('/teams/')) {
      return json(route, { team: null, upcoming: [], recent: [] });
    }
    if (path.startsWith('/predictions')) {
      return json(route, { predictions: [], total: 0, page: 1, limit: 20 });
    }
    return json(route, {});
  });
}

/** Collect console errors and failed requests so a test can assert the page stayed clean. */
export function watchForProblems(page: Page) {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('requestfailed', request => {
    failedRequests.push(`${request.method()} ${request.url()} — ${request.failure()?.errorText}`);
  });
  page.on('response', response => {
    if (response.status() >= 500) failedRequests.push(`${response.status()} ${response.url()}`);
  });
  return { consoleErrors, failedRequests };
}

export const localDay = (offset = 0): string => {
  const now = new Date();
  now.setDate(now.getDate() + offset);
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
};
