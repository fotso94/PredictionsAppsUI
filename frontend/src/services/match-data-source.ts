/**
 * Match data source abstraction.
 *
 * Pages talk to `footballDataService` (see football-data.service.ts), which is one of two
 * implementations of this interface selected by VITE_DATA_SOURCE:
 *  - "backend"      -> backend-match-data.service.ts (FastAPI: Live Score API + GameForecastAPI, retained fallbacks)
 *  - "api-football" -> the legacy browser-side API-Football implementation in football-data.service.ts
 */

import { League, LeagueStanding, Match, Team } from '@/types';

export type DataSourceName = 'backend' | 'api-football';

/**
 * What the backend's last forecast refresh did.
 *
 * A paused refresh (daily allowance spent, or a cooldown after a provider failure) is not the same
 * thing as "this fixture has no forecast": the UI must be able to say "refresh paused until the
 * daily allowance resets" instead of a flat "unavailable".
 */
export interface ForecastSyncStatus {
  /** Forecast provider the backend tried to refresh; null when none is configured */
  provider: string | null;
  /** True when the refresh made no provider call, or stopped early and deferred competitions */
  paused: boolean;
  /** The backend's own wording for why, verbatim; null when the refresh ran normally */
  reason: string | null;
  /** Competition keys whose refresh was postponed to the next allowance reset */
  deferred: string[];
  /** When the backend last ran the refresh */
  syncedAt: string | null;
}

export interface DataSourceMeta {
  /** Upstream provider that produced the data (livescore, api_football, thesportsdb, sample, ...) */
  provider: string | null;
  /** provider = fresh call, cache = shared cache, stale-cache = provider failed and an older copy is shown,
   *  database = nothing fresh was fetched, browser = legacy direct browser call */
  source: 'provider' | 'cache' | 'stale-cache' | 'database' | 'browser';
  stale: boolean;
  fetchedAt: string | null;
  errors: string[];
  /** Report from the backend's forecast refresh; null when the endpoint did not run one */
  forecastSync: ForecastSyncStatus | null;
}

export interface MatchListResult {
  matches: Match[];
  meta: DataSourceMeta;
}

/**
 * How a match read should treat the upstream provider.
 *
 * `refresh: false` makes the backend answer from stored rows only: no provider request is made, no
 * request allowance is spent, and the response still carries everything (fixtures, forecasts,
 * expert predictions, the brief) — only possibly a little older, which the brief's own `freshness`
 * block states outright. Use it for anything that reads matches repeatedly (a date strip the user
 * pages through, a dashboard that polls) rather than burning a request per keystroke.
 *
 * Omitting the option sends no `refresh` parameter at all, leaving the backend's own default
 * (currently `true`) in charge — the behaviour every existing caller already has.
 */
export interface MatchReadOptions {
  refresh?: boolean;
}

/** Ready-made options for a stored-data-only read. Prefer this over writing `{ refresh: false }`. */
export const STORED_ONLY: MatchReadOptions = Object.freeze({ refresh: false });

export interface TeamPage {
  team: Team;
  upcoming: Match[];
  recent: Match[];
}

export interface SearchTeamResult {
  id: string;
  name: string;
  logo: string;
  country: string;
  founded?: number;
}

export interface SearchLeagueResult {
  id: string;
  name: string;
  logo: string;
  country: string;
  type: string;
}

export interface SearchResults {
  teams: SearchTeamResult[];
  leagues: SearchLeagueResult[];
}

export interface ProviderBudget {
  provider: string;
  daily_limit: number;
  used_today: number;
  /** Reservations refused because the allowance was already spent; these never reached the provider */
  refused_today?: number;
  remaining_today: number | null;
  enforced: boolean;
}

/**
 * Counts measured from the data this installation actually holds.
 * Accuracy and user counts are deliberately absent: scoring forecasts needs settled results,
 * so any figure would be invented.
 */
export interface CoverageSummary {
  competitions_covered: number;
  competition_keys: string[];
  upcoming_matches: number;
  matches_stored: number;
  model_forecasts: number;
  upcoming_matches_with_forecast: number;
  forecast_snapshots: number;
  expert_predictions_published: number;
  accuracy_available: boolean;
  accuracy_unavailable_reason: string;
  measured_at: string;
}

export interface ProviderChainEntry {
  name: string;
  integration_status: string;
  configured: boolean;
  budget: ProviderBudget | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_error?: string | null;
  /** Reason the provider is paused after a recent failure, if any */
  cooling_down?: string | null;
}

export interface ProviderStatus {
  active_provider: string;
  configured_fallbacks: string[];
  covered_competitions: string[];
  cache_available: boolean;
  chain: ProviderChainEntry[];
  forecasts: {
    active_provider: string;
    configured: boolean;
    integration_status: string | null;
    budget?: ProviderBudget | null;
    last_sync?: Record<string, unknown> | null;
    cooling_down?: string | null;
  };
  checked_at: string;
}

export interface MatchDataSource {
  readonly name: DataSourceName;
  getTopLeagues(): Promise<League[]>;
  getLeague(leagueId: string): Promise<League | null>;
  getTeamsByLeague(leagueId: string): Promise<Team[]>;
  getStandings(leagueId: string): Promise<LeagueStanding[]>;
  getFixturesByLeague(leagueId: string): Promise<Match[]>;
  getFixturesByDate(date: string, options?: MatchReadOptions): Promise<Match[]>;
  getFixturesByDateWithMeta(date: string, options?: MatchReadOptions): Promise<MatchListResult>;
  getTodayFixtures(): Promise<Match[]>;
  getTomorrowFixtures(): Promise<Match[]>;
  getMatch(matchId: string): Promise<Match | null>;
  getTeam(teamId: string): Promise<TeamPage | null>;
  search(query: string): Promise<SearchResults>;
  getProviderStatus(): Promise<ProviderStatus | null>;
  getCoverage(): Promise<CoverageSummary | null>;
  clearCache(): void;
  /**
   * Drop cached responses whose key starts with `prefix` (everything when omitted).
   * Call it after a write that changes what the public endpoints return, so the next read is fresh
   * instead of serving the in-memory copy for the rest of its TTL.
   */
  invalidate(prefix?: string): void;
}

export function configuredDataSource(): DataSourceName {
  const value = (import.meta.env.VITE_DATA_SOURCE || 'backend').toLowerCase();
  return value === 'api-football' ? 'api-football' : 'backend';
}

/** Randomized placeholder predictions are opt-in for local demos only and never part of the real-data path. */
export function fakePredictionsAllowed(): boolean {
  return String(import.meta.env.VITE_ALLOW_FAKE_PREDICTIONS || '').toLowerCase() === 'true';
}

/**
 * Calendar date (YYYY-MM-DD) in the viewer's local time zone, `offsetDays` from today.
 * "Today" and "Tomorrow" follow the user's clock; the backend interprets the date as the UTC day
 * of kick-off, which coincides with the local day for European kick-offs from the Americas/Europe.
 */
export function localDateString(offsetDays = 0, from: Date = new Date()): string {
  const d = new Date(from.getTime());
  d.setDate(d.getDate() + offsetDays);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * The viewer's UTC offsets that bound one local calendar day, for the backend's `tz_offset` and
 * `tz_offset_end` parameters. Both are minutes east of UTC.
 *
 * They are taken at local midnight and at the NEXT local midnight rather than from a single moment,
 * because a local day is not always 24 hours: on a daylight-saving transition it is 23 or 25. In
 * New York on 1 November 2026 the day runs 04:00Z to 05:00Z the next day, and a single offset with a
 * fixed 24-hour window would drop the first hour along with anything kicking off in it.
 *
 * Only the browser knows the viewer's transition rules, so the boundaries are computed here rather
 * than guessed on the server.
 */
export function localDayOffsets(isoDate?: string): { start: number; end: number } {
  const base = isoDate ? new Date(`${isoDate}T00:00:00`) : new Date();
  const midnight = Number.isNaN(base.getTime()) ? new Date() : base;
  midnight.setHours(0, 0, 0, 0);
  const nextMidnight = new Date(midnight.getTime());
  nextMidnight.setDate(nextMidnight.getDate() + 1);
  return { start: -midnight.getTimezoneOffset(), end: -nextMidnight.getTimezoneOffset() };
}

/** The offset at the start of a local day. Kept for callers that only need the one value. */
export function timezoneOffsetMinutes(isoDate?: string): number {
  return localDayOffsets(isoDate).start;
}

/** @deprecated use localDateString; kept for the legacy API-Football path */
export function utcDateString(offsetDays = 0): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().split('T')[0];
}
