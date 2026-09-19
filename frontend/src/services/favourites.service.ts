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

import { useCallback, useEffect, useSyncExternalStore } from 'react';

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

/**
 * The instant a saved fixture kicks off, or null when we were not given one.
 *
 * DELIBERATELY NOT `kickoffMsOf` (further down this file, for the feed). That one falls back to
 * the calendar date at midnight UTC, which is right for ORDERING a fixture into its day and wrong
 * for deciding whether it has started: it would make every fixture on today's date look overdue
 * from midnight onwards, and start a poll for each one. A fixture whose payload carries no
 * kick-off time is not watched for a kick-off we do not know.
 */
function kickoffTimeOf(entry: SavedMatch): number | null {
  const parsed = entry.match.kickoffUtc ? Date.parse(entry.match.kickoffUtc) : NaN;
  return Number.isNaN(parsed) ? null : parsed;
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
 * WHY A SAVED FIXTURE THAT IS ONLY ABOUT TO START IS WATCHED AT ALL.
 *
 * `syncLivePoll()` used to start its interval only when `savedMatches.live` was non-empty. A
 * fixture that is still upcoming leaves that bucket empty, so no interval ran, so nothing noticed
 * the kick-off: the poll that would have discovered the transition was gated on the state it
 * would have discovered. A reader with the page in front of them watched "Coming up" all through
 * the first half, because the focus refresh only fires on the way BACK to a tab and nothing else
 * re-read anything.
 *
 * WHAT IS WATCHED, AND FOR HOW LONG. Only a saved fixture the record still says is going to be
 * played (`scheduled` — a postponed or cancelled one will not kick off at this time, and watching
 * it would poll for hours over nothing), and only from shortly before its kick-off until the
 * window in which it could still plausibly start has passed. Outside that, nothing is polled: a
 * reader with a fixture saved for Saturday costs one read when they open the page and no more.
 *
 * THE LEAD is for the two clocks involved. The kick-off time is the server's and the comparison
 * is made against the browser's, which can be a minute or two out either way, and the backend's
 * own live pass runs on its schedule rather than on the whistle.
 *
 * THE GRACE is how long a fixture that has not started is still worth watching. Delayed kick-offs
 * are ordinary football. A saved fixture still `scheduled` two hours after its time is either
 * postponed without the record being updated or a row nothing is moving; either way the answer
 * is not going to arrive in the next minute, and the reader's next return to the tab is a better
 * moment to find out than another sixty polls.
 */
const KICKOFF_WATCH_LEAD_MS = 2 * 60 * 1000;
const KICKOFF_WATCH_GRACE_MS = 2 * 60 * 60 * 1000;

/**
 * How often a saved fixture that is DUE to start is re-read, which is deliberately slower than
 * the in-play cadence.
 *
 * `LIVE_REFRESH_MS` is 60s because that is how often a score can change for us. Waiting for a
 * kick-off is not a score: it is one status flip, applied by the backend's own live pass, and
 * `SYNC_LIVE_INTERVAL_SECONDS` is 120. Asking twice inside one of those passes cannot see the
 * flip any sooner, so it is asked once.
 */
const KICKOFF_REFRESH_MS = 120_000;

/**
 * The longest a single "a saved fixture is about to start" timer is allowed to run before it
 * re-arms itself.
 *
 * A fixture three days away must not park a three-day `setTimeout` — a laptop that suspends and
 * resumes, or a clock that is corrected, leaves one of those pointing at the wrong moment, and
 * anything past 2^31 ms fires immediately instead. A clamped wake costs nothing at all: it finds
 * nothing due and schedules the next one.
 */
const KICKOFF_WAKE_MAX_MS = 30 * 60 * 1000;

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

// ------------------------------------------------------- what the personal surfaces may show
/**
 * The reader's own settings for their own pages: what these surfaces are allowed to show them,
 * and one switch that stops all of it.
 *
 * WHAT IS ACTUALLY OPTIONAL HERE, ENUMERATED
 *
 * This application has no alerts. It sends no push message, no SMS and no marketing email — the
 * only mail it ever sends is account mail the reader asked for, such as a password reset. So the
 * complete list of things these surfaces raise without being asked is three items long, and all
 * three only ever happen while the reader is looking at the page:
 *
 *   `forecasts`    the model and expert probabilities, tips and briefs shown beside a fixture;
 *   `prompts`      the invitations to go and browse more, or follow more;
 *   `liveUpdates`  automatically re-reading a saved match while it is in play.
 *
 * WHY A PAUSE IS A SEPARATE FLAG AND NOT JUST "TURN ALL THREE OFF". A pause has to be immediate
 * and, more importantly, REVERSIBLE WITHOUT LOSS: a reader who had forecasts off and prompts on
 * before they paused gets exactly that back when they resume. Writing the three flags to false
 * and back would forget which was which and hand them a configuration they never chose.
 *
 * WHAT A PAUSE IS NOT, AND THIS MATTERS MORE THAN ANYTHING ELSE IN THIS FILE. It stops what THIS
 * application shows on these pages. It is not a bookmaker self-exclusion, it blocks no betting
 * site, app, account or payment, and it reaches nothing outside this browser. Software on one
 * page cannot do those things, and a control that implied it could would be worse than no control
 * at all — a reader who believed it would stop looking for the tool that actually helps. Every
 * sentence rendered next to this switch has to keep saying so.
 *
 * WHERE IT IS STORED. `localStorage`, keyed per signed-in user id so a shared machine never hands
 * one reader another's settings. The API has no field for any of this (`PUT /users/me/preferences`
 * accepts theme, notification flags, favourite ids and an odds format, and nothing else), so these
 * do not follow a reader to another device, and the panel says so rather than letting them assume.
 */
export interface PersonalPreferences {
  /** Show model forecasts, expert tips and probabilities on the reader's own pages. */
  forecasts: boolean;
  /** Show invitations to browse more matches or follow more teams. */
  prompts: boolean;
  /** Re-read a saved match automatically while it is in play. */
  liveUpdates: boolean;
  /** While true, none of the three above is shown or run, whatever their own values say. */
  paused: boolean;
}

/** The three things a reader can switch individually. `paused` is the one that governs them. */
export type OptionalSurface = 'forecasts' | 'prompts' | 'liveUpdates';

/**
 * The defaults, which are what this build already did before there was anything to set.
 *
 * Deliberately not "everything off": silently changing what an existing reader sees, because a
 * preference they never expressed now has an opinion, is its own kind of dishonesty. Quiet by
 * default is delivered by there being no channel that can reach anybody who is not on the page —
 * see the enumeration above — not by blanking the page of the reader who is.
 */
export const DEFAULT_PREFERENCES: PersonalPreferences = Object.freeze({
  forecasts: true,
  prompts: true,
  liveUpdates: true,
  paused: false,
});

const PREFERENCES_KEY_PREFIX = 'personal.preferences.v1';

const preferencesKeyFor = (userId: string | null | undefined): string =>
  `${PREFERENCES_KEY_PREFIX}.${userId || 'anonymous'}`;

/** Field by field, never a cast: what is in storage is last week's shape, or corrupt. */
function coercePreferences(raw: unknown): PersonalPreferences {
  const source = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const flag = (value: unknown, fallback: boolean): boolean =>
    (typeof value === 'boolean' ? value : fallback);
  return {
    forecasts: flag(source.forecasts, DEFAULT_PREFERENCES.forecasts),
    prompts: flag(source.prompts, DEFAULT_PREFERENCES.prompts),
    liveUpdates: flag(source.liveUpdates, DEFAULT_PREFERENCES.liveUpdates),
    paused: flag(source.paused, DEFAULT_PREFERENCES.paused),
  };
}

/**
 * The settings store.
 *
 * Every read and write is wrapped: `localStorage` throws outright in a browser set to block site
 * data, and losing a preference must never take the dashboard down with it. A browser that
 * refuses storage simply gets the defaults for the session, and the panel says the setting could
 * not be kept rather than pretending it was.
 */
class PersonalPreferencesStore {
  private state: PersonalPreferences = { ...DEFAULT_PREFERENCES };
  private key = preferencesKeyFor(null);
  private listeners = new Set<Listener>();
  /** True when the last write to storage threw. Rendered, not swallowed. */
  private storageFailed = false;

  getState = (): PersonalPreferences => this.state;

  /** True when this browser refused to keep the last change. */
  isDurable = (): boolean => !this.storageFailed;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  private emit(): void {
    this.listeners.forEach(listener => listener());
  }

  /**
   * Point the store at one account's settings. Idempotent, and safe to call on every render.
   *
   * Signing out rebinds to the anonymous key rather than clearing: the next reader on this machine
   * must not inherit the last one's settings, and the last one's must still be there when they
   * come back.
   */
  bindAccount = (userId: string | null | undefined): void => {
    const key = preferencesKeyFor(userId);
    if (key === this.key) return;
    this.key = key;
    this.state = this.read();
    this.emit();
  };

  private read(): PersonalPreferences {
    try {
      const raw = window.localStorage.getItem(this.key);
      return raw ? coercePreferences(JSON.parse(raw)) : { ...DEFAULT_PREFERENCES };
    } catch {
      return { ...DEFAULT_PREFERENCES };
    }
  }

  private write(next: PersonalPreferences): void {
    this.state = next;
    try {
      window.localStorage.setItem(this.key, JSON.stringify(next));
      this.storageFailed = false;
    } catch {
      // Kept for this session in memory; the panel reports that it will not survive a reload.
      this.storageFailed = true;
    }
    this.emit();
  }

  /** Change one setting. Changing an individual switch never silently lifts a pause. */
  setSurface = (surface: OptionalSurface, on: boolean): void => {
    if (this.state[surface] === on) return;
    this.write({ ...this.state, [surface]: on });
  };

  /**
   * Pause or resume everything optional.
   *
   * The three individual settings are left exactly as they are, so resuming restores the reader's
   * own configuration rather than a default one.
   */
  setPaused = (paused: boolean): void => {
    if (this.state.paused === paused) return;
    this.write({ ...this.state, paused });
  };

  /** Forget this account's settings entirely. Used by "delete my data". */
  forget = (): void => {
    try {
      window.localStorage.removeItem(this.key);
      this.storageFailed = false;
    } catch {
      this.storageFailed = true;
    }
    this.state = { ...DEFAULT_PREFERENCES };
    this.emit();
  };

  /** Whether one optional surface may run right now. A pause beats every individual setting. */
  isOn = (surface: OptionalSurface): boolean => !this.state.paused && this.state[surface];
}

export const personalPreferencesStore = new PersonalPreferencesStore();

/** Whether `surface` may appear, given these settings. The one place the pause rule is applied. */
export function surfaceIsOn(prefs: PersonalPreferences, surface: OptionalSurface): boolean {
  return !prefs.paused && prefs[surface];
}

export interface UsePersonalPreferencesResult extends PersonalPreferences {
  /** Whether this surface may appear right now — the individual setting AND the pause. */
  isOn: (surface: OptionalSurface) => boolean;
  setSurface: (surface: OptionalSurface, on: boolean) => void;
  setPaused: (paused: boolean) => void;
  /** False when this browser refused to keep the last change. */
  durable: boolean;
}

/**
 * React access to the settings, bound to whoever is signed in.
 *
 * WHY THIS HOOK IS IN THE SERVICE AND NOT BESIDE THE PANEL THAT RENDERS THE SWITCHES. Every
 * surface that hides something on a preference has to apply the pause rule as well as the
 * individual switch, and a panel that honoured one and forgot the other would be the exact defect
 * the pause exists to prevent. Keeping the store, `surfaceIsOn` and this binding in one module is
 * what makes that impossible to get half right. It cannot live in the component file either: a
 * module that exports both a component and a hook breaks Fast Refresh, which this project lints
 * as an error (`react-refresh/only-export-components`), and src/hooks belongs to another owner.
 *
 * The account is bound in an effect rather than during render, because `bindAccount` notifies its
 * subscribers and notifying a store mid-render is how React ends up warning that one component is
 * updating another while it renders. The cost is the defaults for a single frame after a sign-in.
 */
export function usePersonalPreferences(userId: string | null | undefined): UsePersonalPreferencesResult {
  const prefs = useSyncExternalStore(
    personalPreferencesStore.subscribe,
    personalPreferencesStore.getState,
    personalPreferencesStore.getState,
  );

  useEffect(() => { personalPreferencesStore.bindAccount(userId); }, [userId]);

  const isOn = useCallback((surface: OptionalSurface) => surfaceIsOn(prefs, surface), [prefs]);

  return {
    ...prefs,
    isOn,
    setSurface: personalPreferencesStore.setSurface,
    setPaused: personalPreferencesStore.setPaused,
    durable: personalPreferencesStore.isDurable(),
  };
}

/**
 * A read whose answer belongs to a session that has ended, refused rather than applied.
 *
 * It is never shown to anybody and never means "the request failed": the request was made on
 * behalf of a reader who is no longer here, and the honest thing to tell whoever is here now is
 * nothing at all. Every caller inside this file swallows it, and the three panels that can reach
 * `reload()` already `.catch(() => undefined)`.
 */
class DiscardedRead extends Error {
  constructor() {
    super('This favourites read belongs to a session that has ended, and was discarded.');
    this.name = 'DiscardedRead';
  }
}

/**
 * How many times one `load()` will discard a snapshot that turned out to predate a local write
 * and read again before giving up.
 *
 * A retry only happens when the reader completed a write WHILE the read was on the wire, so in
 * practice it happens once or not at all — a person cannot press a star faster than the round
 * trip indefinitely. The bound is here so that a stuck caller writing in a loop cannot turn this
 * into one; on exhaustion the optimistic state stands, which is the newer of the two, and the
 * next tab return reconciles it.
 */
const MAX_SUPERSEDED_REREADS = 4;

/**
 * One shared, optimistic view of what this user follows and has saved.
 *
 * Subscribe with `useFavourites()` (src/hooks/useFavourites.ts) rather than reading `getState()`
 * in a render: the hook wires it to `useSyncExternalStore`, which handles tearing for you.
 *
 * TWO COUNTERS DECIDE WHETHER AN ANSWER MAY BE APPLIED, and they are the whole of the concurrency
 * design in this class. A read is one round trip; anything can happen during it.
 *
 *   `session`  bumped whenever the identity behind this store changes — signing in, signing out,
 *              or one account replacing another on the same machine. A read captures it when it
 *              is ISSUED. If it no longer matches when the answer lands, the answer belonged to
 *              somebody else's session and is dropped WITHOUT A TRACE: no data, no error, no
 *              `loadedAt`, no focus watcher, no poll. `reset()` cannot cancel a request that is
 *              already on the wire, so this is what stops it being applied.
 *
 *   `writes`   bumped whenever a local write changes what we hold. A snapshot the server built
 *              before that write cannot contain it, so applying it would silently undo the
 *              reader's own action — the star going back off on its own. Such a read is
 *              discarded AND REPLACED by a fresh one, because the reader is still owed the
 *              server's current answer and not merely the absence of a wrong one.
 */
class FavouritesStore {
  private state: FavouritesState = EMPTY_STATE;
  private listeners = new Set<Listener>();
  private inFlight: Promise<FavouritesSnapshot> | null = null;
  /** When the last snapshot genuinely arrived. Not part of `state`: nothing renders it. */
  private loadedAt = 0;
  private livePoll: ReturnType<typeof setInterval> | null = null;
  /** The period the running interval was created with, so a change of cadence restarts it. */
  private livePollPeriodMs = 0;
  /** The one-shot timer that wakes this store when a saved fixture reaches its kick-off. */
  private kickoffWake: ReturnType<typeof setTimeout> | null = null;
  private stopWatchingReturns: (() => void) | null = null;
  /**
   * Whose favourites these are.
   *
   * The store held no identity at all before, which is why an answer could not be told apart from
   * one belonging to another account: `reset()` on sign-out was the only signal, and a sign-out
   * immediately followed by a different sign-in looked, from in here, like one continuous
   * session. It is a key rather than the user object — `useFavourites` passes the signed-in id —
   * and nothing is done with it but comparison.
   */
  private accountId: string | null = null;

  private session = 0;

  private writes = 0;

  getState = (): FavouritesState => this.state;

  /**
   * Which session this store is on. Bumped by every identity change and every reset.
   *
   * Exposed so `followedFixturesStore`, whose fan-out is built from this store's snapshot and
   * takes far longer than one request, can make the same check before applying its own answer.
   */
  sessionId = (): number => this.session;

  /**
   * Point the store at one account, invalidating anything in flight for the previous one.
   *
   * Idempotent, and safe to call on every render. Signing out binds `null`. An ACCOUNT CHANGE is
   * the case this exists for: it is not the same event as a sign-out, it is the one that can put
   * one person's saved matches in front of another, and before this the store could not see the
   * difference.
   */
  bindAccount = (userId: string | null | undefined): void => {
    const next = userId ?? null;
    if (next === this.accountId) return;
    this.accountId = next;
    this.reset();
  };

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
  load = (): Promise<FavouritesSnapshot> => {
    if (this.inFlight) return this.inFlight;
    const attempt = this.readUntilCurrent();
    this.inFlight = attempt;
    /*
     * ONLY THE OWNER OF THE SLOT MAY CLEAR IT. The old code cleared `inFlight` in a `finally`
     * with no such check, so a read that outlived a `reset()` — which nulls the handle and lets
     * the next `load()` put its own there — cleared a handle belonging to a NEWER request, and
     * from then on concurrent callers each started a request of their own.
     */
    const release = (): void => { if (this.inFlight === attempt) this.inFlight = null; };
    attempt.then(release, release);
    return attempt;
  };

  /**
   * One read, repeated only while its answer keeps turning out to be older than something local.
   *
   * Every mutation below is guarded by the two counters described on the class. Nothing is
   * written on a discarded read — not the state, not `loadedAt`, not the watcher and not the
   * poll — because the only honest trace of a request made for a session that has ended is none.
   */
  private async readUntilCurrent(): Promise<FavouritesSnapshot> {
    for (let attempt = 0; attempt <= MAX_SUPERSEDED_REREADS; attempt += 1) {
      const session = this.session;
      const writes = this.writes;
      const hadData = this.state.data !== null;
      this.set(hadData ? { refreshing: true } : { status: 'loading', error: null });

      let snapshot: FavouritesSnapshot;
      try {
        snapshot = await favouritesApi.getFavourites();
      } catch (error) {
        // The failure path has the same hole as the success path and needs the same guard: an
        // older read's 503 must not put whoever is signed in NOW into an error state about a
        // request that was never theirs.
        if (this.session !== session) throw new DiscardedRead();
        this.set({
          status: 'error',
          error: getErrorMessage(error, 'Your saved teams, leagues and matches could not be loaded.'),
          refreshing: false,
        });
        throw error;
      }

      if (this.session !== session) throw new DiscardedRead();
      // Older than a local write. Discard it and read again rather than apply a snapshot that
      // predates the reader's own save or follow. Not solved by serialising reads behind writes,
      // which would make every star wait for a round trip it does not need.
      if (this.writes !== writes) continue;

      this.loadedAt = Date.now();
      this.set({ status: 'ready', data: snapshot, error: null, refreshing: false });
      // Only now is there something worth keeping current, and only now do we know whether
      // anything is in play or about to be.
      this.watchForReturns();
      this.syncLivePoll();
      return snapshot;
    }

    // Writes kept landing faster than the server could answer. Stop rather than spin: what we
    // hold optimistically is the newer of the two, and a tab return will reconcile it.
    this.set(this.state.data ? { refreshing: false } : { status: 'idle', refreshing: false });
    throw new DiscardedRead();
  }

  /** Load only if nothing has ever been loaded. Never throws: a caller mounting a widget on every
   *  page should not have to catch. The failure is still visible in `status` and `error`. */
  ensureLoaded = (): void => {
    if (this.state.status !== 'idle' || this.inFlight) return;
    void this.load().catch(() => undefined);
  };

  /** Drop everything, e.g. on sign-out. `idle` (not an empty snapshot) so the next reader reloads. */
  reset = (): void => {
    // FIRST, and this is the whole point: anything already on the wire now belongs to a session
    // that has ended, and `readUntilCurrent` will refuse to apply it. Dropping the handle below
    // stops the next caller sharing that request; it has never been able to cancel it.
    this.session += 1;
    this.inFlight = null;
    this.loadedAt = 0;
    // Signed out, there is nothing to keep current and nobody to keep it current for. Leaving the
    // listeners attached would have a signed-out tab re-requesting the previous user's favourites
    // every time it came back to the front, and every one of those would be a 401.
    this.stopWatchingReturns?.();
    this.stopWatchingReturns = null;
    this.stopLivePoll();
    this.stopKickoffWake();
    this.state = EMPTY_STATE;
    this.listeners.forEach(listener => listener());
  };

  /**
   * Record that a local write has changed what this store holds.
   *
   * Called on the optimistic change, on the reconciliation with the server's answer, and on a
   * rollback — all three change what we hold, and a read issued before any of them is older than
   * the store. The cost of being generous here is at most one extra stored read.
   */
  private noteLocalWrite(): void {
    this.writes += 1;
  }

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
    // away, so neither an interval nor a pending wake is left running behind a hidden tab.
    const onHidden = () => {
      if (tabIsVisible()) return;
      this.stopLivePoll();
      this.stopKickoffWake();
    };
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onHidden);
    // Turning live updates off, or pausing everything optional, has to stop the interval THEN —
    // not at the next tab switch. A pause a reader can still see working is not a pause.
    const stopWatchingPreferences = personalPreferencesStore.subscribe(() => this.syncLivePoll());
    this.stopWatchingReturns = () => {
      stopWake();
      stopWatchingPreferences();
      if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onHidden);
    };
  }

  /**
   * How often this store should be re-reading right now, or null for not at all.
   *
   * TWO REASONS TO BE READING, AND NOTHING ELSE IS ONE.
   *   a saved match IN PLAY            — its score changes; `LIVE_REFRESH_MS`.
   *   a saved match DUE TO KICK OFF    — its status is about to change once; `KICKOFF_REFRESH_MS`.
   *
   * The second is what was missing, and its absence is why an upcoming fixture never became a
   * live one while the tab stayed in front. It is not a general-purpose poller: a reader with
   * nothing saved, nothing saved for today, or nothing saved inside its kick-off window is
   * polled at no cadence at all, and every read on this path is one indexed query over that
   * reader's own rows that reaches no provider.
   *
   * The preference is checked here rather than at the call sites because this is the only place
   * the interval is created, and a background re-read the reader has switched off is exactly the
   * kind of optional behaviour a pause has to reach.
   */
  private pollPeriodMs(): number | null {
    if (typeof window === 'undefined' || !tabIsVisible()) return null;
    if (!personalPreferencesStore.isOn('liveUpdates')) return null;
    if ((this.state.data?.savedMatches.live.length ?? 0) > 0) return LIVE_REFRESH_MS;
    if (this.savedDueToStart() > 0) return KICKOFF_REFRESH_MS;
    return null;
  }

  /** Saved fixtures whose kick-off has arrived and which the record still says will be played. */
  private savedDueToStart(now: number = Date.now()): number {
    const upcoming = this.state.data?.savedMatches.upcoming ?? [];
    return upcoming.filter(entry => {
      // `upcoming` is everything that is neither live nor finished, postponed and cancelled
      // included. Those two are not about to kick off and must not be watched as if they were.
      if (entry.match.status !== 'scheduled') return false;
      const kickoff = kickoffTimeOf(entry);
      if (kickoff === null) return false;
      return now >= kickoff - KICKOFF_WATCH_LEAD_MS && now <= kickoff + KICKOFF_WATCH_GRACE_MS;
    }).length;
  }

  /** When the next saved fixture starts being worth watching, or null when none does. */
  private nextKickoffWatchAt(now: number = Date.now()): number | null {
    const upcoming = this.state.data?.savedMatches.upcoming ?? [];
    let soonest: number | null = null;
    upcoming.forEach(entry => {
      if (entry.match.status !== 'scheduled') return;
      const kickoff = kickoffTimeOf(entry);
      if (kickoff === null) return;
      const from = kickoff - KICKOFF_WATCH_LEAD_MS;
      // Already inside its window: the interval has it, and a wake for a moment in the past
      // would fire in a tight loop.
      if (from <= now) return;
      if (soonest === null || from < soonest) soonest = from;
    });
    return soonest;
  }

  /**
   * Start, stop or re-pitch the poll, and arm the wake for the next kick-off.
   *
   * Both halves are decided here so they cannot disagree, and both are re-evaluated on every
   * load, every tab return and every change of preference.
   */
  private syncLivePoll(): void {
    const period = this.pollPeriodMs();
    if (period === null) {
      this.stopLivePoll();
    } else if (this.livePoll === null || this.livePollPeriodMs !== period) {
      // A fixture that kicks off moves from the kick-off cadence to the in-play one; the
      // interval is recreated rather than left running at the wrong pitch.
      this.stopLivePoll();
      this.livePollPeriodMs = period;
      this.livePoll = setInterval(() => {
        if (!tabIsVisible()) return;
        this.refreshIfStale(period - 1_000);
      }, period);
    }
    this.scheduleKickoffWake();
  }

  /**
   * Wake up when the next saved fixture is about to start — and only then.
   *
   * This is what stops the kick-off watch being a poller. Between now and that moment nothing is
   * requested at all; the timer costs nothing and holds no connection. When it fires, the store
   * reads once immediately (rather than waiting out a first full interval) and lets
   * `syncLivePoll` decide whether there is now a reason to keep reading.
   */
  private scheduleKickoffWake(): void {
    this.stopKickoffWake();
    if (typeof window === 'undefined' || !tabIsVisible()) return;
    if (!personalPreferencesStore.isOn('liveUpdates')) return;
    const from = this.nextKickoffWatchAt();
    if (from === null) return;
    const delay = Math.min(Math.max(from - Date.now(), 250), KICKOFF_WAKE_MAX_MS);
    this.kickoffWake = setTimeout(() => {
      this.kickoffWake = null;
      // A clamped wake finds nothing due and simply re-arms below; a real one reads.
      if (this.savedDueToStart() > 0) this.refreshIfStale(FOCUS_REFRESH_MIN_AGE_MS);
      this.syncLivePoll();
    }, delay);
  }

  private stopKickoffWake(): void {
    if (this.kickoffWake === null) return;
    clearTimeout(this.kickoffWake);
    this.kickoffWake = null;
  }

  private stopLivePoll(): void {
    if (this.livePoll === null) return;
    clearInterval(this.livePoll);
    this.livePoll = null;
    this.livePollPeriodMs = 0;
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
      this.noteLocalWrite();
      this.set({
        data: optimistic,
        ...(kind === 'team'
          ? { pendingTeamIds: withId(before.pendingTeamIds, id) }
          : { pendingLeagueIds: withId(before.pendingLeagueIds, id) }),
      });
    } else {
      this.noteLocalWrite();
      this.set(kind === 'team'
        ? { pendingTeamIds: withId(before.pendingTeamIds, id) }
        : { pendingLeagueIds: withId(before.pendingLeagueIds, id) });
    }

    try {
      const result = await favouritesApi.follow(kind, id, following);
      const current = this.state.data;
      // The reconciliation is a second local write: a read issued between the optimistic change
      // and this line is older than the server's own answer too.
      this.noteLocalWrite();
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
      this.noteLocalWrite();
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
      this.noteLocalWrite();
      this.set({
        data: { ...before.data, savedMatches: insertSaved(before.data.savedMatches, optimisticEntry) },
        pendingMatchIds: withId(before.pendingMatchIds, matchId),
      });
    } else {
      this.noteLocalWrite();
      this.set({ pendingMatchIds: withId(before.pendingMatchIds, matchId) });
    }

    try {
      const result = await favouritesApi.saveMatch(matchId, options?.note);
      const current = this.state.data;
      this.noteLocalWrite();
      this.set({
        // Replace the optimistic entry with the server's, which carries the real saved_at and the
        // fixture exactly as every other endpoint serialises it.
        data: current ? { ...current, savedMatches: insertSaved(current.savedMatches, result) } : current,
        pendingMatchIds: without(this.state.pendingMatchIds, matchId),
      });
      // Saving a fixture that is in play, or one that kicks off in ten minutes, is a reason to
      // start watching that did not exist a moment ago.
      this.syncLivePoll();
      return result;
    } catch (error) {
      this.noteLocalWrite();
      this.set({ data: before.data, pendingMatchIds: without(this.state.pendingMatchIds, matchId) });
      throw error;
    }
  };

  /** Unsave a match, optimistically. Unsaving something that was not saved is not an error. */
  unsaveMatch = async (matchId: string): Promise<UnsaveMatchResult> => {
    const before = this.state;
    this.noteLocalWrite();
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
      this.noteLocalWrite();
      this.set({ pendingMatchIds: without(this.state.pendingMatchIds, matchId) });
      // The fixture that was being watched may be the one just removed.
      this.syncLivePoll();
      return result;
    } catch (error) {
      this.noteLocalWrite();
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
    // Same reason as in FavouritesStore: a pause has to stop this fan-out the moment it is asked
    // for, and this one costs a request per follow per minute.
    const stopWatchingPreferences = personalPreferencesStore.subscribe(() => this.syncLivePoll());
    this.detach = () => {
      stopWake();
      stopFollowing();
      stopWatchingPreferences();
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
   *
   * KNOWN, AND DELIBERATELY NOT CLOSED HERE. This is still gated on the state it would discover:
   * a fixture reached only through a FOLLOW that kicks off while the reader watches is not
   * noticed until they return to the tab. `FavouritesStore` now has a kick-off watch for exactly
   * this (see `savedDueToStart`), and it is affordable there because one read answers for the
   * whole reader. The same watch here is one request PER FOLLOW — up to fifteen — repeated for
   * as long as a kick-off is pending, and that is a different order of load on the backend for a
   * fixture the reader did not ask for by name. A saved fixture, which is the one they did ask
   * for, is covered. Closing this properly wants the single `GET /api/v1/me/feed` already
   * written up for the backend's owner above, not fifteen requests a minute from here.
   */
  private syncLivePoll(): void {
    const inPlay = this.state.fixtures.some(entry => (
      entry.match.status === 'live' || entry.match.status === 'halftime'
    ));
    const shouldPoll = inPlay && this.listeners.size > 0 && tabIsVisible()
      && typeof window !== 'undefined' && personalPreferencesStore.isOn('liveUpdates');
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
        // Let go of the fan-out that is still running: it belongs to the session that has just
        // ended, `load()` will refuse to apply it, and holding the handle would make the next
        // session's first `load()` return this one's promise instead of starting its own.
        this.inFlight = null;
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
  load = (): Promise<void> => {
    if (this.inFlight) return this.inFlight;
    const snapshot = favouritesStore.getState().data;
    if (!snapshot) return Promise.resolve();

    /*
     * WHOSE FEED THIS IS. The same hole as in `FavouritesStore.load`, and worse here: this is one
     * request PER FOLLOW, so it is in flight for far longer and far more likely to still be
     * running when a reader signs out or somebody else signs in. Captured when the fan-out is
     * issued and checked before anything is written, so an answer built for a session that has
     * ended is dropped rather than shown to whoever is here now.
     */
    const session = favouritesStore.sessionId();
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
      return Promise.resolve();
    }

    this.set(this.state.status === 'ready'
      ? { refreshing: true }
      : { status: 'loading', refreshing: true, error: null });
    const run = (async () => {
      const settled = await mapWithLimit(follows, FEED_CONCURRENCY, follow => (
        follow.kind === 'team' ? feedApi.teamFixtures(follow.id) : feedApi.leagueFixtures(follow.id)
      ));
      // Discarded whole: no fixtures, no `unreadable`, no `builtFrom`, no `loadedAt`, no poll.
      if (favouritesStore.sessionId() !== session) return;

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

    const settle: Promise<void> = run.finally(() => {
      // Only the owner of the slot may clear it: `onFavouritesChanged` drops the handle on a
      // sign-out, and by now it may belong to the next session's fan-out.
      if (this.inFlight === settle) this.inFlight = null;
      // Nothing of this load belongs to the session that is current now, so there is nothing of
      // ours to tidy up in it either.
      if (favouritesStore.sessionId() !== session) return;
      // Belt and braces: nothing in `run` throws today, but a load that ended without clearing
      // this would leave every Retry control disabled for the rest of the session.
      if (this.state.refreshing) this.set({ refreshing: false });
      // A follow changed WHILE this load was running. The notification that would have rebuilt
      // the feed was swallowed by the in-flight guard, so without this the newly followed team's
      // fixtures would never appear — the exact failure the guard exists to avoid causing.
      if (followKey(favouritesStore.getState().data) !== this.builtFrom) void this.load();
    });
    this.inFlight = settle;
    return settle;
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
