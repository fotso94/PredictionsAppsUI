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
import { timezoneOffsetMinutes } from './match-data-source';
import type {
  FavouriteLimits, FavouritesSnapshot, FavouritesState, FollowResult, Match, SavedMatch,
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

// ----------------------------------------------------------------------------- staying current
/**
 * WHY ANYTHING REFRESHES AT ALL, AND WHY IT COSTS NO PROVIDER REQUEST
 *
 * A reader who leaves this tab open and comes back an hour later was being shown whatever was on
 * screen when they left: a match that has since kicked off still listed as upcoming, a saved
 * fixture that has finished still showing no score. Nothing in this application refreshed anything
 * — there was no interval and no focus handler anywhere — so the only way to see the current state
 * of a saved match was to reload the page by hand.
 *
 * THE CONSTRAINT THAT DECIDED THE DESIGN. The model-forecast provider's allowance is eight
 * requests a DAY, and the data on these pages is refreshed centrally by the backend's scheduler,
 * not per visitor. So a refresh here may only ever re-read what the backend already holds. Every
 * request on this path is a stored read: `/api/v1/me/*` never touches a provider, `/teams/{id}` is
 * a pure database read, and the one competition endpoint that CAN reach a provider is always sent
 * `refresh=false` (see `feedApi.leagueFixtures`). A visitor arriving, returning to the tab a
 * hundred times and leaving again spends zero provider requests.
 *
 * WHAT IS DELIBERATELY NOT REFRESHED ON FOCUS. The dated match lists (`/api/v1/matches?date=…`)
 * are not touched from here. The backend's own default for that endpoint is `refresh=true`, so a
 * blanket refetch-on-focus over the match lists could spend an allowance the moment somebody
 * alt-tabs. Provider status, coverage and measured performance are not refreshed either: they move
 * on the scheduler's clock rather than the reader's, and re-reading them on focus buys nothing.
 */

/**
 * The smallest age a snapshot must have before returning to the tab re-reads it.
 *
 * This is a COALESCING GUARD, not a ration: `focus` and `visibilitychange` routinely arrive as a
 * pair for one tab switch, and a window manager can fire several in a second. Five seconds
 * collapses those into one request while still meaning "when you come back, this is current".
 */
const FOCUS_REFRESH_MIN_AGE_MS = 5_000;

/**
 * How often a saved match that is IN PLAY is re-read, and nothing else is polled at all.
 *
 * Sixty seconds, because that is the cadence at which this data can actually change for us: the
 * backend refreshes live scores centrally and every client already caches match reads for 60s
 * (CACHE_TTL_MS in backend-match-data.service). Polling faster would return the same rows.
 * The interval exists only while the reader has a match in play AND the tab is visible — a hidden
 * tab and a card of finished fixtures both poll nothing.
 */
const LIVE_REFRESH_MS = 60_000;

/**
 * The same guard for the FOLLOW FAN-OUT, which is not the same size of request.
 *
 * `FOCUS_REFRESH_MIN_AGE_MS` guards one indexed read of the reader's own rows, so five seconds is
 * the right floor for it. The feed is one request PER FOLLOW and the API caps a reader at fifteen,
 * so reusing that constant here made a tab switch cost fifteen reads and put a five-second floor
 * under it: measured on this stack, ten tab-returns six seconds apart issued 150 fixture requests
 * where the favourites snapshot issued 10.
 *
 * Sixty seconds, for the reason already argued for LIVE_REFRESH_MS above: the backend refreshes
 * centrally and every client caches match reads for 60s, so a second fan-out inside the same
 * minute returns the same rows. Nothing is lost — a follow the reader CHANGES still rebuilds the
 * feed immediately, because that path is the favourites subscription, not this one.
 */
const FEED_FOCUS_REFRESH_MIN_AGE_MS = 60_000;

/**
 * Run `handler` when the reader comes back to this tab. Returns the disposer.
 *
 * Both events are listened for because neither alone covers both ways back: switching browser tabs
 * fires `visibilitychange`, while switching applications fires `focus` with the document never
 * having been hidden. They often arrive together, which is what the caller's age guard is for.
 */
function onReaderReturns(handler: () => void): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const wake = () => { if (document.visibilityState === 'visible') handler(); };
  window.addEventListener('focus', wake);
  document.addEventListener('visibilitychange', wake);
  return () => {
    window.removeEventListener('focus', wake);
    document.removeEventListener('visibilitychange', wake);
  };
}

/** True when this tab is in front. Treated as visible where there is no document (SSR, tests). */
const tabIsVisible = (): boolean =>
  typeof document === 'undefined' || document.visibilityState === 'visible';

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
  /** When the last snapshot genuinely arrived. Not part of `state`: nothing renders it. */
  private loadedAt = 0;
  private livePoll: ReturnType<typeof setInterval> | null = null;
  private stopWatchingReturns: (() => void) | null = null;

  getState = (): FavouritesState => this.state;

  /** Milliseconds since the last successful load, or Infinity when nothing has ever loaded. */
  ageMs = (): number => (this.loadedAt === 0 ? Number.POSITIVE_INFINITY : Date.now() - this.loadedAt);

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
      this.loadedAt = Date.now();
      this.set({ status: 'ready', data: snapshot, error: null, refreshing: false });
      // Only now is there something worth keeping current, and only now do we know whether
      // anything is in play.
      this.watchForReturns();
      this.syncLivePoll();
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
    this.loadedAt = 0;
    // Signed out, there is nothing to keep current and nobody to keep it current for. Leaving the
    // listeners attached would have a signed-out tab re-requesting the previous user's favourites
    // every time it came back to the front, and every one of those would be a 401.
    this.stopWatchingReturns?.();
    this.stopWatchingReturns = null;
    this.stopLivePoll();
    this.state = EMPTY_STATE;
    this.listeners.forEach(listener => listener());
  };

  // ------------------------------------------------------------------- staying current
  /**
   * Re-read the snapshot if it is older than `minAgeMs`. Never throws, never reports a failure to
   * the reader: this is a background refresh they did not ask for, and the state it leaves behind
   * is the honest one either way — a failed refresh sets `status: 'error'` while keeping the last
   * snapshot it really received.
   */
  refreshIfStale = (minAgeMs = FOCUS_REFRESH_MIN_AGE_MS): void => {
    if (this.state.data === null || this.inFlight) return;
    if (this.ageMs() < minAgeMs) return;
    void this.load().catch(() => undefined);
  };

  private watchForReturns(): void {
    if (this.stopWatchingReturns) return;
    const stopWake = onReaderReturns(() => {
      // A tab coming back to the front is also the moment a poll should start or stop: it may have
      // been hidden for an hour, during which nothing was polled at all.
      this.syncLivePoll();
      this.refreshIfStale();
    });
    // `onReaderReturns` only fires on the way BACK. This is its pair: the moment the tab goes
    // away, so an interval is not left running behind a hidden tab.
    const onHidden = () => { if (!tabIsVisible()) this.stopLivePoll(); };
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onHidden);
    this.stopWatchingReturns = () => {
      stopWake();
      if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onHidden);
    };
  }

  /** Poll only while a saved match is in play and the tab is in front; otherwise not at all. */
  private syncLivePoll(): void {
    const inPlay = this.state.data?.savedMatches.live.length ?? 0;
    const shouldPoll = inPlay > 0 && tabIsVisible() && typeof window !== 'undefined';
    if (shouldPoll && !this.livePoll) {
      this.livePoll = setInterval(() => {
        if (!tabIsVisible()) return;
        this.refreshIfStale(LIVE_REFRESH_MS - 1_000);
      }, LIVE_REFRESH_MS);
    } else if (!shouldPoll) {
      this.stopLivePoll();
    }
  }

  private stopLivePoll(): void {
    if (this.livePoll === null) return;
    clearInterval(this.livePoll);
    this.livePoll = null;
  }

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

// ------------------------------------------------------------------ fixtures behind a follow
/**
 * The fixtures that make a follow worth having: what each followed team and competition has coming
 * up, and what they have just played.
 *
 * WHY THESE CALLS AND NOT `backendMatchDataService.getFixturesByLeague`
 * That reader sends no `refresh` parameter, so the backend applies its own default — the route is
 * declared `refresh: bool = Query(True)` — and `MatchDataService.sync_upcoming` then goes out to
 * the fixtures provider. A dashboard rebuilding this feed whenever the reader came back to the tab
 * would spend a provider request per followed competition per visit, and the forecast provider's
 * allowance is eight requests a DAY. So `refresh=false` is sent explicitly here, and the backend
 * answers from stored rows (`source: "database"`, `provider: null`, nothing spent).
 * `GET /api/v1/teams/{id}` needs no such parameter: it touches no provider at all.
 *
 * ONE REQUEST PER FOLLOW, WHICH IS THE SHAPE THE API OFFERS. There is no endpoint that returns the
 * fixtures behind every follow at once, so this fans out over the follows — at most 15 of them,
 * since the API caps a user at 10 teams and 5 competitions — four at a time. A single
 * `GET /api/v1/me/feed` would be one request instead of fifteen; that is written up for the
 * backend's owner rather than invented here.
 */

/** How far either side of now a followed team or competition contributes fixtures to the feed. */
export const FEED_DAYS_AHEAD = 7;
export const FEED_DAYS_BACK = 3;

/** How many fixtures reached only through a follow each group of the feed will show. */
export const FEED_FOLLOWED_CAP: Record<FeedPhase, number> = { live: 20, result: 8, upcoming: 12 };

/** Requests in flight at once while fanning out over the follows. Polite, not fast. */
const FEED_CONCURRENCY = 4;

export const feedApi = {
  /** Everything stored for one team, both directions. A pure database read on the backend. */
  async teamFixtures(teamId: string): Promise<Match[]> {
    const { data } = await apiClient.get<{ team: ApiTeam; upcoming?: ApiMatch[]; recent?: ApiMatch[] }>(
      `/api/v1/teams/${encodeURIComponent(teamId)}`);
    return [...(data.upcoming ?? []), ...(data.recent ?? [])].map(mapApiMatch);
  },

  /** One competition's window. `refresh=false` is the whole point — see the note above. */
  async leagueFixtures(leagueId: string): Promise<Match[]> {
    const { data } = await apiClient.get<{ matches?: ApiMatch[] }>(
      `/api/v1/leagues/${encodeURIComponent(leagueId)}/matches`,
      {
        params: {
          refresh: false,
          days_ahead: FEED_DAYS_AHEAD,
          days_back: FEED_DAYS_BACK,
          tz_offset: timezoneOffsetMinutes(),
        },
      });
    return (data.matches ?? []).map(mapApiMatch);
  },
};

/** Why a fixture is in the feed. Shown on the row: a feed nobody can explain is a feed nobody trusts. */
export interface FeedReason {
  kind: 'saved' | 'team' | 'league';
  id: string;
  /** What to call it on screen: 'Saved', or the team's or competition's own name. */
  label: string;
}

export interface FollowedFixture {
  match: Match;
  reasons: FeedReason[];
}

export interface FollowedFixturesState {
  status: 'idle' | 'loading' | 'ready' | 'error';
  fixtures: FollowedFixture[];
  /**
   * The follows whose fixtures could not be read — NAMED, not merely counted.
   *
   * NOT an error for the whole feed: the rest of it is real and is shown. But a count is only
   * enough for the summary line, and every consumer that renders a follow ROW needs to know
   * whether THIS follow is one of them. Without that a followed team whose request came back 500
   * was indistinguishable from one with nothing scheduled, and the row said "No fixture stored
   * for the next 7 days" — a positive claim about data that had never arrived, which is rule 1 of
   * this module broken at the last step before the screen.
   */
  unreadable: FeedReason[];
  /**
   * True while a rebuild is in flight over a feed that is already showing something.
   *
   * `status` cannot carry this: a background refresh must not blank the feed, so it stays 'ready'
   * throughout. A reader who has just pressed Retry on a failed follow is owed the difference
   * between "working on it" and "nothing happened".
   */
  refreshing: boolean;
  /** Set only when the whole load failed. The server's own wording where it gave one. */
  error: string | null;
}

const EMPTY_FOLLOWED: FollowedFixturesState = Object.freeze({
  status: 'idle' as const, fixtures: [], unreadable: [], refreshing: false, error: null,
});

/** True when this particular follow is one whose fixtures could not be read. */
export function followIsUnreadable(
  state: FollowedFixturesState, kind: 'team' | 'league', id: string,
): boolean {
  return state.unreadable.some(follow => follow.kind === kind && follow.id === id);
}

/** The follows a feed was built from, so a changed follow list can be noticed and nothing else can. */
function followKey(snapshot: FavouritesSnapshot | null): string {
  if (!snapshot) return '';
  return `t:${[...snapshot.teamIds].sort().join(',')}|l:${[...snapshot.leagueIds].sort().join(',')}`;
}

/** Run `work` over `items`, at most `limit` at a time. Rejections are the caller's to inspect. */
async function mapWithLimit<T, R>(items: T[], limit: number, work: (item: T) => Promise<R>): Promise<PromiseSettledResult<R>[]> {
  const results: PromiseSettledResult<R>[] = new Array(items.length);
  let next = 0;
  const runner = async (): Promise<void> => {
    for (let index = next++; index < items.length; index = next++) {
      try {
        results[index] = { status: 'fulfilled', value: await work(items[index]) };
      } catch (reason) {
        results[index] = { status: 'rejected', reason };
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, runner));
  return results;
}

/**
 * The fixtures behind this user's follows, loaded on demand and kept current while somebody is
 * looking at them.
 *
 * It is a second store rather than part of the favourites snapshot because it is much more
 * expensive to build (one request per follow) and only one panel needs it. It attaches its focus
 * listener when it gains its first subscriber and drops it with the last, so a page that never
 * renders the feed never refreshes it.
 */
class FollowedFixturesStore {
  private state: FollowedFixturesState = EMPTY_FOLLOWED;
  private listeners = new Set<Listener>();
  private inFlight: Promise<void> | null = null;
  private loadedAt = 0;
  /** The follow list the current `fixtures` were built from. */
  private builtFrom = '';
  private detach: (() => void) | null = null;
  private livePoll: ReturnType<typeof setInterval> | null = null;

  getState = (): FollowedFixturesState => this.state;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    if (this.listeners.size === 1) this.attach();
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) this.release();
    };
  };

  private set(patch: Partial<FollowedFixturesState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach(listener => listener());
  }

  private attach(): void {
    if (this.detach) return;
    const stopWake = onReaderReturns(() => { this.syncLivePoll(); this.refreshIfStale(); });
    // Following or unfollowing changes what belongs in the feed, and so does signing out. Watching
    // the favourites store is what makes a newly followed team's fixtures appear without a reload.
    const stopFollowing = favouritesStore.subscribe(() => this.onFavouritesChanged());
    const onHidden = () => { if (!tabIsVisible()) this.stopLivePoll(); };
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onHidden);
    this.detach = () => {
      stopWake();
      stopFollowing();
      if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onHidden);
    };
  }

  /** The last subscriber left: nobody is looking at this feed, so nothing about it is refreshed. */
  private release(): void {
    this.detach?.();
    this.detach = null;
    this.stopLivePoll();
  }

  /**
   * Poll only while a fixture in this feed is actually in play, the tab is in front and somebody
   * is subscribed — which on this build means the dashboard is the page on screen.
   *
   * This costs one stored read per follow per minute, which is more than the favourites store's
   * single request, and it is spent only in the one situation that justifies it: a reader
   * watching a dashboard with a match running on it. It stops the moment the tab goes away, the
   * match ends, or they navigate off the page.
   */
  private syncLivePoll(): void {
    const inPlay = this.state.fixtures.some(entry => (
      entry.match.status === 'live' || entry.match.status === 'halftime'
    ));
    const shouldPoll = inPlay && this.listeners.size > 0 && tabIsVisible() && typeof window !== 'undefined';
    if (shouldPoll && !this.livePoll) {
      this.livePoll = setInterval(() => {
        if (!tabIsVisible()) return;
        this.refreshIfStale(LIVE_REFRESH_MS - 1_000);
      }, LIVE_REFRESH_MS);
    } else if (!shouldPoll) {
      this.stopLivePoll();
    }
  }

  private stopLivePoll(): void {
    if (this.livePoll === null) return;
    clearInterval(this.livePoll);
    this.livePoll = null;
  }

  private onFavouritesChanged(): void {
    const snapshot = favouritesStore.getState().data;
    if (snapshot === null) {
      // Signed out, or reset. Drop the feed rather than leave the previous user's fixtures up.
      if (this.state.status !== 'idle') {
        this.builtFrom = '';
        this.loadedAt = 0;
        this.stopLivePoll();
        this.set({ status: 'idle', fixtures: [], unreadable: [], refreshing: false, error: null });
      }
      return;
    }
    if (followKey(snapshot) !== this.builtFrom) void this.load();
  }

  /** Load once. Safe to call from a render effect: it returns immediately when nothing changed. */
  ensureLoaded = (): void => {
    const snapshot = favouritesStore.getState().data;
    if (!snapshot) return;
    if (this.inFlight) return;
    if (this.state.status !== 'idle' && followKey(snapshot) === this.builtFrom) return;
    void this.load();
  };

  refreshIfStale = (minAgeMs = FEED_FOCUS_REFRESH_MIN_AGE_MS): void => {
    if (this.state.status === 'idle' || this.inFlight) return;
    if (this.loadedAt !== 0 && Date.now() - this.loadedAt < minAgeMs) return;
    void this.load();
  };

  /**
   * Rebuild the feed from the follows currently held.
   *
   * A follow that cannot be read is RECORDED BY NAME, not dropped silently and not escalated into
   * a failure for the whole feed: the other follows produced real fixtures and those are shown,
   * and the panels can both count the missing follows and say, on the row of each one, that its
   * fixtures are unknown rather than absent.
   */
  load = async (): Promise<void> => {
    if (this.inFlight) return this.inFlight;
    const snapshot = favouritesStore.getState().data;
    if (!snapshot) return;

    const key = followKey(snapshot);
    const teamName = new Map(snapshot.teams.map(team => [team.id, team.name]));
    const leagueName = new Map(snapshot.leagues.map(league => [league.id, league.name]));
    const follows: FeedReason[] = [
      ...snapshot.teamIds.map(id => ({ kind: 'team' as const, id, label: teamName.get(id) ?? 'A team you follow' })),
      ...snapshot.leagueIds.map(id => ({ kind: 'league' as const, id, label: leagueName.get(id) ?? 'A competition you follow' })),
    ];

    if (follows.length === 0) {
      this.builtFrom = key;
      this.loadedAt = Date.now();
      this.stopLivePoll();
      this.set({ status: 'ready', fixtures: [], unreadable: [], refreshing: false, error: null });
      return;
    }

    this.set(this.state.status === 'ready'
      ? { refreshing: true }
      : { status: 'loading', refreshing: true, error: null });
    const run = (async () => {
      const settled = await mapWithLimit(follows, FEED_CONCURRENCY, follow => (
        follow.kind === 'team' ? feedApi.teamFixtures(follow.id) : feedApi.leagueFixtures(follow.id)
      ));

      const byMatch = new Map<string, FollowedFixture>();
      const unreadable: FeedReason[] = [];
      settled.forEach((result, index) => {
        if (result.status === 'rejected') { unreadable.push(follows[index]); return; }
        result.value.forEach(match => {
          const held = byMatch.get(match.id);
          // One fixture can arrive from both clubs and its competition. It is one row carrying
          // every reason it is there, never three rows.
          if (held) held.reasons.push(follows[index]);
          else byMatch.set(match.id, { match, reasons: [follows[index]] });
        });
      });

      this.builtFrom = key;
      this.loadedAt = Date.now();
      const allFailed = unreadable.length === follows.length;
      this.set({
        status: allFailed ? 'error' : 'ready',
        fixtures: Array.from(byMatch.values()),
        unreadable,
        refreshing: false,
        error: allFailed
          ? 'The fixtures behind the teams and competitions you follow could not be loaded.'
          : null,
      });
      // Whether anything is in play is only known once the fixtures are in hand.
      this.syncLivePoll();
    })();

    this.inFlight = run.finally(() => {
      this.inFlight = null;
      // Belt and braces: nothing in `run` throws today, but a load that ended without clearing
      // this would leave every Retry control disabled for the rest of the session.
      if (this.state.refreshing) this.set({ refreshing: false });
      // A follow changed WHILE this load was running. The notification that would have rebuilt
      // the feed was swallowed by the in-flight guard, so without this the newly followed team's
      // fixtures would never appear — the exact failure the guard exists to avoid causing.
      if (followKey(favouritesStore.getState().data) !== this.builtFrom) void this.load();
    });
    return this.inFlight;
  };
}

export const followedFixturesStore = new FollowedFixturesStore();

// ------------------------------------------------------------------------------- the feed
export type FeedPhase = 'live' | 'result' | 'upcoming';

export interface FeedEntry {
  matchId: string;
  match: Match;
  /** The user's own save row when they saved this fixture, so the note travels with it. */
  saved: SavedMatch | null;
  reasons: FeedReason[];
  phase: FeedPhase;
  /** Kick-off as milliseconds since the epoch, or null when the payload carried no usable time. */
  kickoffMs: number | null;
}

export interface FeedGroup {
  phase: FeedPhase;
  entries: FeedEntry[];
  /** Everything that qualified for the group, including what the cap left out. */
  total: number;
  /** Fixtures the cap left out. Only ever ones reached through a follow — never a saved match. */
  hidden: number;
}

/** Same rule as `bucketOf`, named for the feed: anything neither in play nor played is still ahead. */
function phaseOf(match: Match): FeedPhase {
  if (match.status === 'live' || match.status === 'halftime') return 'live';
  if (match.status === 'finished') return 'result';
  return 'upcoming';
}

function kickoffMsOf(match: Match): number | null {
  const parsed = match.kickoffUtc ? Date.parse(match.kickoffUtc) : NaN;
  if (!Number.isNaN(parsed)) return parsed;
  // No `kickoff_utc` on the payload: the calendar date is all we have, and it still orders the
  // fixture to the right day. Never a guessed time of day dressed up as one we were given.
  const fromDate = match.date ? Date.parse(`${match.date}T00:00:00Z`) : NaN;
  return Number.isNaN(fromDate) ? null : fromDate;
}

/**
 * Build the one ordered feed the dashboard shows, from what this user saved and what they follow.
 *
 * THE ORDER, AND WHY IT IS THIS ONE. A reader comes back to this page with three questions, in
 * this order: is anything happening right now, what happened while I was away, and what is next.
 *
 *  1. IN PLAY, earliest kick-off first — the match nearest full time is the one whose result is
 *     about to land.
 *  2. RESULTS, most recent first. They sit ABOVE the upcoming fixtures deliberately: a result is
 *     the only part of this feed that is new information, and it is the end of the journey that
 *     began when the reader saved the match. An upcoming fixture says the same thing today that it
 *     said yesterday.
 *  3. COMING UP, soonest first.
 *
 * WHAT THE WINDOW DOES AND DOES NOT CUT. A fixture reached through a follow only appears inside
 * the feed's window (FEED_DAYS_BACK behind, FEED_DAYS_AHEAD ahead), because a followed competition
 * holds a whole season and that is a calendar, not a feed. A SAVED match is never cut by the
 * window or by the cap: the reader asked for that one by name, and a dashboard that quietly
 * dropped it would be worse than one that never offered saving.
 */
export function buildFeed(
  snapshot: FavouritesSnapshot | null,
  followed: FollowedFixture[],
  now: number = Date.now(),
): FeedGroup[] {
  const entries = new Map<string, FeedEntry>();

  const add = (match: Match, saved: SavedMatch | null, reasons: FeedReason[]): void => {
    const held = entries.get(match.id);
    if (held) {
      reasons.forEach(reason => {
        if (!held.reasons.some(existing => existing.kind === reason.kind && existing.id === reason.id)) {
          held.reasons.push(reason);
        }
      });
      return;
    }
    entries.set(match.id, {
      matchId: match.id,
      match,
      saved,
      reasons: [...reasons],
      phase: phaseOf(match),
      kickoffMs: kickoffMsOf(match),
    });
  };

  if (snapshot) {
    allSaved(snapshot.savedMatches).forEach(entry => {
      add(entry.match, entry, [{ kind: 'saved', id: entry.matchId, label: 'Saved' }]);
    });
  }

  const earliest = now - FEED_DAYS_BACK * 86_400_000;
  const latest = now + FEED_DAYS_AHEAD * 86_400_000;
  followed.forEach(({ match, reasons }) => {
    if (entries.has(match.id)) { add(match, null, reasons); return; }
    const at = kickoffMsOf(match);
    // A fixture with no usable time is kept: dropping a real fixture because its payload was thin
    // would be inventing an absence. It sorts to the end of its group.
    if (at !== null && (at < earliest || at > latest)) return;
    add(match, null, reasons);
  });

  const order: Record<FeedPhase, (a: FeedEntry, b: FeedEntry) => number> = {
    live: (a, b) => byTime(a, b, 1),
    result: (a, b) => byTime(a, b, -1),
    upcoming: (a, b) => byTime(a, b, 1),
  };

  return (['live', 'result', 'upcoming'] as const).map(phase => {
    const all = Array.from(entries.values()).filter(entry => entry.phase === phase).sort(order[phase]);
    let room = FEED_FOLLOWED_CAP[phase];
    let hidden = 0;
    const kept = all.filter(entry => {
      if (entry.saved) return true;
      if (room > 0) { room -= 1; return true; }
      hidden += 1;
      return false;
    });
    return { phase, entries: kept, total: all.length, hidden };
  });
}

/** Kick-off order, `direction` 1 for soonest first and -1 for most recent first. Unknown times last. */
function byTime(a: FeedEntry, b: FeedEntry, direction: 1 | -1): number {
  if (a.kickoffMs === null && b.kickoffMs === null) return 0;
  if (a.kickoffMs === null) return 1;
  if (b.kickoffMs === null) return -1;
  return (a.kickoffMs - b.kickoffMs) * direction;
}

export default favouritesStore;
