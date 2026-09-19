/**
 * Wiring between a list of fixtures and the shared favourites store, and the sign-in handoff that
 * lets an interrupted save finish itself.
 *
 * Every page that shows fixtures needs the same four things to drive `FixtureRow`'s save control:
 * whether this match is saved, whether a write is in flight, what to do when the control is used,
 * and what to do when nobody is signed in. Repeating that in four pages is how the star on one
 * page ends up disagreeing with the star on another, so it lives here once and reads from the one
 * store (src/services/favourites.service.ts).
 *
 * THE SIGN-IN HANDOFF. Pressing save while signed out used to end the journey: the visitor was
 * sent to /login, the form ignored where they came from, and they landed on a role dashboard with
 * their date and filters gone and the match still unsaved. The handoff below is the whole
 * contract, in one module because a producer and a consumer of the same navigation state must not
 * drift apart:
 *
 *   producers  `requireSignIn()` here, and `ProtectedRoute`, write `{ from, save?, at }` into the
 *              router's navigation state.
 *   consumers  `LoginPage` and `RegisterPage` read it back through `safeReturnPath()` and
 *              `useResumeSave()`.
 *
 * Every entry point to a save uses those two functions and nothing else. The star in the fixture
 * list and the control on the match page are the same journey with the same guarantees; when the
 * list had a handoff of its own that carried only `from`, its visitors signed in, landed back on
 * the right list, and found the match still unsaved.
 *
 * WHY THE ROUTER'S STATE AND NOT STORAGE. Navigation state lives on the one history entry that the
 * save control pushed. It is never written to localStorage or sessionStorage, so there is no
 * record of an intent left lying around for a later page, a later tab or a later day to act on —
 * the failure being avoided is a match quietly appearing in someone's saved list because they
 * pressed a star last week and signed in today. A timestamp is carried as well, because a browser
 * can restore a whole window (history state included) long afterwards; an intent past
 * SAVE_INTENT_TTL_MS is dropped rather than honoured.
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

/** The save a visitor had asked for when they were sent to sign in. */
export interface SaveIntent {
  matchId: string;
  /** For the sentence shown when the save resumes — e.g. "Bayern Munich versus Union Berlin". */
  label?: string;
}

/** The navigation state carried to /login and /register. Every field is optional and untrusted. */
export interface SignInHandoff {
  /** Where the visitor was: a router `Location`, or a path string. Validated before use. */
  from?: unknown;
  /** The save that was interrupted. Absent unless a save control is what sent them here. */
  save?: SaveIntent;
  /** When the handoff was created, epoch ms. */
  at?: number;
}

/**
 * How long an interrupted save stays honourable.
 *
 * Ten minutes is a sign-in, a forgotten password and a second attempt. It is not long enough for a
 * restored browser window to resume something the visitor has forgotten asking for.
 */
export const SAVE_INTENT_TTL_MS = 10 * 60 * 1000;

/** Tolerance for a clock that is slightly ahead. A timestamp further in the future is not evidence. */
const FUTURE_SKEW_MS = 60 * 1000;

/**
 * Screens that must never be a return destination: sending someone back to the form they have just
 * completed is a loop, not a return.
 */
const AUTH_PATHS = new Set(['/login', '/register', '/forgot-password', '/reset-password']);

/**
 * A newline or a NUL smuggled into a redirect target defeats naive prefix checks, and some parsers
 * strip them before resolving. Written as a scan rather than a regular expression because a
 * character class of control characters is itself what `no-control-regex` exists to catch.
 */
function hasControlCharacter(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code < 0x20 || code === 0x7f) return true;
  }
  return false;
}

/** Ids come from the API as UUIDs; the bound and the alphabet keep a hostile value out of a URL. */
const MATCH_ID_PATTERN = /^[A-Za-z0-9:_-]{1,128}$/;

/** Longest return path accepted. Well past any real route, short of a denial-of-service string. */
const MAX_PATH_LENGTH = 2048;

/** A router `Location`, a path string, or something that is neither. */
function candidatePath(from: unknown): string | null {
  if (typeof from === 'string') return from;
  if (from !== null && typeof from === 'object') {
    const location = from as { pathname?: unknown; search?: unknown; hash?: unknown };
    if (typeof location.pathname !== 'string') return null;
    const search = typeof location.search === 'string' ? location.search : '';
    const hash = typeof location.hash === 'string' ? location.hash : '';
    return `${location.pathname}${search}${hash}`;
  }
  return null;
}

/**
 * The internal path this handoff asks to return to, or null.
 *
 * A return destination is attacker-controllable — any page can push navigation state, and this
 * value decides where a just-authenticated visitor is sent — so it is an allow-list, not a
 * block-list. ACCEPTED: a path on this application, beginning with a single "/", optionally with a
 * query string and a fragment. REJECTED, every one of them tested in
 * e2e/live/save-journey.spec.ts: an absolute URL ("https://evil.example/x"), a protocol-relative
 * URL ("//evil.example"), a backslash variant that some parsers fold into one ("/\evil.example"),
 * a "javascript:" or "data:" URL, anything carrying a control character, anything longer than
 * MAX_PATH_LENGTH, anything that resolves to another origin, and the authentication screens
 * themselves.
 */
export function safeReturnPath(state: unknown): string | null {
  const handoff = (state ?? null) as SignInHandoff | null;
  const candidate = candidatePath(handoff?.from);
  if (candidate === null) return null;

  if (candidate.length === 0 || candidate.length > MAX_PATH_LENGTH) return null;
  if (hasControlCharacter(candidate)) return null;
  // No route here contains one, and "/\evil.example" is read as protocol-relative by the URL
  // parser, so the whole character goes.
  if (candidate.includes('\\')) return null;
  if (!candidate.startsWith('/')) return null;
  if (candidate.startsWith('//')) return null;

  // The parser has the last word: it normalises "/a/../b", resolves anything exotic left above,
  // and settles the only question that matters — does this stay on our origin?
  let resolved: URL;
  try {
    resolved = new URL(candidate, window.location.origin);
  } catch {
    return null;
  }
  if (resolved.origin !== window.location.origin) return null;
  if (AUTH_PATHS.has(resolved.pathname.toLowerCase())) return null;

  const path = `${resolved.pathname}${resolved.search}${resolved.hash}`;

  // CHECK WHAT WE RETURN, NOT ONLY WHAT WE WERE GIVEN. The parser removes dot segments, and it
  // does so AFTER the "//" test above: "/..//evil.example/steal" arrives here as the pathname
  // "//evil.example/steal". It passed the origin test — resolved against our own origin, a
  // leading ".." has nowhere to climb to — but the string handed back is protocol-relative, and
  // the router resolves it a SECOND time against the document. `history.pushState` then refuses
  // it as cross-origin and throws, which in the already-authenticated branch is an exception
  // inside <Navigate>: the sign-in page unmounts into a blank screen and the visitor is stranded.
  // The browser's own same-origin check is what stops the redirect; this stops the crash, and
  // keeps the promise this function's contract makes about its return value.
  if (path.startsWith('//')) return null;

  return path;
}

/**
 * The save this handoff asks to finish, or null.
 *
 * Null for anything that is not a fresh, well-formed intent: no `save`, an id that is not an id, a
 * missing or unreadable timestamp, a timestamp from the future, or one older than
 * SAVE_INTENT_TTL_MS. `now` is injectable so the expiry can be tested without waiting.
 */
export function pendingSaveIntent(state: unknown, now: number = Date.now()): SaveIntent | null {
  const handoff = (state ?? null) as SignInHandoff | null;
  const save = handoff?.save;
  if (!save || typeof save !== 'object') return null;

  const matchId = (save as SaveIntent).matchId;
  if (typeof matchId !== 'string' || !MATCH_ID_PATTERN.test(matchId)) return null;

  const at = handoff?.at;
  if (typeof at !== 'number' || !Number.isFinite(at)) return null;
  if (at > now + FUTURE_SKEW_MS) return null;
  if (now - at > SAVE_INTENT_TTL_MS) return null;

  const label = typeof save.label === 'string' && save.label.length > 0 ? save.label : undefined;
  return { matchId, label };
}

/**
 * THE LIST A FIXTURE WAS OPENED FROM, carried in the fixture page's own query string.
 *
 * The match page offers a way back to the results. Ordinarily that is a real history Back, which
 * restores the list exactly — same date, same filters, same scroll position — because the
 * workspace keeps all of it in the URL. There is one journey where Back is not available: the
 * reader saved while signed out, and the sign-in form replaced its own history entry on the way
 * back, so the entry behind the fixture is no longer the list. Until now the control fell back to
 * `/matches?date=<the fixture's day>`, which is the right day and none of the reader's filters —
 * a 23-row list where they had chosen one competition.
 *
 * WHY THE QUERY STRING AND NOT NAVIGATION STATE. The sign-in round trip already preserves the
 * full path AND query of where the visitor was (`safeReturnPath` above returns
 * `pathname + search + hash`, and both sign-in forms navigate back to exactly that). A value in
 * the fixture URL therefore survives the round trip with no extra plumbing, survives a reload and
 * a restored tab, and works the same whether the visitor signed in or registered. Navigation
 * state would have had to be re-attached by every screen in the chain, and the one that dropped
 * it would be the one nobody noticed.
 *
 * IT IS READ BACK THROUGH THE SAME ALLOW-LIST as a sign-in return destination, because it is the
 * same kind of value: an attacker-controllable string that decides where a link goes. Anything
 * off this origin, any auth screen, any control character — refused, and the reader gets the
 * honest day-list fallback instead.
 */
export const RESULTS_LIST_PARAM = 'from';

/** A location's path and query, which is all either half of this needs. */
interface PathAndQuery {
  pathname: string;
  search: string;
}

/**
 * A fixture link that remembers the list it is being opened from.
 *
 * Adds nothing when the list carries no query of its own: the fixture page's own fallback already
 * reaches an unfiltered day list, so the parameter would be noise in a URL people paste.
 */
export function fixtureHrefFrom(matchId: string, list: PathAndQuery): string {
  const base = `/match/${matchId}`;
  if (!list.search || list.search === '?') return base;
  const here = `${list.pathname}${list.search}`;
  return `${base}?${RESULTS_LIST_PARAM}=${encodeURIComponent(here)}`;
}

/**
 * The routes that actually show a list of fixtures. Nothing else is a "result".
 *
 * All four render the SAME workspace (src/components/matches/MatchdayWorkspace.tsx, through
 * MatchesPage and the home page), so all four are lists a reader can narrow and then open a
 * fixture from. `/predictions/today` and `/predictions/tomorrow` are the preset days: they keep
 * the reader's competition and market filters in their own query string exactly as `/matches`
 * does (MatchdayWorkspace only switches to `/matches` when the chosen date leaves the preset
 * day), and they are linked from the footer, the saved-matches panel and the following panel.
 *
 * MEASURED when they were missing from this set: a reader on
 * `/predictions/today?comp=<Premier League>` — a five-row list — opened a fixture, saved while
 * signed out, signed in, came back, and "Back to results" had degraded to
 * "All matches on Sat 19 Sept", landing on the unfiltered 23-row day. That is the same defect
 * this parameter exists to close, at a different entry point; the fixture link had recorded the
 * preset list correctly and this allow-list was throwing it away.
 *
 * Widening it costs nothing the restriction was protecting: every entry here is a fixture list on
 * this origin, so the control's label still cannot be pointed at a page that is not results.
 */
const RESULTS_PATHS = new Set(['/', '/matches', '/predictions/today', '/predictions/tomorrow']);

/** The list a fixture page was opened from, or null when there is not a usable one. */
export function resultsListFrom(search: string): string | null {
  const raw = new URLSearchParams(search).get(RESULTS_LIST_PARAM);
  if (raw === null) return null;
  const path = safeReturnPath({ from: raw });
  if (path === null) return null;

  // The control that uses this says "Back to results". A link somebody else composed must not be
  // able to point that sentence at a page which is not a list of results — the control would be
  // promising a destination it does not reach, which is the one thing it has always refused to
  // do. Anything else falls back to the honest day list.
  const pathname = (path.split(/[?#]/)[0] ?? '').replace(/\/+$/, '') || '/';
  return RESULTS_PATHS.has(pathname) ? path : null;
}

/**
 * Navigation state put on the destination when a sign-in hands the visitor back.
 *
 * It exists so a page can tell "you walked here" from "you were returned here". The difference
 * matters for any control offering to go back: the entry behind this one is the sign-in form,
 * which immediately redirects an authenticated visitor forward again, so a Back that looks like it
 * returns to the list would instead appear to do nothing at all.
 */
export interface ReturnedFromSignIn {
  resumedFromSignIn?: boolean;
}

export function arrivedFromSignIn(state: unknown): boolean {
  return ((state ?? null) as ReturnedFromSignIn | null)?.resumedFromSignIn === true;
}

/**
 * Finish the save a visitor started before they signed in.
 *
 * Call it once, immediately after a successful sign-in, with the navigation state that brought
 * them to the form. It saves nothing when there is no intent, and it never rejects: a failed save
 * is reported to the visitor, not thrown at the sign-in handler, which has already succeeded.
 *
 * The favourites store is not asked to load here (`autoLoad: false`): the write goes straight to
 * the API with the token the sign-in has just stored, and the page the visitor lands on loads the
 * list for itself. Loading here as well would be a second request for the same answer.
 */
export function useResumeSave(): (state: unknown) => Promise<void> {
  const { setMatchSaved } = useFavourites({ autoLoad: false });

  return useCallback(async (state: unknown) => {
    const intent = pendingSaveIntent(state);
    if (!intent) return;
    const subject = intent.label ?? 'That match';
    try {
      await setMatchSaved(intent.matchId, true);
      toast.success(`${subject} is saved to your dashboard.`);
    } catch (err: unknown) {
      // Say it did not happen. Signing in is not the same event as saving, and the visitor has to
      // know which of the two worked.
      toast.error(getErrorMessage(err, `${subject} could not be saved. Nothing was changed.`));
    }
  }, [setMatchSaved]);
}

export interface MatchSavingOptions {
  /**
   * Report a failed write with a toast. Default true.
   *
   * Turn it off where the caller shows the failure beside the control itself: two copies of one
   * sentence is noise, and a toast that has already faded cannot answer "did that save work?".
   * `toggleSave` returns the message either way.
   */
  toastErrors?: boolean;
}

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
   *
   * Resolves to null when the write landed, or to the message explaining why it did not. It never
   * rejects, so a caller that ignores the result still cannot leave an unhandled rejection behind.
   */
  toggleSave: (matchId: string, next: boolean, match?: Match) => Promise<string | null>;
  /**
   * Send a signed-out visitor to sign in, remembering where they were — and, when `intent` names
   * the match they were saving, that the save should finish itself once they are back.
   */
  requireSignIn: (intent?: SaveIntent) => void;
}

export function useMatchSaving(options: MatchSavingOptions = {}): MatchSaving {
  const { toastErrors = true } = options;
  const { signedIn, failed, error, isMatchSaved, isMatchPending, setMatchSaved } = useFavourites();
  const navigate = useNavigate();
  const location = useLocation();

  const requireSignIn = useCallback((intent?: SaveIntent) => {
    // Saving needs an account. Say so, then go to the sign-in form carrying where we came from —
    // the same `state.from` shape ProtectedRoute uses, so one place can learn to honour it — and
    // the save itself, so the visitor does not have to find the star again afterwards.
    toast('Sign in to save matches to your dashboard.');
    const handoff: SignInHandoff = { from: location, save: intent, at: Date.now() };
    navigate('/login', { state: handoff });
  }, [navigate, location]);

  const toggleSave = useCallback(async (matchId: string, next: boolean, match?: Match) => {
    try {
      await setMatchSaved(matchId, next, match ? { match } : undefined);
      return null;
    } catch (err: unknown) {
      const message = getErrorMessage(err, next
        ? 'That match could not be saved. Nothing was changed.'
        : 'That match could not be removed. Nothing was changed.');
      if (toastErrors) toast.error(message);
      return message;
    }
  }, [setMatchSaved, toastErrors]);

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
