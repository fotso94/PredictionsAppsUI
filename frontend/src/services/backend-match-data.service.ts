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
import {
  ConfidenceLevel, ExpertPredictionRevision, ForecastAnomaly, HeadToHead, League, LeagueStanding,
  Match, MatchBrief, MatchBriefCompact, MatchPredictions, MatchStatus, Team,
} from '@/types';
import {
  CoverageSummary, DataSourceMeta, ForecastSyncStatus, MatchDataSource, MatchListResult, MatchReadOptions,
  ProviderStatus, SearchResults, TeamPage,
  localDateString, localDayOffsets, timezoneOffsetMinutes,
} from './match-data-source';
import { getErrorMessage, getErrorStatus } from '@/utils/errors';
// Kick-off times are mapped in the reader's chosen zone, and the cache is dropped when that zone
// changes — see `localTime` below and the `onZoneChange` registration at the foot of this file.
import { formatTime, onZoneChange } from '@/i18n';

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
  exact_score: Record<string, number | null> | null;
  /** Provider remainder for every scoreline it did not list; never a scoreline itself */
  exact_score_other_prob: number | null;
  recommended_bets: Record<string, unknown> | null;
  reasoning: string | null;
  confidence: number | null;
  match_confidence: string | null;
  matched_by: string | null;
  /** When the provider's model ran; null when the provider did not say */
  model_run_at: string | null;
  /** When the provider last touched the event */
  provider_updated_at: string | null;
  /** When this installation retrieved it */
  fetched_at: string | null;
  /** False when model_run_at is null: the generation time is genuinely unknown */
  generated_at_known: boolean;
  /** Consistency problems in the provider payload, reported not corrected */
  anomalies: ForecastAnomaly[] | null;
  state: 'available' | 'stale' | 'kickoff_passed' | 'unavailable';
  state_reason: string | null;
  markets_available: { match_result: boolean; btts: boolean; over_under_25: boolean; over_under_35: boolean; exact_score: boolean };
}

/**
 * The compact brief the backend attaches to every fixture in a list payload, and the full brief
 * the detail endpoint adds. Typed in src/types/brief.ts; carried here verbatim so nothing is lost
 * between the wire and the UI. Optional because a payload from before the brief landed (or from
 * the legacy API-Football source) simply does not have one.
 */
export type ApiMatchBriefCompact = MatchBriefCompact;
export type ApiMatchBrief = MatchBrief;

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
  /** Present on every fixture in a list payload; absent on payloads from before the brief landed. */
  brief_compact?: ApiMatchBriefCompact | null;
  /** Only the match-detail endpoint supplies the full brief. */
  brief?: ApiMatchBrief | null;
  /** Only the match-detail endpoint supplies the preserved earlier versions. */
  expert_prediction_revisions?: ExpertPredictionRevision[];
  provider_refs?: { provider: string; external_id: string; confidence: string | null; matched_by: string | null }[];
}

export interface ApiMatchList {
  date: string | null;
  provider: string | null;
  source: 'provider' | 'cache' | 'stale-cache' | 'database';
  stale: boolean;
  fetched_at: string | null;
  errors: string[];
  /** Report from ForecastService.ensure_synced(): { provider, competitions, skipped, retried, deferred, error?, synced_at } */
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

/** Provider probabilities are 0-1 floats; the UI shows percent with one decimal. Null stays null. */
function pct(value: number): number;
function pct(value: number | null | undefined): number | null;
function pct(value: number | null | undefined): number | null {
  return value === null || value === undefined ? null : Math.round(value * 1000) / 10;
}

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

/** Strongest published number among the ones the source actually supplied; null when it supplied none. */
function strongest(...values: (number | null)[]): number | null {
  const published = values.filter((v): v is number => v !== null);
  return published.length > 0 ? Math.max(...published) : null;
}

/**
 * BTTS exactly as published. A half the source omitted stays null: "no" is NOT 100 - "yes".
 * The two are complementary in theory, but deriving one from the other publishes a number the
 * model never produced (and hides the provider's own rounding or inconsistency).
 */
function bttsBlock(yes: number | null, no: number | null, score?: number | null) {
  const y = pct(yes);
  const n = pct(no);
  if (y === null && n === null) return null;
  return { yes: y, no: n, confidence: levelFromScore(score, levelFromProbability(strongest(y, n))) };
}

/** Total-goals lines exactly as published; every line the source omitted stays null. */
function totalsBlock(o25: number | null, u25: number | null, o35: number | null, u35: number | null, score?: number | null) {
  const over25 = pct(o25);
  const under25 = pct(u25);
  const over35 = pct(o35);
  const under35 = pct(u35);
  if (over25 === null && under25 === null && over35 === null && under35 === null) return null;
  return {
    over25, under25, over35, under35,
    confidence: levelFromScore(score, levelFromProbability(strongest(over25, under25))),
  };
}

/**
 * Most likely scoreline from the provider's exact-score map.
 *
 * Only entries that are actually a scoreline ("2-1") carrying a published probability in (0, 1]
 * survive: anything else (a null value, a stray key such as "other", a percentage-scaled number)
 * would otherwise be rendered as a scoreline at 0%.
 */
function correctScoreBlock(exact: Record<string, number | null> | null | undefined): MatchPredictions['correctScore'] {
  if (!exact) return null;
  const usable = Object.entries(exact).filter(
    (entry): entry is [string, number] =>
      /^\d+-\d+$/.test(entry[0]) && typeof entry[1] === 'number' && Number.isFinite(entry[1]) && entry[1] > 0 && entry[1] <= 1,
  );
  if (usable.length === 0) return null;
  const [score, prob] = usable.sort((a, b) => b[1] - a[1])[0];
  const probability = pct(prob);
  return { mostLikely: score, probability, confidence: levelFromProbability(probability) };
}

/**
 * An expert prediction, market by market.
 *
 * Each block is built independently: an expert who published only BTTS and totals still reaches the
 * UI with those markets and a null 1X2, instead of the whole prediction being discarded.
 */
export function mapExpertPrediction(expert: ApiExpertPrediction): MatchPredictions | null {
  const outcome = outcomeBlock(expert.home_win_prob, expert.draw_prob, expert.away_win_prob, expert.confidence_score);
  const btts = bttsBlock(expert.btts_yes_prob, expert.btts_no_prob, expert.btts_confidence);
  const totals = totalsBlock(expert.total_goals_over_25_prob, expert.total_goals_under_25_prob,
    expert.total_goals_over_35_prob, expert.total_goals_under_35_prob, expert.total_goals_confidence);
  if (!outcome && !btts && !totals) return null; // nothing was published at all
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
    markets: {
      matchResult: outcome !== null,
      btts: btts !== null,
      overUnder25: totals !== null && (totals.over25 !== null || totals.under25 !== null),
      overUnder35: totals !== null && (totals.over35 !== null || totals.under35 !== null),
      exactScore: false, // experts do not publish a scoreline distribution
    },
    publishedAt: expert.published_at,
  };
}

export function mapForecast(forecast: ApiForecast | null, fallbackState: ApiMatch['forecast_state']): MatchPredictions | null {
  if (!forecast) return null;
  const outcome = outcomeBlock(forecast.home_win_prob, forecast.draw_prob, forecast.away_win_prob);
  const btts = bttsBlock(forecast.btts_yes_prob, forecast.btts_no_prob);
  const totals = totalsBlock(forecast.total_goals_over_25_prob, forecast.total_goals_under_25_prob,
    forecast.total_goals_over_35_prob, forecast.total_goals_under_35_prob);
  const correctScore = correctScoreBlock(forecast.exact_score);
  if (!outcome && !btts && !totals && !correctScore) return null;
  return {
    // null when the provider published no 1X2 market for this event. The other markets still
    // reach the UI; a zero-filled 1X2 block would claim a 0% home win the model never produced.
    outcome,
    bothTeamsToScore: btts,
    totalGoals: totals,
    correctScore,
    exactScoreOther: pct(forecast.exact_score_other_prob),
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
      overUnder25: forecast.markets_available?.over_under_25 ?? (totals !== null && (totals.over25 !== null || totals.under25 !== null)),
      overUnder35: forecast.markets_available?.over_under_35 ?? (totals !== null && (totals.over35 !== null || totals.under35 !== null)),
      exactScore: forecast.markets_available?.exact_score ?? correctScore !== null,
    },
    // Kept apart on purpose: only model_run_at is the generation time. When the provider did not
    // publish one, generationTimeKnown is false and the UI must not pass off a fetch time for it.
    modelRunAt: forecast.model_run_at,
    providerUpdatedAt: forecast.provider_updated_at,
    fetchedAt: forecast.fetched_at,
    generationTimeKnown: forecast.generated_at_known ?? forecast.model_run_at !== null,
    anomalies: forecast.anomalies || [],
    recommendedBets: forecast.recommended_bets,
    matchConfidence: forecast.match_confidence,
  };
}

/**
 * The kick-off as a clock reading, in the READER'S CHOSEN zone rather than the device's.
 *
 * This runs once per fixture at mapping time and the result is cached, so it is not on its own
 * enough: a reader who changes zone with a day already loaded would keep the old times. Two
 * things cover that. The cache is dropped when the zone changes (see the `onZoneChange` hook at
 * the foot of this file), and the row itself re-formats `kickoffUtc` on every render rather than
 * printing this string (see `FixtureRow`). This value stays correct for the same reason it always
 * had to be: it is the sort key's tie-break and the fallback when the payload carries no instant.
 */
function localTime(iso: string | null): string {
  if (!iso) return '--:--';
  return formatTime(iso) ?? '--:--';
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
    date: match.kickoff_utc ? localDateString(0, new Date(match.kickoff_utc)) : localDateString(),
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
    // Carried through untouched. The brief is already the finished statement — reason codes,
    // wording, rounded percentages and all — so re-deriving any of it here would be a second
    // version of the same fact, free to drift from the one the backend stands behind.
    // `undefined` (payload has no brief) is deliberately NOT turned into null or an empty brief:
    // "this payload does not carry a brief" is not "this match has nothing to say".
    briefCompact: match.brief_compact,
    brief: match.brief,
    expertPredictionRevisions: match.expert_prediction_revisions,
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

const stringsOf = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];

/**
 * Read the backend's forecast-refresh report.
 *
 * The backend reports a paused refresh two ways: a top-level `error` (no provider configured, a
 * cooldown after a failure, or the daily allowance already spent) and/or a non-empty `deferred`
 * list when it stopped part-way. Either means "not refreshed right now" — which the UI must be
 * able to distinguish from "this fixture has no forecast".
 */
export function parseForecastSync(raw: Record<string, unknown> | null | undefined): ForecastSyncStatus | null {
  if (!raw || typeof raw !== 'object') return null;
  const provider = typeof raw.provider === 'string' ? raw.provider : null;
  const topLevelError = typeof raw.error === 'string' && raw.error.trim() ? raw.error : null;
  const competitions = (raw.competitions && typeof raw.competitions === 'object' ? raw.competitions : {}) as Record<string, unknown>;
  const competitionError = Object.values(competitions)
    .map(entry => (entry && typeof entry === 'object' ? (entry as { error?: unknown }).error : null))
    .find((message): message is string => typeof message === 'string' && message.trim().length > 0) ?? null;
  const deferred = stringsOf(raw.deferred);
  const reason = topLevelError ?? competitionError;
  return {
    provider,
    paused: reason !== null || deferred.length > 0,
    reason,
    deferred,
    syncedAt: typeof raw.synced_at === 'string' ? raw.synced_at : null,
  };
}

function metaOf(list: ApiMatchList): DataSourceMeta {
  return {
    provider: list.provider,
    source: list.source,
    stale: list.stale,
    fetchedAt: list.fetched_at,
    errors: list.errors || [],
    forecastSync: parseForecastSync(list.forecast_sync),
  };
}

/** The backend's own wording where it gave one, with a match-data specific default for a bare 503. */
export function describeError(error: unknown): string {
  const message = getErrorMessage(error, '');
  if (message && message !== 'The service is temporarily unavailable.') return message;
  return getErrorStatus(error) === 503 ? 'Match data is temporarily unavailable.' : (message || 'Request failed');
}

// ----------------------------------------------------------------------------- service
type CacheEntry<T> = { value: T; timestamp: number };

/** Cache-key prefixes, so writes can invalidate exactly what they changed. */
export const CACHE_KEYS = {
  leagues: 'leagues',
  standings: 'standings-',
  /** fixtures for a date: the lists that carry expert predictions and forecasts */
  matchesByDate: 'matches-',
  /** fixtures of one competition: also carries expert predictions */
  matchesByLeague: 'league-matches-',
} as const;

/** Every cached response whose content can change when an expert publishes, edits or removes one. */
export const PREDICTION_CACHE_PREFIXES = [CACHE_KEYS.matchesByDate, CACHE_KEYS.matchesByLeague];

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
    return this.cached(CACHE_KEYS.leagues, async () => {
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
    return this.cached(`${CACHE_KEYS.standings}${leagueId}`, async () => {
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
    return this.cached(`${CACHE_KEYS.matchesByLeague}${leagueId}`, async () => {
      const { data } = await apiClient.get<{ matches: ApiMatch[] }>(`${API}/leagues/${encodeURIComponent(leagueId)}/matches`, {
        params: { days_ahead: 14, days_back: 7, tz_offset: timezoneOffsetMinutes() },
      });
      return data.matches.map(mapApiMatch);
    });
  }

  /**
   * Fixtures for one calendar day.
   *
   * Pass `STORED_ONLY` (or `{ refresh: false }`) for a stored-data-only read: the backend answers
   * from rows it already holds, makes no provider request and spends no request allowance. A
   * stored-only response is cached under its own key, so it can never be served to a caller that
   * did ask for a refresh, nor a refreshed response reused to make a stored-only read look free.
   */
  async getFixturesByDateWithMeta(date: string, options?: MatchReadOptions): Promise<MatchListResult> {
    const refresh = options?.refresh;
    const key = `${CACHE_KEYS.matchesByDate}${date}${refresh === undefined ? '' : `:refresh=${refresh}`}`;
    return this.cached(key, async () => {
      // The viewer's calendar day, not the UTC one: a 21:00 kickoff in New York is 01:00 the next
      // day in UTC, and bucketing it by the UTC day would hide tonight's match from Today. Both
      // boundaries are sent because a daylight-saving day is 23 or 25 hours, not 24.
      const offsets = localDayOffsets(date);
      const { data } = await apiClient.get<ApiMatchList>(`${API}/matches`, {
        // `refresh` is omitted entirely when the caller did not ask, so the backend's own default
        // stays in charge and no existing caller's behaviour changes.
        params: { date, tz_offset: offsets.start, tz_offset_end: offsets.end, ...(refresh === undefined ? {} : { refresh }) },
      });
      return { matches: data.matches.map(mapApiMatch), meta: metaOf(data) };
    });
  }

  async getFixturesByDate(date: string, options?: MatchReadOptions): Promise<Match[]> {
    return (await this.getFixturesByDateWithMeta(date, options)).matches;
  }

  getTodayFixtures(): Promise<Match[]> {
    return this.getFixturesByDate(localDateString(0));
  }

  getTomorrowFixtures(): Promise<Match[]> {
    return this.getFixturesByDate(localDateString(1));
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

  async getCoverage(): Promise<CoverageSummary | null> {
    try {
      const { data } = await apiClient.get<CoverageSummary>(`${API}/data-providers/coverage`);
      return data;
    } catch (error) {
      console.warn('Coverage summary unavailable:', describeError(error));
      return null;
    }
  }

  clearCache(): void {
    this.cache.clear();
  }

  /**
   * Drop cached responses whose key starts with `prefix` (everything when omitted).
   *
   * Without this, a public list keeps its in-memory copy for the rest of the 60 s TTL after an
   * expert publishes, edits, unpublishes or deletes a prediction, so the change looks lost.
   */
  invalidate(prefix?: string): void {
    if (!prefix) {
      this.cache.clear();
      return;
    }
    for (const key of Array.from(this.cache.keys())) {
      if (key.startsWith(prefix)) this.cache.delete(key);
    }
  }

  /** Forget every cached list whose content depends on published expert predictions. */
  invalidatePredictionCaches(): void {
    PREDICTION_CACHE_PREFIXES.forEach(prefix => this.invalidate(prefix));
  }
}

export const backendMatchDataService = new BackendMatchDataService();

/**
 * A change of time zone invalidates every cached list.
 *
 * `mapApiMatch` writes two zone-dependent fields onto each `Match` — `time`, the clock reading,
 * and `date`, the calendar day the fixture falls on — at mapping time. A reader who moves from
 * Europe/Paris to Africa/Douala with today's list already in this cache would otherwise keep
 * Paris's calendar for as long as the TTL lasts, and a 00:30 CET kick-off would stay filed under
 * the wrong day. Dropping the cache costs one request against the backend's stored rows; it
 * spends no provider allowance, because every read on those routes is `refresh=false`.
 */
onZoneChange(() => backendMatchDataService.clearCache());

export default backendMatchDataService;
