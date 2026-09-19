/**
 * React access to the shared favourites store (src/services/favourites.service.ts).
 *
 * One store, many subscribers: the star on a fixture row, the star on the match page and the
 * personal dashboard all read the same state, so they cannot disagree about what is followed.
 *
 * The hook deliberately does NOT flatten `status` into a boolean. A component that renders
 * `teams.length === 0` as "you follow no teams" must first check `failed`, because on a failed load
 * that empty array means "we do not know", not "none".
 */

import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import favouritesStore from '@/services/favourites.service';
import type {
  FavouritesSnapshot, FavouritesState, FollowResult, SavedMatch, SavedMatchesSnapshot,
  SaveMatchResult, UnsaveMatchResult,
} from '@/types';
import useAuth from './useAuth';

export interface UseFavouritesOptions {
  /**
   * Load on mount when signed in and nothing has been loaded yet. Default true.
   * Set false for a control that should only reflect state somebody else loaded.
   */
  autoLoad?: boolean;
}

export interface UseFavouritesResult extends FavouritesState {
  /** True while the first load is running and there is nothing to show yet. */
  loading: boolean;
  /**
   * True when the last load failed. Check this BEFORE reading any list as "empty": on a failure
   * the lists are whatever we last held (often nothing), which is not an answer about this user.
   */
  failed: boolean;
  /** True when a real snapshot has been received at least once. */
  loaded: boolean;
  /** Whether a user is signed in at all. Favourites are per-user and need authentication. */
  signedIn: boolean;
  /** Saved matches, or empty buckets when nothing has loaded. Pair every read with `failed`. */
  savedMatches: SavedMatchesSnapshot;
  isTeamFollowed: (teamId: string) => boolean;
  isLeagueFollowed: (leagueId: string) => boolean;
  isMatchSaved: (matchId: string) => boolean;
  savedEntry: (matchId: string) => SavedMatch | null;
  /** True while a write for this id is in flight. */
  isTeamPending: (teamId: string) => boolean;
  isLeaguePending: (leagueId: string) => boolean;
  isMatchPending: (matchId: string) => boolean;
  /** Every write rejects on failure after restoring the previous state — always handle the rejection. */
  setTeamFollowed: (teamId: string, following: boolean) => Promise<FollowResult>;
  setLeagueFollowed: (leagueId: string, following: boolean) => Promise<FollowResult>;
  saveMatch: (matchId: string, options?: { note?: string | null; match?: SavedMatch['match'] }) => Promise<SaveMatchResult>;
  unsaveMatch: (matchId: string) => Promise<UnsaveMatchResult>;
  setMatchSaved: (matchId: string, saved: boolean, options?: { note?: string | null; match?: SavedMatch['match'] }) => Promise<SaveMatchResult | UnsaveMatchResult>;
  /** Force a reload. Rejects on failure; the store's `error` is set either way. */
  reload: () => Promise<FavouritesSnapshot>;
}

const EMPTY_SAVED: SavedMatchesSnapshot = {
  upcoming: [], live: [], finished: [], counts: { upcoming: 0, live: 0, finished: 0, total: 0 },
};

export function useFavourites(options: UseFavouritesOptions = {}): UseFavouritesResult {
  const { autoLoad = true } = options;
  const { isAuthenticated, user } = useAuth();
  const state = useSyncExternalStore(favouritesStore.subscribe, favouritesStore.getState, favouritesStore.getState);

  /**
   * WHO the store is holding favourites for.
   *
   * The id where there is one; otherwise the address, and failing both a constant. The fallbacks
   * matter: `bindAccount(null)` means SIGNED OUT, so handing it an accidental null for a signed-in
   * reader whose payload was thin would leave the store reset and never loaded. Signed-out is
   * decided by `isAuthenticated` below and nothing else.
   */
  const accountKey = user?.id || user?.email || 'signed-in';

  useEffect(() => {
    /*
     * IDENTITY FIRST, on every change of it.
     *
     * `bindAccount` is what tells the store that a response already on the wire belongs to
     * somebody who is no longer here — a reader who signed out, or one who has been replaced by
     * another account on this machine. It resets the store (back to `idle`, not to an empty
     * snapshot, so nothing reads as "this user follows nothing") and invalidates the in-flight
     * read, which `reset()` alone could never do.
     *
     * An ACCOUNT CHANGE is a distinct event from a sign-out and the one that can put one
     * person's saved matches in front of another; both arrive here as a changed key.
     */
    favouritesStore.bindAccount(isAuthenticated ? accountKey : null);
    if (!isAuthenticated) return;
    if (autoLoad) favouritesStore.ensureLoaded();
  }, [isAuthenticated, accountKey, autoLoad]);

  const isTeamFollowed = useCallback((teamId: string) => Boolean(state.data?.teamIds.includes(teamId)), [state.data]);
  const isLeagueFollowed = useCallback((leagueId: string) => Boolean(state.data?.leagueIds.includes(leagueId)), [state.data]);

  const savedMatches = state.data?.savedMatches ?? EMPTY_SAVED;
  const savedIds = useMemo(
    () => new Set([...savedMatches.upcoming, ...savedMatches.live, ...savedMatches.finished].map(entry => entry.matchId)),
    [savedMatches],
  );
  const isMatchSaved = useCallback((matchId: string) => savedIds.has(matchId), [savedIds]);
  const savedEntry = useCallback((matchId: string) => favouritesStore.savedEntry(matchId), []);

  const isTeamPending = useCallback((teamId: string) => state.pendingTeamIds.includes(teamId), [state.pendingTeamIds]);
  const isLeaguePending = useCallback((leagueId: string) => state.pendingLeagueIds.includes(leagueId), [state.pendingLeagueIds]);
  const isMatchPending = useCallback((matchId: string) => state.pendingMatchIds.includes(matchId), [state.pendingMatchIds]);

  return {
    ...state,
    loading: state.status === 'loading',
    failed: state.status === 'error',
    loaded: state.data !== null,
    signedIn: isAuthenticated,
    savedMatches,
    isTeamFollowed,
    isLeagueFollowed,
    isMatchSaved,
    savedEntry,
    isTeamPending,
    isLeaguePending,
    isMatchPending,
    setTeamFollowed: favouritesStore.setTeamFollowed,
    setLeagueFollowed: favouritesStore.setLeagueFollowed,
    saveMatch: favouritesStore.saveMatch,
    unsaveMatch: favouritesStore.unsaveMatch,
    setMatchSaved: favouritesStore.setMatchSaved,
    reload: favouritesStore.load,
  };
}

export default useFavourites;
