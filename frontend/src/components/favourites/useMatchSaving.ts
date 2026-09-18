/**
 * Wiring between a list of fixtures and the shared favourites store.
 *
 * Every page that shows fixtures needs the same four things to drive `FixtureRow`'s save control:
 * whether this match is saved, whether a write is in flight, what to do when the control is used,
 * and what to do when nobody is signed in. Repeating that in four pages is how the star on one
 * page ends up disagreeing with the star on another, so it lives here once and reads from the one
 * store (src/services/favourites.service.ts).
 *
 * WHAT THIS DOES NOT DO
 *  - It does not swallow a failure. `favouritesStore` restores the exact previous state and
 *    rethrows; this reports the server's own message to the reader. A star that stays filled after
 *    a failed save is a lie about what the server holds.
 *  - It does not save anything for a signed-out visitor. There is nowhere to put it: saves are
 *    per-user rows behind authentication. The visitor is sent to sign in, and nothing is stashed
 *    in the browser pretending to be a save that would then vanish.
 *  - Saving is not a bet and nothing here stakes, scores or settles anything.
 */

import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import type { Match } from '@/types';
import useFavourites from '@/hooks/useFavourites';
import { getErrorMessage } from '@/utils/errors';

export interface MatchSaving {
  /** A user is signed in. False renders the save control as a sign-in invitation. */
  signedIn: boolean;
  /**
   * The last favourites load failed, so "not saved" below means "we do not know", not "no".
   * Show it next to the list rather than letting an unfilled star assert something false.
   */
  failed: boolean;
  /** The server's own wording for that failure, when there is one. */
  error: string | null;
  isSaved: (matchId: string) => boolean;
  isPending: (matchId: string) => boolean;
  /**
   * Handle the save control. `match` lets the store show the fixture immediately in the saved
   * lists; without it the entry only appears once the server's copy comes back.
   */
  toggleSave: (matchId: string, next: boolean, match?: Match) => void;
  /** Send a signed-out visitor to sign in, remembering where they were. */
  requireSignIn: () => void;
}

export function useMatchSaving(): MatchSaving {
  const { signedIn, failed, error, isMatchSaved, isMatchPending, setMatchSaved } = useFavourites();
  const navigate = useNavigate();
  const location = useLocation();

  const requireSignIn = useCallback(() => {
    // Saving needs an account. Say so, then go to the sign-in form carrying where we came from —
    // the same `state.from` shape ProtectedRoute uses, so one place can learn to honour it.
    toast('Sign in to save matches to your dashboard.');
    navigate('/login', { state: { from: location } });
  }, [navigate, location]);

  const toggleSave = useCallback((matchId: string, next: boolean, match?: Match) => {
    void setMatchSaved(matchId, next, match ? { match } : undefined).catch((err: unknown) => {
      toast.error(getErrorMessage(err, next
        ? 'That match could not be saved. Nothing was changed.'
        : 'That match could not be removed. Nothing was changed.'));
    });
  }, [setMatchSaved]);

  return {
    signedIn,
    failed,
    error,
    isSaved: isMatchSaved,
    isPending: isMatchPending,
    toggleSave,
    requireSignIn,
  };
}

export default useMatchSaving;
