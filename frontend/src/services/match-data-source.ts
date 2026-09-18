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

export interface DataSourceMeta {
  /** Upstream provider that produced the data (livescore, api_football, thesportsdb, sample, ...) */
  provider: string | null;
  /** provider = fresh call, cache = shared cache, stale-cache = provider failed and an older copy is shown,
   *  database = nothing fresh was fetched, browser = legacy direct browser call */
  source: 'provider' | 'cache' | 'stale-cache' | 'database' | 'browser';
  stale: boolean;
  fetchedAt: string | null;
  errors: string[];
}

export interface MatchListResult {
  matches: Match[];
  meta: DataSourceMeta;
}

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
  remaining_today: number | null;
  enforced: boolean;
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
  getFixturesByDate(date: string): Promise<Match[]>;
  getFixturesByDateWithMeta(date: string): Promise<MatchListResult>;
  getTodayFixtures(): Promise<Match[]>;
  getTomorrowFixtures(): Promise<Match[]>;
  getMatch(matchId: string): Promise<Match | null>;
  getTeam(teamId: string): Promise<TeamPage | null>;
  search(query: string): Promise<SearchResults>;
  getProviderStatus(): Promise<ProviderStatus | null>;
  clearCache(): void;
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

/** @deprecated use localDateString; kept for the legacy API-Football path */
export function utcDateString(offsetDays = 0): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().split('T')[0];
}
