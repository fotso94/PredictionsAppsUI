/**
 * Followed teams and leagues, and saved matches.
 *
 * Wraps the seven endpoints under /api/v1/me (all of them signed-in-only, all of them stored-data
 * reads that make no provider request) and keeps one optimistic store for the whole app, so the
 * star on a fixture row, the star on the match page and the personal dashboard cannot disagree
 * with each other about what is followed.
 *
 * The token comes from api-client's request interceptor, which reads it from localStorage and sets
 * `Authorization: Bearer <access token>` on every request; a 401 triggers its refresh-and-retry.
 * Nothing here handles tokens itself.
 *
 * TWO RULES THIS MODULE IS BUILT AROUND
 *
 * 1. A FAILURE IS NEVER AN EMPTY RESULT. Every read rethrows. The store keeps the last snapshot it
 *    genuinely received and reports `status: 'error'` with the server's own message, so a caller
 *    can say "we could not load your favourites" instead of "you follow nothing". This is the same
 *    mistake search.service.ts already had to have fixed once — a swallowed network error made the
 *    dropdown announce "No results found for Arsenal" for a search that had never run.
 *
 * 2. AN OPTIMISTIC WRITE ROLLS BACK HONESTLY. A toggle applies immediately, then reconciles with
 *    the authoritative list the server returns. If the write fails, the EXACT previous state is
 *    restored and the error is rethrown, so the control goes back to where it was and the caller
 *    can tell the user it did not happen. A star that stays filled after a failed save is a lie.
 */

import apiClient from './api-client';
import {
  ApiLeague, ApiMatch, ApiTeam, mapApiLeague, mapApiMatch, mapApiTeam,
} from './backend-match-data.service';
import type {
  FavouriteLimits, FavouritesSnapshot, FavouritesState, FollowResult, SavedMatch,
  SavedMatchCounts, SavedMatchesSnapshot, SaveMatchResult, UnsaveMatchResult,
} from '@/types';
import { getErrorMessage } from '@/utils/errors';

const API = '/api/v1/me';

/** Longest note the API accepts (NOTE_MAX_LENGTH in app/schemas/favourites.py). */
export const NOTE_MAX_LENGTH = 2000;

// ----------------------------------------------------------------------------- wire payloads
interface ApiSavedMatchEntry {
  match_id: string;
  note?: string | null;
  saved_at?: string | null;
  updated_at?: string | null;
  match: ApiMatch;
}

interface ApiSavedMatchWrite extends ApiSavedMatchEntry {
  created: boolean;
}

interface ApiSavedMatches {
  upcoming?: ApiSavedMatchEntry[];
  live?: ApiSavedMatchEntry[];
  finished?: ApiSavedMatchEntry[];
  counts?: Partial<SavedMatchCounts>;
}

interface ApiFavourites {
  teams?: ApiTeam[];
  leagues?: ApiLeague[];
  team_ids?: string[];
  league_ids?: string[];
  unresolved?: { teams?: string[]; leagues?: string[] };
  saved_matches?: ApiSavedMatches;
  limits?: Partial<FavouriteLimits>;
}

interface ApiFollowResponse {
  kind: string;
  id: string;
  following: boolean;
  changed: boolean;
  ids?: string[];
  limit: number;
}

interface ApiUnsaveResponse {
  match_id: string;
  removed: boolean;
}

// ----------------------------------------------------------------------------- mapping
const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];

function mapSavedEntry(entry: ApiSavedMatchEntry): SavedMatch {
  return {
    matchId: entry.match_id,
    // An absent note and an empty note are both "no note"; neither is an error.
    note: entry.note ?? null,
    savedAt: entry.saved_at ?? null,
    updatedAt: entry.updated_at ?? null,
    match: mapApiMatch(entry.match),
  };
}

function mapSavedMatches(raw: ApiSavedMatches | undefined): SavedMatchesSnapshot {
  const upcoming = (raw?.upcoming ?? []).map(mapSavedEntry);
  const live = (raw?.live ?? []).map(mapSavedEntry);
  const finished = (raw?.finished ?? []).map(mapSavedEntry);
  return {
    upcoming,
    live,
    finished,
    // The server's own counts win where it sent them: they are what it actually holds, which can
    // differ from what it could serialise (a save whose fixture row is gone is skipped from the
    // lists). Falling back to the list lengths only when it sent nothing at all.
    counts: {
      upcoming: raw?.counts?.upcoming ?? upcoming.length,
      live: raw?.counts?.live ?? live.length,
      finished: raw?.counts?.finished ?? finished.length,
      total: raw?.counts?.total ?? upcoming.length + live.length + finished.length,
    },
  };
}

function mapFavourites(raw: ApiFavourites): FavouritesSnapshot {
  return {
    teams: (raw.teams ?? []).map(team => mapApiTeam(team)),
    leagues: (raw.leagues ?? []).map(mapApiLeague),
    teamIds: strings(raw.team_ids),
    leagueIds: strings(raw.league_ids),
    unresolved: {
      teams: strings(raw.unresolved?.teams),
      leagues: strings(raw.unresolved?.leagues),
    },
    savedMatches: mapSavedMatches(raw.saved_matches),
    // Limits come from the API so a page never hard-codes "10 teams"; the fallbacks match
    // MAX_FAVOURITE_TEAMS / MAX_FAVOURITE_LEAGUES and only apply if the field is missing entirely.
    limits: { teams: raw.limits?.teams ?? 10, leagues: raw.limits?.leagues ?? 5 },
  };
}

const emptySaved = (): SavedMatchesSnapshot => ({
  upcoming: [], live: [], finished: [], counts: { upcoming: 0, live: 0, finished: 0, total: 0 },
});

// ----------------------------------------------------------------------------- raw API calls
/**
 * The bare endpoints. Every one of them REJECTS on failure — there is no "return an empty list on
 * error" path anywhere in this file, because an empty list is an answer and a failure is not.
 */
export const favouritesApi = {
  async getFavourites(): Promise<FavouritesSnapshot> {
    const { data } = await apiClient.get<ApiFavourites>(`${API}/favourites`);
    return mapFavourites(data);
  },

  async getSavedMatches(): Promise<SavedMatchesSnapshot> {
    const { data } = await apiClient.get<ApiSavedMatches>(`${API}/saved-matches`);
    return mapSavedMatches(data);
  },

  async follow(kind: 'team' | 'league', id: string, following: boolean): Promise<FollowResult> {
    const path = `${API}/favourites/${kind === 'team' ? 'teams' : 'leagues'}/${encodeURIComponent(id)}`;
    const { data } = following
      ? await apiClient.put<ApiFollowResponse>(path)
      : await apiClient.delete<ApiFollowResponse>(path);
    return {
      kind: data.kind === 'league' ? 'league' : 'team',
      id: data.id,
      following: data.following,
      changed: data.changed,
      ids: strings(data.ids),
      limit: data.limit,
    };
  },

  /**
   * Save a match, or edit the note on a save that already exists.
   *
   * Omit `note` to leave an existing note untouched; pass null or '' to clear it. The distinction
   * is the API's, and it is preserved here rather than normalised away: re-saving a match must not
   * silently wipe the note the owner wrote on it.
   */
  async saveMatch(matchId: string, note?: string | null): Promise<SaveMatchResult> {
    const body = note === undefined ? {} : { note };
    const { data } = await apiClient.put<ApiSavedMatchWrite>(
      `${API}/saved-matches/${encodeURIComponent(matchId)}`, body);
    return { ...mapSavedEntry(data), created: data.created };
  },

  async unsaveMatch(matchId: string): Promise<UnsaveMatchResult> {
    const { data } = await apiClient.delete<ApiUnsaveResponse>(
      `${API}/saved-matches/${encodeURIComponent(matchId)}`);
    return { matchId: data.match_id, removed: data.removed };
  },
};

// ----------------------------------------------------------------------------- optimistic store
const EMPTY_STATE: FavouritesState = Object.freeze({
  status: 'idle' as const,
  data: null,
  error: null,
  refreshing: false,
  pendingTeamIds: [],
  pendingLeagueIds: [],
  pendingMatchIds: [],
});

type Listener = () => void;

const without = (list: string[], id: string): string[] => list.filter(entry => entry !== id);
const withId = (list: string[], id: string): string[] => (list.includes(id) ? list : [...list, id]);

/** All three saved-match buckets as one list, for "is this saved?" without caring which bucket. */
function allSaved(saved: SavedMatchesSnapshot): SavedMatch[] {
  return [...saved.upcoming, ...saved.live, ...saved.finished];
}

function countsOf(upcoming: SavedMatch[], live: SavedMatch[], finished: SavedMatch[]): SavedMatchCounts {
  return {
    upcoming: upcoming.length,
    live: live.length,
    finished: finished.length,
    total: upcoming.length + live.length + finished.length,
  };
}

/**
 * Which bucket a fixture belongs in, by the same rule the API uses: `live` is in play now,
 * `finished` has been played, and EVERYTHING ELSE is `upcoming` — a postponed or cancelled fixture
 * stays in `upcoming` carrying its real status rather than being reported as finished.
 */
function bucketOf(entry: SavedMatch): 'upcoming' | 'live' | 'finished' {
  const status = entry.match.status;
  if (status === 'live' || status === 'halftime') return 'live';
  if (status === 'finished') return 'finished';
  return 'upcoming';
}

function insertSaved(saved: SavedMatchesSnapshot, entry: SavedMatch): SavedMatchesSnapshot {
  const removed = removeSaved(saved, entry.matchId);
  const bucket = bucketOf(entry);
  const upcoming = bucket === 'upcoming' ? [...removed.upcoming, entry] : removed.upcoming;
  const live = bucket === 'live' ? [...removed.live, entry] : removed.live;
  // `finished` runs most recent first, so a newly saved finished fixture goes to the front.
  const finished = bucket === 'finished' ? [entry, ...removed.finished] : removed.finished;
  return { upcoming, live, finished, counts: countsOf(upcoming, live, finished) };
}

function removeSaved(saved: SavedMatchesSnapshot, matchId: string): SavedMatchesSnapshot {
  const upcoming = saved.upcoming.filter(entry => entry.matchId !== matchId);
  const live = saved.live.filter(entry => entry.matchId !== matchId);
  const finished = saved.finished.filter(entry => entry.matchId !== matchId);
  return { upcoming, live, finished, counts: countsOf(upcoming, live, finished) };
}

/**
 * One shared, optimistic view of what this user follows and has saved.
 *
 * Subscribe with `useFavourites()` (src/hooks/useFavourites.ts) rather than reading `getState()`
 * in a render: the hook wires it to `useSyncExternalStore`, which handles tearing for you.
 */
class FavouritesStore {
  private state: FavouritesState = EMPTY_STATE;
  private listeners = new Set<Listener>();
  private inFlight: Promise<FavouritesSnapshot> | null = null;

  getState = (): FavouritesState => this.state;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  private set(patch: Partial<FavouritesState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach(listener => listener());
  }

  /**
   * Load the snapshot, once.
   *
   * Concurrent callers share the one request. On failure the state becomes `error` with the
   * server's own wording AND the error is rethrown, so neither the store nor the caller can mistake
   * the failure for "this user follows nothing". Any snapshot already held is kept: stale truth
   * beats invented emptiness.
   */
  load = async (): Promise<FavouritesSnapshot> => {
    if (this.inFlight) return this.inFlight;
    const hadData = this.state.data !== null;
    this.set(hadData ? { refreshing: true } : { status: 'loading', error: null });
    const request = favouritesApi.getFavourites();
    this.inFlight = request;
    try {
      const snapshot = await request;
      this.set({ status: 'ready', data: snapshot, error: null, refreshing: false });
      return snapshot;
    } catch (error) {
      this.set({
        status: 'error',
        error: getErrorMessage(error, 'Your saved teams, leagues and matches could not be loaded.'),
        refreshing: false,
      });
      throw error;
    } finally {
      this.inFlight = null;
    }
  };

  /** Load only if nothing has ever been loaded. Never throws: a caller mounting a widget on every
   *  page should not have to catch. The failure is still visible in `status` and `error`. */
  ensureLoaded = (): void => {
    if (this.state.status !== 'idle' || this.inFlight) return;
    void this.load().catch(() => undefined);
  };

  /** Drop everything, e.g. on sign-out. `idle` (not an empty snapshot) so the next reader reloads. */
  reset = (): void => {
    this.inFlight = null;
    this.state = EMPTY_STATE;
    this.listeners.forEach(listener => listener());
  };

  // ------------------------------------------------------------------- reads
  isTeamFollowed = (teamId: string): boolean => Boolean(this.state.data?.teamIds.includes(teamId));
  isLeagueFollowed = (leagueId: string): boolean => Boolean(this.state.data?.leagueIds.includes(leagueId));
  isMatchSaved = (matchId: string): boolean =>
    Boolean(this.state.data && allSaved(this.state.data.savedMatches).some(entry => entry.matchId === matchId));

  savedEntry = (matchId: string): SavedMatch | null => {
    if (!this.state.data) return null;
    return allSaved(this.state.data.savedMatches).find(entry => entry.matchId === matchId) ?? null;
  };

  // ------------------------------------------------------------------- writes
  /**
   * Follow or unfollow a team, optimistically.
   *
   * The id list moves at once; the resolved `teams` list is left alone until the next load, because
   * following an id we hold no row for must not invent a team object to show. On success the
   * server's authoritative `ids` replace the optimistic ones — so hitting the follow limit, or a
   * change made in another tab, corrects the display instead of being papered over.
   */
  setTeamFollowed = (teamId: string, following: boolean): Promise<FollowResult> =>
    this.toggleFollow('team', teamId, following);

  setLeagueFollowed = (leagueId: string, following: boolean): Promise<FollowResult> =>
    this.toggleFollow('league', leagueId, following);

  private async toggleFollow(kind: 'team' | 'league', id: string, following: boolean): Promise<FollowResult> {
    const before = this.state;
    const data = before.data;
    if (data) {
      const ids = following
        ? (kind === 'team' ? withId(data.teamIds, id) : withId(data.leagueIds, id))
        : (kind === 'team' ? without(data.teamIds, id) : without(data.leagueIds, id));
      const optimistic: FavouritesSnapshot = kind === 'team'
        ? { ...data, teamIds: ids, teams: following ? data.teams : data.teams.filter(team => team.id !== id) }
        : { ...data, leagueIds: ids, leagues: following ? data.leagues : data.leagues.filter(league => league.id !== id) };
      this.set({
        data: optimistic,
        ...(kind === 'team'
          ? { pendingTeamIds: withId(before.pendingTeamIds, id) }
          : { pendingLeagueIds: withId(before.pendingLeagueIds, id) }),
      });
    } else {
      this.set(kind === 'team'
        ? { pendingTeamIds: withId(before.pendingTeamIds, id) }
        : { pendingLeagueIds: withId(before.pendingLeagueIds, id) });
    }

    try {
      const result = await favouritesApi.follow(kind, id, following);
      const current = this.state.data;
      this.set({
        // The server's list is the truth. Reconciling rather than trusting the optimistic guess is
        // what makes a refused follow (limit reached) show up as the star going back off.
        data: current
          ? (kind === 'team' ? { ...current, teamIds: result.ids } : { ...current, leagueIds: result.ids })
          : current,
        ...(kind === 'team'
          ? { pendingTeamIds: without(this.state.pendingTeamIds, id) }
          : { pendingLeagueIds: without(this.state.pendingLeagueIds, id) }),
      });
      // A follow that resolved to a team/league we hold no row for only appears in the resolved
      // lists after a reload; refresh quietly so the dashboard fills in rather than staying blank.
      if (result.changed && result.following) void this.load().catch(() => undefined);
      return result;
    } catch (error) {
      // Put back exactly what was there, pending flags included. Leaving the optimistic state up
      // after a failure would show a follow that does not exist on the server.
      this.set({
        data: before.data,
        pendingTeamIds: without(this.state.pendingTeamIds, id),
        pendingLeagueIds: without(this.state.pendingLeagueIds, id),
      });
      throw error;
    }
  }

  /**
   * Save a match (or edit its note), optimistically.
   *
   * Optimism has a limit here: the payload of a save is the fixture itself, and we can only show
   * one we already have. `match` must be supplied when the fixture is not already in the store —
   * without it the save still runs, but the entry appears only once the server's copy comes back.
   */
  saveMatch = async (matchId: string, options?: { note?: string | null; match?: SavedMatch['match'] }): Promise<SaveMatchResult> => {
    const before = this.state;
    const existing = this.savedEntry(matchId);
    const fixture = options?.match ?? existing?.match ?? null;
    // Omitted note means "leave the existing note alone" — the API's rule, mirrored here so the
    // optimistic entry shows the same note the server will keep.
    const note = options?.note === undefined ? (existing?.note ?? null) : (options.note || null);

    if (before.data && fixture) {
      const now = new Date().toISOString();
      const optimisticEntry: SavedMatch = {
        matchId,
        note,
        savedAt: existing?.savedAt ?? now,
        updatedAt: now,
        match: fixture,
      };
      this.set({
        data: { ...before.data, savedMatches: insertSaved(before.data.savedMatches, optimisticEntry) },
        pendingMatchIds: withId(before.pendingMatchIds, matchId),
      });
    } else {
      this.set({ pendingMatchIds: withId(before.pendingMatchIds, matchId) });
    }

    try {
      const result = await favouritesApi.saveMatch(matchId, options?.note);
      const current = this.state.data;
      this.set({
        // Replace the optimistic entry with the server's, which carries the real saved_at and the
        // fixture exactly as every other endpoint serialises it.
        data: current ? { ...current, savedMatches: insertSaved(current.savedMatches, result) } : current,
        pendingMatchIds: without(this.state.pendingMatchIds, matchId),
      });
      return result;
    } catch (error) {
      this.set({ data: before.data, pendingMatchIds: without(this.state.pendingMatchIds, matchId) });
      throw error;
    }
  };

  /** Unsave a match, optimistically. Unsaving something that was not saved is not an error. */
  unsaveMatch = async (matchId: string): Promise<UnsaveMatchResult> => {
    const before = this.state;
    if (before.data) {
      this.set({
        data: { ...before.data, savedMatches: removeSaved(before.data.savedMatches, matchId) },
        pendingMatchIds: withId(before.pendingMatchIds, matchId),
      });
    } else {
      this.set({ pendingMatchIds: withId(before.pendingMatchIds, matchId) });
    }

    try {
      const result = await favouritesApi.unsaveMatch(matchId);
      this.set({ pendingMatchIds: without(this.state.pendingMatchIds, matchId) });
      return result;
    } catch (error) {
      this.set({ data: before.data, pendingMatchIds: without(this.state.pendingMatchIds, matchId) });
      throw error;
    }
  };

  /** Save or unsave in one call, for a toggle control. */
  setMatchSaved = (matchId: string, saved: boolean, options?: { note?: string | null; match?: SavedMatch['match'] }): Promise<SaveMatchResult | UnsaveMatchResult> =>
    saved ? this.saveMatch(matchId, options) : this.unsaveMatch(matchId);
}

export const favouritesStore = new FavouritesStore();

/** A snapshot with nothing in it. Only for a signed-out placeholder — never as an error result. */
export const emptyFavourites = (): FavouritesSnapshot => ({
  teams: [], leagues: [], teamIds: [], leagueIds: [],
  unresolved: { teams: [], leagues: [] },
  savedMatches: emptySaved(),
  limits: { teams: 10, leagues: 5 },
});

export default favouritesStore;
