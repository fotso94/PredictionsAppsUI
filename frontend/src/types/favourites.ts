/**
 * Followed teams and leagues, and saved matches.
 *
 * Backed by /api/v1/me/favourites and /api/v1/me/saved-matches (both require a signed-in user and
 * both read stored data only — no provider request is ever made to answer them).
 *
 * The one distinction these types exist to protect: "you follow nothing" and "we could not find
 * out what you follow" are different statements. `FavouritesState.data` stays null until a load
 * has actually succeeded, so a failure can never be rendered as an empty list. The same mistake
 * was already made once in search.service.ts, where a swallowed network error made the dropdown
 * announce "No results found" for a search that had never run.
 */

import type { League, Match, Team } from './index';

/** One saved fixture: the fixture itself plus this user's own private data about it. */
export interface SavedMatch {
  /** Internal match UUID. Also `match.id`; kept separately because it is the key the API uses. */
  matchId: string;
  /** Private to the owner of the save. Never visible to anybody else. */
  note: string | null;
  /** When the match was saved (UTC ISO-8601). */
  savedAt: string | null;
  /** When the note was last changed (UTC ISO-8601). */
  updatedAt: string | null;
  /** The same fixture payload every other match endpoint returns, mapped to the UI `Match` type. */
  match: Match;
}

/** How many of each kind the API returned, as the API counted them. */
export interface SavedMatchCounts {
  upcoming: number;
  live: number;
  finished: number;
  total: number;
}

/**
 * Saved matches split by state.
 *
 * `live` is in play now and `finished` has been played; `upcoming` is EVERYTHING ELSE, so a
 * postponed or cancelled fixture stays in `upcoming` carrying its real status in `match.status`
 * rather than being misreported as finished. `upcoming` and `live` run earliest kickoff first,
 * `finished` most recent first.
 */
export interface SavedMatchesSnapshot {
  upcoming: SavedMatch[];
  live: SavedMatch[];
  finished: SavedMatch[];
  counts: SavedMatchCounts;
}

/**
 * Followed ids that no longer match a row we hold.
 *
 * Reported rather than dropped: "we are following something we cannot show you" is a different
 * statement from "you follow nothing", and only the UI can decide how to say it.
 */
export interface UnresolvedFavourites {
  teams: string[];
  leagues: string[];
}

/** How many teams and leagues a user may follow. Comes from the API; never hard-coded in a page. */
export interface FavouriteLimits {
  teams: number;
  leagues: number;
}

/** Everything the personal dashboard needs, from one stored-data-only read. */
export interface FavouritesSnapshot {
  /** Followed teams that resolved to a row we hold, in the order they were added. */
  teams: Team[];
  /** Followed leagues that resolved to a row we hold, in the order they were added. */
  leagues: League[];
  /** Exactly what is stored, unresolved ids included. Use this for "is this followed?" checks. */
  teamIds: string[];
  leagueIds: string[];
  unresolved: UnresolvedFavourites;
  savedMatches: SavedMatchesSnapshot;
  limits: FavouriteLimits;
}

/** Result of following or unfollowing. `changed` is false when the call was already a no-op. */
export interface FollowResult {
  kind: 'team' | 'league';
  id: string;
  /** State AFTER the call. */
  following: boolean;
  changed: boolean;
  /** The full followed list after the call, as the server holds it. */
  ids: string[];
  limit: number;
}

/** Result of saving a match. `created` is false when it was already saved. */
export interface SaveMatchResult extends SavedMatch {
  created: boolean;
}

/** Result of unsaving. `removed` is false when there was nothing to remove; that is not an error. */
export interface UnsaveMatchResult {
  matchId: string;
  removed: boolean;
}

/**
 * Lifecycle of the favourites store.
 *  - `idle`    nothing has been requested yet.
 *  - `loading` the first load is running; there is no data to show.
 *  - `ready`   `data` is a snapshot that really came from the server.
 *  - `error`   the load failed. `data` is whatever we last held, or null — never an empty snapshot
 *              standing in for the failure.
 */
export type FavouritesStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface FavouritesState {
  status: FavouritesStatus;
  /**
   * Null until a load has SUCCEEDED at least once. A caller that renders `data?.teams ?? []` as
   * "you follow no teams" must check `status` first: on `error` that empty array is a failure,
   * not an answer.
   */
  data: FavouritesSnapshot | null;
  /** The server's own wording where it gave one. Null whenever `status` is not 'error'. */
  error: string | null;
  /** True while a reload runs over data we already hold, so the UI can stay on screen. */
  refreshing: boolean;
  /** Ids with a write in flight, so one pending control does not disable the others. */
  pendingTeamIds: string[];
  pendingLeagueIds: string[];
  pendingMatchIds: string[];
}
