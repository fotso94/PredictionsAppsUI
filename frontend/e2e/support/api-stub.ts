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

export interface ApiMatch extends Json {
  id: string;
  kickoff_utc: string;
  status: string;
  forecast: ApiForecast | null;
  forecast_state?: string;
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

export interface ProviderStatusPayload extends Json {
  chain: ProviderChainEntryPayload[];
  forecasts: {
    budget: ProviderBudgetPayload | null;
    cooling_down: string | null;
  } & Json;
}

export interface LeaguesPayload extends Json {
  competitions?: Json[];
}

export const baseMatches = (): ApiMatch[] => JSON.parse(JSON.stringify(matchesDay.matches)) as ApiMatch[];
export const baseDayPayload = (): DayPayload => JSON.parse(JSON.stringify(matchesDay)) as DayPayload;
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
  }
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
  day?: (isoDate: string) => DayPayload;
  status?: ProviderStatusPayload;
  coverage?: Json | null;
  matchById?: (id: string) => ApiMatch | null;
  /** Return a status code to make that route fail instead of answering. */
  fail?: (url: string) => number | null;
}

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

    if (path === '/data-providers/status') {
      return json(route, options.status ?? baseStatus());
    }
    if (path === '/data-providers/coverage') {
      return json(route, options.coverage ?? baseCoverage());
    }
    if (path === '/matches') {
      const date = url.searchParams.get('date') || new Date().toISOString().slice(0, 10);
      return json(route, (options.day ?? ((d: string) => dayPayload(d)))(date));
    }
    if (path === '/matches/live') {
      return json(route, { matches: [], provider: 'livescore', source: 'provider', stale: false, errors: [] });
    }
    if (path.startsWith('/matches/')) {
      const id = path.split('/')[2];
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
      return json(route, { teams: [], competitions: [] });
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
