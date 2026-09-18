/**
 * Backend match-data source (default).
 *
 * Talks to the FastAPI endpoints added in Phase 1:
 *   GET /api/v1/matches?date=YYYY-MM-DD   GET /api/v1/matches/live   GET /api/v1/matches/{id}
 *   GET /api/v1/leagues                    GET /api/v1/leagues/{id}/standings   GET /api/v1/leagues/{id}/matches
 *   GET /api/v1/teams/search?q=            GET /api/v1/teams/{id}
 *   GET /api/v1/data-providers/status
 * The backend owns provider credentials (Live Score API, GameForecastAPI, retained API-Football/TheSportsDB)
 * and the shared cache; this module only maps the stable backend JSON to the UI types.
 */

import apiClient from './api-client';
import { ConfidenceLevel, HeadToHead, League, LeagueStanding, Match, MatchPredictions, MatchStatus, Team } from '@/types';
import {
  DataSourceMeta, MatchDataSource, MatchListResult, ProviderStatus, SearchResults, TeamPage, utcDateString,
} from './match-data-source';

const API = '/api/v1';
const CACHE_TTL_MS = 60 * 1000; // the backend already caches per provider; this only de-duplicates page renders

// ----------------------------------------------------------------------------- backend payloads
export interface ApiTeam {
  id: string;
  name: string;
  short_name: string | null;
  logo: string;
  country: string | null;
}

export interface ApiLeague {
  id: string;
  key: string | null;
  name: string;
  country: string | null;
  country_code: string | null;
  logo: string;
  is_cup: boolean;
  providers: Record<string, string>;
}

export interface ApiExpertPrediction {
  id: string;
  source: string;
  priority_level: number;
  status: string;
  home_win_prob: number | null;
  draw_prob: number | null;
  away_win_prob: number | null;
  confidence_score: number | null;
  btts_yes_prob: number | null;
  btts_no_prob: number | null;
  btts_confidence: number | null;
  total_goals_over_25_prob: number | null;
  total_goals_under_25_prob: number | null;
  total_goals_over_35_prob: number | null;
  total_goals_under_35_prob: number | null;
  total_goals_confidence: number | null;
  reasoning: string | null;
  published_at: string | null;
  created_by: string;
}

export interface ApiForecast {
  provider: string;
  external_event_id: string;
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
  recommended_bets: Record<string, unknown> | null;
  reasoning: string | null;
  confidence: number | null;
  match_confidence: string | null;
  matched_by: string | null;
  model_run_at: string | null;
  provider_updated_at: string | null;
  fetched_at: string | null;
  state: 'available' | 'stale' | 'kickoff_passed' | 'unavailable';
  state_reason: string | null;
  markets_available: { match_result: boolean; btts: boolean; over_under_25: boolean; over_under_35: boolean };
}

export interface ApiMatch {
  id: string;
  provider: string | null;
  external_id: string | null;
  competition: ApiLeague | null;
  home: ApiTeam | null;
  away: ApiTeam | null;
  kickoff_utc: string | null;
  status: MatchStatus;
  minute: string | null;
  score: { home: number; away: number; ht_home: number | null; ht_away: number | null } | null;
  venue: string | null;
  round: string | null;
  season: string | null;
  expert_prediction: ApiExpertPrediction | null;
  expert_predictions?: ApiExpertPrediction[];
  forecast: ApiForecast | null;
  forecast_state: 'available' | 'stale' | 'kickoff_passed' | 'unavailable';
  last_synced_at: string | null;
  provider_refs?: { provider: string; external_id: string; confidence: string | null; matched_by: string | null }[];
}

export interface ApiMatchList {
  date: string | null;
  provider: string | null;
  source: 'provider' | 'cache' | 'stale-cache' | 'database';
  stale: boolean;
  fetched_at: string | null;
  errors: string[];
  forecast_sync: Record<string, unknown> | null;
  matches: ApiMatch[];
}

export interface ApiStanding {
  position: number;
  team: { id: string | null; external_id: string; name: string; logo: string };
  played: number; won: number; drawn: number; lost: number;
  goals_for: number; goals_against: number; goal_difference: number; points: number;
  form: string[];
}

// ----------------------------------------------------------------------------- mapping helpers
const emptyStats = () => ({
  matchesPlayed: 0, wins: 0, draws: 0, losses: 0, goalsFor: 0, goalsAgainst: 0, goalDifference: 0, points: 0,
  form: [] as string[], homeRecord: { played: 0, wins: 0, draws: 0, losses: 0 }, awayRecord: { played: 0, wins: 0, draws: 0, losses: 0 },
});

const emptyHeadToHead = (): HeadToHead => ({
  totalMatches: 0, homeTeamWins: 0, draws: 0, awayTeamWins: 0, lastMatches: [], averageGoals: { home: 0, away: 0, total: 0 },
});

export function mapApiTeam(team: ApiTeam | null, fallbackName = 'Unknown'): Team {
  const name = team?.name || fallbackName;
  return {
    id: team?.id || '',
    name,
    shortName: team?.short_name || name.substring(0, 3).toUpperCase(),
    logo: team?.logo || '/teams/default.svg',
    country: team?.country || '',
    league: '',
    founded: 0,
    venue: '',
    colors: { primary: '#000000', secondary: '#FFFFFF' },
    stats: emptyStats(),
  };
}

export function mapApiLeague(league: ApiLeague | null): League {
  const name = league?.name || 'Unknown competition';
  return {
    id: league?.id || '',
    name,
    shortName: name.split(' ').map(w => w[0]).join('').toUpperCase(),
    country: league?.country || '',
    logo: league?.logo || '/leagues/default.svg',
    season: '',
    type: league?.is_cup ? 'cup' : 'domestic',
    tier: 1,
  };
}

const pct = (value: number | null | undefined): number | null =>
  value === null || value === undefined ? null : Math.round(value * 1000) / 10;

/** Display bucket derived from the strength of the source's own probabilities (not a generated number). */
function levelFromProbability(max: number | null): ConfidenceLevel {
  if (max === null) return 'low';
  if (max > 60) return 'very-high';
  if (max > 50) return 'high';
  if (max > 40) return 'medium';
  return 'low';
}

function levelFromScore(score: number | null | undefined, fallback: ConfidenceLevel): ConfidenceLevel {
  if (score === null || score === undefined) return fallback;
  if (score >= 0.8) return 'very-high';
  if (score >= 0.65) return 'high';
  if (score >= 0.5) return 'medium';
  return 'low';
}

function outcomeBlock(home: number | null, draw: number | null, away: number | null, score?: number | null) {
  const h = pct(home), d = pct(draw), a = pct(away);
  if (h === null || d === null || a === null) return null;
  const level = levelFromProbability(Math.max(h, d, a));
  return { homeWin: h, draw: d, awayWin: a, confidence: score === undefined ? level : levelFromScore(score, level) };
}

function bttsBlock(yes: number | null, no: number | null, score?: number | null) {
  const y = pct(yes);
  if (y === null) return null;
  const n = pct(no) ?? Math.round((100 - y) * 10) / 10;
  return { yes: y, no: n, confidence: levelFromScore(score, levelFromProbability(Math.max(y, n))) };
}

function totalsBlock(o25: number | null, u25: number | null, o35: number | null, u35: number | null, score?: number | null) {
  const over25 = pct(o25);
  if (over25 === null) return null;
  const under25 = pct(u25) ?? Math.round((100 - over25) * 10) / 10;
  return {
    over25, under25, over35: pct(o35), under35: pct(u35),
    confidence: levelFromScore(score, levelFromProbability(Math.max(over25, under25))),
  };
}

export function mapExpertPrediction(expert: ApiExpertPrediction): MatchPredictions | null {
  const outcome = outcomeBlock(expert.home_win_prob, expert.draw_prob, expert.away_win_prob, expert.confidence_score);
  if (!outcome) return null;
  const btts = bttsBlock(expert.btts_yes_prob, expert.btts_no_prob, expert.btts_confidence);
  const totals = totalsBlock(expert.total_goals_over_25_prob, expert.total_goals_under_25_prob,
    expert.total_goals_over_35_prob, expert.total_goals_under_35_prob, expert.total_goals_confidence);
  return {
    outcome,
    bothTeamsToScore: btts,
    totalGoals: totals,
    correctScore: null,
    analysis: expert.reasoning || 'Expert prediction (no written analysis).',
    keyFactors: [],
    source: 'expert',
    source_type: expert.source,
    confidence_score: expert.confidence_score,
    priority_level: expert.priority_level,
    state: 'available',
    markets: { matchResult: true, btts: btts !== null, overUnder25: totals !== null, overUnder35: totals?.over35 !== null && totals?.over35 !== undefined },
    publishedAt: expert.published_at,
  };
}

export function mapForecast(forecast: ApiForecast | null, fallbackState: ApiMatch['forecast_state']): MatchPredictions | null {
  if (!forecast) return null;
  const outcome = outcomeBlock(forecast.home_win_prob, forecast.draw_prob, forecast.away_win_prob);
  const btts = bttsBlock(forecast.btts_yes_prob, forecast.btts_no_prob);
  const totals = totalsBlock(forecast.total_goals_over_25_prob, forecast.total_goals_under_25_prob,
    forecast.total_goals_over_35_prob, forecast.total_goals_under_35_prob);
  let correctScore: MatchPredictions['correctScore'] = null;
  if (forecast.exact_score && Object.keys(forecast.exact_score).length > 0) {
    const [score, prob] = Object.entries(forecast.exact_score).sort((a, b) => b[1] - a[1])[0];
    correctScore = { mostLikely: score, probability: pct(prob) ?? 0, confidence: levelFromProbability(pct(prob)) };
  }
  if (!outcome && !btts && !totals && !correctScore) return null;
  return {
    outcome: outcome || { homeWin: 0, draw: 0, awayWin: 0, confidence: 'low' },
    bothTeamsToScore: btts,
    totalGoals: totals,
    correctScore,
    analysis: forecast.reasoning || 'Model forecast (no written reasoning supplied by the provider).',
    keyFactors: [],
    source: 'provider',
    source_type: forecast.provider,
    providerName: forecast.provider,
    confidence_score: forecast.confidence,
    state: forecast.state || fallbackState,
    stateReason: forecast.state_reason,
    markets: {
      matchResult: forecast.markets_available?.match_result ?? outcome !== null,
      btts: forecast.markets_available?.btts ?? btts !== null,
      overUnder25: forecast.markets_available?.over_under_25 ?? totals !== null,
      overUnder35: forecast.markets_available?.over_under_35 ?? (totals?.over35 !== null && totals?.over35 !== undefined),
    },
    generatedAt: forecast.model_run_at || forecast.provider_updated_at || forecast.fetched_at,
    recommendedBets: forecast.recommended_bets,
    matchConfidence: forecast.match_confidence,
  };
}

function localTime(iso: string | null): string {
  if (!iso) return '--:--';
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function mapApiMatch(match: ApiMatch): Match {
  const expert = match.expert_prediction ? mapExpertPrediction(match.expert_prediction) : null;
  const forecast = mapForecast(match.forecast, match.forecast_state);
  const forecastIsCurrent = forecast !== null && forecast.state === 'available';
  const homeTeam = mapApiTeam(match.home, 'Home');
  const awayTeam = mapApiTeam(match.away, 'Away');
  homeTeam.venue = match.venue || '';
  return {
    id: match.id,
    homeTeam,
    awayTeam,
    league: mapApiLeague(match.competition),
    date: match.kickoff_utc ? match.kickoff_utc.split('T')[0] : utcDateString(),
    time: localTime(match.kickoff_utc),
    kickoffUtc: match.kickoff_utc || undefined,
    status: match.status || 'scheduled',
    venue: match.venue || 'Venue to be confirmed',
    round: match.round || '',
    season: match.season || '',
    odds: null, // no bookmaker odds feed in Phase 1: shown as unavailable
    predictions: expert || (forecastIsCurrent ? forecast : null),
    expertPrediction: expert,
    expertPredictions: (match.expert_predictions || []).map(mapExpertPrediction).filter((p): p is MatchPredictions => p !== null),
    providerForecast: forecast,
    headToHead: emptyHeadToHead(),
    result: match.score ? {
      homeScore: match.score.home,
      awayScore: match.score.away,
      halfTimeScore: { home: match.score.ht_home ?? 0, away: match.score.ht_away ?? 0 },
      fullTimeScore: { home: match.score.home, away: match.score.away },
    } : undefined,
    provider: match.provider,
    externalId: match.external_id,
    minute: match.minute,
    lastSyncedAt: match.last_synced_at,
  };
}

export function mapApiStanding(row: ApiStanding): LeagueStanding {
  return {
    position: row.position,
    team: mapApiTeam({ id: row.team.id || row.team.external_id, name: row.team.name, short_name: null, logo: row.team.logo, country: null }),
    matchesPlayed: row.played,
    wins: row.won,
    draws: row.drawn,
    losses: row.lost,
    goalsFor: row.goals_for,
    goalsAgainst: row.goals_against,
    goalDifference: row.goal_difference,
    points: row.points,
    form: row.form || [],
  };
}

function metaOf(list: ApiMatchList): DataSourceMeta {
  return { provider: list.provider, source: list.source, stale: list.stale, fetchedAt: list.fetched_at, errors: list.errors || [] };
}

export function describeError(error: unknown): string {
  const err = error as { response?: { status?: number; data?: { detail?: unknown } }; message?: string };
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const d = detail as { message?: string; errors?: string[] };
    return [d.message, ...(d.errors || [])].filter(Boolean).join(' — ');
  }
  if (err?.response?.status === 503) return 'Match data is temporarily unavailable.';
  return err?.message || 'Request failed';
}

// ----------------------------------------------------------------------------- service
type CacheEntry<T> = { value: T; timestamp: number };

class BackendMatchDataService implements MatchDataSource {
  readonly name = 'backend' as const;
  private cache = new Map<string, CacheEntry<unknown>>();

  private async cached<T>(key: string, loader: () => Promise<T>): Promise<T> {
    const hit = this.cache.get(key) as CacheEntry<T> | undefined;
    if (hit && Date.now() - hit.timestamp < CACHE_TTL_MS) return hit.value;
    const value = await loader();
    this.cache.set(key, { value, timestamp: Date.now() });
    return value;
  }

  async getTopLeagues(): Promise<League[]> {
    return this.cached('leagues', async () => {
      const { data } = await apiClient.get<{ provider: string | null; competitions: ApiLeague[] }>(`${API}/leagues`);
      return data.competitions.map(mapApiLeague);
    });
  }

  async getLeague(leagueId: string): Promise<League | null> {
    const fromList = (await this.getTopLeagues()).find(l => l.id === leagueId);
    if (fromList) return fromList;
    try {
      const { data } = await apiClient.get<ApiLeague>(`${API}/leagues/${encodeURIComponent(leagueId)}`);
      return mapApiLeague(data);
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404) return null;
      throw error;
    }
  }

  async getStandings(leagueId: string): Promise<LeagueStanding[]> {
    return this.cached(`standings-${leagueId}`, async () => {
      const { data } = await apiClient.get<{ standings: ApiStanding[] }>(`${API}/leagues/${encodeURIComponent(leagueId)}/standings`);
      return data.standings.map(mapApiStanding);
    });
  }

  /** Teams of a competition: standings first, then the clubs appearing in the calendar. */
  async getTeamsByLeague(leagueId: string): Promise<Team[]> {
    const standings = await this.getStandings(leagueId).catch(() => [] as LeagueStanding[]);
    const teams = new Map<string, Team>();
    standings.forEach(row => { if (row.team.id) teams.set(row.team.id, row.team); });
    if (teams.size === 0) {
      const matches = await this.getFixturesByLeague(leagueId);
      matches.forEach(m => { teams.set(m.homeTeam.id, m.homeTeam); teams.set(m.awayTeam.id, m.awayTeam); });
    }
    return Array.from(teams.values()).sort((a, b) => a.name.localeCompare(b.name));
  }

  async getFixturesByLeague(leagueId: string): Promise<Match[]> {
    return this.cached(`league-matches-${leagueId}`, async () => {
      const { data } = await apiClient.get<{ matches: ApiMatch[] }>(`${API}/leagues/${encodeURIComponent(leagueId)}/matches`, {
        params: { days_ahead: 14, days_back: 7 },
      });
      return data.matches.map(mapApiMatch);
    });
  }

  async getFixturesByDateWithMeta(date: string): Promise<MatchListResult> {
    return this.cached(`matches-${date}`, async () => {
      const { data } = await apiClient.get<ApiMatchList>(`${API}/matches`, { params: { date } });
      return { matches: data.matches.map(mapApiMatch), meta: metaOf(data) };
    });
  }

  async getFixturesByDate(date: string): Promise<Match[]> {
    return (await this.getFixturesByDateWithMeta(date)).matches;
  }

  getTodayFixtures(): Promise<Match[]> {
    return this.getFixturesByDate(utcDateString(0));
  }

  getTomorrowFixtures(): Promise<Match[]> {
    return this.getFixturesByDate(utcDateString(1));
  }

  async getLiveMatches(): Promise<MatchListResult> {
    const { data } = await apiClient.get<ApiMatchList>(`${API}/matches/live`);
    return { matches: data.matches.map(mapApiMatch), meta: metaOf(data) };
  }

  async getMatch(matchId: string): Promise<Match | null> {
    try {
      const { data } = await apiClient.get<ApiMatch>(`${API}/matches/${encodeURIComponent(matchId)}`);
      return mapApiMatch(data);
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404) return null;
      throw error;
    }
  }

  async getTeam(teamId: string): Promise<TeamPage | null> {
    try {
      const { data } = await apiClient.get<{ team: ApiTeam; upcoming: ApiMatch[]; recent: ApiMatch[] }>(`${API}/teams/${encodeURIComponent(teamId)}`);
      return { team: mapApiTeam(data.team), upcoming: data.upcoming.map(mapApiMatch), recent: data.recent.map(mapApiMatch) };
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404) return null;
      throw error;
    }
  }

  async search(query: string): Promise<SearchResults> {
    if (!query || query.trim().length < 2) return { teams: [], leagues: [] };
    const { data } = await apiClient.get<{ teams: ApiTeam[]; competitions: ApiLeague[] }>(`${API}/teams/search`, { params: { q: query.trim() } });
    return {
      teams: data.teams.map(t => ({ id: t.id, name: t.name, logo: t.logo, country: t.country || '' })),
      leagues: data.competitions.map(l => ({ id: l.id, name: l.name, logo: l.logo, country: l.country || '', type: l.is_cup ? 'Cup' : 'League' })),
    };
  }

  async getProviderStatus(): Promise<ProviderStatus | null> {
    try {
      const { data } = await apiClient.get<ProviderStatus>(`${API}/data-providers/status`);
      return data;
    } catch (error) {
      console.warn('Provider status unavailable:', describeError(error));
      return null;
    }
  }

  clearCache(): void {
    this.cache.clear();
  }
}

export const backendMatchDataService = new BackendMatchDataService();
export default backendMatchDataService;
