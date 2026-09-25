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
 * THE RULES THIS MODULE IS BUILT AROUND
 *
 * 1. A FAILURE IS NEVER AN EMPTY RESULT. Every read rethrows. The store keeps the last snapshot it
 *    genuinely received and reports `status: 'error'` with the server's own message, so a caller
 *    can say "we could not load your favourites" instead of "you follow nothing". search.service.ts
 *    holds the same rule for the same reason, and names the symptom: a swallowed network error
 *    tells the reader "No results found for Arsenal" about a search that never ran.
 *
 * 2. AN OPTIMISTIC WRITE ROLLS BACK HONESTLY. A toggle applies immediately, then reconciles with
 *    the authoritative list the server returns. If the write fails, THE THING THAT FAILED is put
 *    back and the error is rethrown, so the control goes back to where it was and the caller can
 *    tell the user it did not happen. A star that stays filled after a failed save is a lie.
 *
 *    "The thing that failed", not the whole snapshot. A rollback must never restore `before.data`
 *    — the entire favourites state captured before the write went out — because that throws away
 *    anything a legitimate refresh brought in while the write was in flight, and, across a change
 *    of account, would put one reader's whole favourites state into another's.
 *
 *    Not the whole ROW either, which is the same mistake one level down: a save row carries the
 *    fixture, and a note edit does not write the fixture. See `revertSavedMatch`.
 *
 *    AND IT GOES BACK TO THE LAST VALUE THE SERVER HAS CONFIRMED SO FAR, WHICH IS NOT ALWAYS THE
 *    VALUE THE STORE HELD WHEN THE WRITE WAS ISSUED. With a write for the same key already on the
 *    wire, the store is holding that write's optimistic guess, and a second write that captured
 *    it would, on failure, put a note nobody ever saved back on the screen — the reader left
 *    looking at the first of two edits that both failed. The baseline is per key, opened by the
 *    first write of a chain and shared by every write that overlaps it.
 *
 *    "SO FAR" IS MEANT LITERALLY: a write still on the wire can confirm something newer, and when
 *    its answer lands it is applied over the rollback. That is rule 4's other half — an answer
 *    only stands aside for a newer one that is still coming or has already spoken — and it is
 *    what stops a failed unsave taking a save the server accepted down with it. A READ CONFIRMS
 *    TOO: a refresh landing while the chain is open is the server speaking about the key later
 *    than the value the chain opened on, so it replaces it and the rollback puts THAT back. See
 *    `saveBaselines` on `FavouritesStore`.
 *
 * 3. AN ANSWER FROM A SESSION THAT HAS ENDED IS NOT APPLIED — for WRITES exactly as for reads.
 *    `session` and `writes` both guard reads; only `session` can guard a write against time,
 *    because a write is the local change and cannot be older than itself. A save, unsave or
 *    follow whose response lands after the reader signed out, or after somebody else signed in on
 *    the same machine, writes NOTHING: not the data (a private note is in that payload), not the
 *    pending flags, not a poll, not an error. The caller is told with `DiscardedWrite` rather than
 *    a resolved promise, because the write did happen on the server for the account that started
 *    it and a component that believed it had succeeded HERE would be saying something false.
 *
 * 4. AN ANSWER SPEAKS ONLY FOR WHAT NO NEWER WRITE HAS SPOKEN FOR. Two writes can be answered in
 *    the opposite order to the one they were issued in, and each answer carries the server's view
 *    of the world from before it had seen the other. Letting whichever answer lands last win
 *    would lose the reader's last intent to the network's last packet: a team put back into the
 *    followed list by the answer to the unfollow BEFORE it, a corrected note replaced by the
 *    version it corrected. So an answer stands aside while a newer write on its key is STILL ON
 *    THE WIRE, and again when a newer write's answer has ALREADY stated what that key holds.
 *    With neither true it is applied however old it is: nothing newer is coming and nothing
 *    newer has come, so it is the most recent thing the server has told this tab about the key
 *    and the alternative is leaving the screen on a guess. See `writesOnKey` on
 *    `FavouritesStore`.
 *
 * 5. AN ANSWER'S UNAUTHORED FIELDS CAN BE THE OLDER COPY, AND ONE COUNTER DECIDES WHICH. A save
 *    answer carries the whole fixture, which no save writes; a follow answer carries the whole
 *    followed list, of which a follow writes one id. Both are snapshots frozen when the server
 *    processed the write, so neither is dated against anything the store learned afterwards.
 *    USUALLY THEY ARE THE FRESHER COPY — nothing has landed since the write went out, and taking
 *    them is what keeps the row current. They are older only when something moved underneath
 *    them while the write was on the wire: a read snapshot (`snapshotsApplied`), or, for the
 *    whole followed list, another write of the reader's own (`writesInFlight`, `lastWriteTicket`).
 *    Every place that takes an unauthored field asks that question first, and when the answer is
 *    the older copy it is believed about its own fields alone: the note and its two timestamps
 *    (`saveMatch`), the one followed id (`followIdsAfterWrite`). That is how a match that ended
 *    while a note edit was in flight stays finished, and how a follow a later unfollow removed
 *    stays removed. The same distinction as 2, on the success side: a rollback undoes only what
 *    its write did, and a success applies only what its write did — plus whatever nothing newer
 *    has anything to say about.
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
import { isPlayableNow, resultDelay } from '@/utils/resultDelay';

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

// ------------------------------------------------------- undoing ONE write, not the whole world
/**
 * REVERTING A FAILED WRITE TOUCHES ONLY WHAT THAT WRITE TOUCHED.
 *
 * No rollback here may be `this.set({ data: before.data })` — the whole snapshot as it stood when
 * the write was issued. That is wrong twice over. Across a change of account it puts one reader's
 * entire favourites state into another's; and even inside one session it silently discards
 * whatever a legitimate refresh brought in while the write was on the wire, so a match the reader
 * saved on their phone, arriving in a refresh, would vanish again because an unrelated follow
 * happened to fail. The helpers below invert exactly the optimistic step and nothing else,
 * applied to whatever the store holds NOW.
 */
type FollowedTeam = FavouritesSnapshot['teams'][number];
type FollowedLeague = FavouritesSnapshot['leagues'][number];

/**
 * What the server last said about one followed id, in the shape the two reverts below need.
 *
 * `teamRow` and `leagueRow` are the resolved rows an unfollow drops from the displayed lists, so
 * a rollback can put back the club or competition the panel lists and not merely the id. Only the
 * one matching the key's kind is ever set; the key is namespaced, so there is no id at which both
 * could be meant.
 */
interface ConfirmedFollow {
  followed: boolean;
  teamRow: FollowedTeam | null;
  leagueRow: FollowedLeague | null;
}

/**
 * One key's last confirmed value, and the ticket of the write whose answer stated it.
 *
 * `answeredTicket` is 0 while no answer has stated the value: it is then the row the chain
 * opened with, or the one a read snapshot has brought in since. See `saveBaselines` on
 * `FavouritesStore`.
 */
interface Baseline<T> {
  answeredTicket: number;
  value: T;
}

function revertTeamFollow(
  snapshot: FavouritesSnapshot, id: string, wasFollowed: boolean, rowBefore: FollowedTeam | null,
): FavouritesSnapshot {
  return {
    ...snapshot,
    teamIds: wasFollowed ? withId(snapshot.teamIds, id) : without(snapshot.teamIds, id),
    // Only an UNFOLLOW removes a resolved row optimistically, so only its rollback puts one back;
    // a failed follow never added one and must not invent one here.
    teams: wasFollowed && rowBefore && !snapshot.teams.some(team => team.id === id)
      ? [...snapshot.teams, rowBefore]
      : snapshot.teams,
  };
}

function revertLeagueFollow(
  snapshot: FavouritesSnapshot, id: string, wasFollowed: boolean, rowBefore: FollowedLeague | null,
): FavouritesSnapshot {
  return {
    ...snapshot,
    leagueIds: wasFollowed ? withId(snapshot.leagueIds, id) : without(snapshot.leagueIds, id),
    leagues: wasFollowed && rowBefore && !snapshot.leagues.some(league => league.id === id)
      ? [...snapshot.leagues, rowBefore]
      : snapshot.leagues,
  };
}

/**
 * The followed list to show once a follow write's answer comes back.
 *
 * A FOLLOW ANSWER CARRIES THE WHOLE LIST, AND THAT LIST IS ONLY AS CURRENT AS THE WRITES THE
 * SERVER HAD PROCESSED WHEN IT BUILT IT. Assigning `result.ids` wholesale makes a claim about
 * every id in the account rather than about the one the reader touched. Unfollow a team and then
 * another one quickly: the server answers the first with a list that STILL CONTAINS the second,
 * because it had not seen the second unfollow yet. Whichever way round the two answers then
 * arrive, one of them is speaking about an id it cannot know the current value of — and when the
 * older one lands last it puts the second team back, contradicting both the optimistic removal
 * and the second unfollow's own confirmed answer. The dashboard is then listing a club the reader
 * has just removed and the server no longer holds.
 *
 * `serverListIsCurrent` is the caller's judgement that NOTHING THIS STORE KNOWS OF HAPPENED
 * BETWEEN THE SERVER BUILDING THAT LIST AND THIS ANSWER BEING APPLIED: no other write was in
 * flight when this one was issued, none was issued since, and no read snapshot has been applied
 * in the meantime. THE READ MATTERS AS MUCH AS THE WRITES, and is the easiest of the three to
 * leave out: a follow made on another device arrives here inside a refresh, the answer to a star
 * pressed on this tab was built by the server before that follow existed, and assigning it
 * wholesale deletes the other device's club from the dashboard — the older of two server views
 * overwriting the newer.
 *
 * All three hold for the ordinary case, one star pressed on its own, which is why the whole list
 * is still worth taking when they do: it is how a follow refused for hitting the limit, or a
 * change made in another tab, corrects the display instead of being papered over. When they do
 * not hold, the answer is trusted about its own id — which its write did author — and nothing
 * else, and the rest of the list catches up on the next read: a snapshot of one instant, rather
 * than two instants mixed together.
 */
function followIdsAfterWrite(
  serverIds: string[], localIds: string[], id: string, following: boolean,
  serverListIsCurrent: boolean,
): string[] {
  if (serverListIsCurrent) return serverIds;
  return following ? withId(localIds, id) : without(localIds, id);
}

/**
 * Swap one saved row for a new version of ITSELF, where it already sits.
 *
 * Separate from `insertSaved` because the caller has already established that the FIXTURE has not
 * changed, and therefore neither has the bucket. Re-inserting would move the row to the end of
 * its list (or the front of `finished`) for no reason. That is a small thing and worth stating as
 * the small thing it is: `buildFeed` re-sorts every group by kick-off time alone, so a row's
 * position inside its bucket reaches the reader only as the tiebreak between fixtures whose
 * kick-off times are equal or missing, and as the row order of the data export.
 */
function replaceSaved(saved: SavedMatchesSnapshot, entry: SavedMatch): SavedMatchesSnapshot {
  const swap = (list: SavedMatch[]): SavedMatch[] =>
    list.map(held => (held.matchId === entry.matchId ? entry : held));
  // The counts cannot move: one row is exchanged for one row, in the bucket it was already in.
  return {
    ...saved, upcoming: swap(saved.upcoming), live: swap(saved.live), finished: swap(saved.finished),
  };
}

/**
 * Put one saved match back to the row it had — or to absent, when it had none.
 *
 * `entryBefore` is the reader's own save row as it stood before the write, note included, so a
 * failed note edit restores the note they had rather than clearing it.
 *
 * ONLY THE READER'S OWN FIELDS GO BACK, NEVER THE FIXTURE, and that distinction is the whole of
 * this function. A `SavedMatch` carries `.match` — the entire fixture payload, status and score
 * included — and reinserting the captured row whole would throw away a result refresh that landed
 * while the note edit was on the wire: a fixture the backend had moved to FINISHED with a final
 * score would revert to the LIVE, scoreless copy captured before the edit, and because
 * `insertSaved` buckets on `match.status` it would jump back under "In play now" as well — a
 * failed note edit making a played match look like it is still being played. The write only ever
 * touched the note and its two timestamps, so those are the only fields a rollback may touch;
 * whatever fixture the store holds now is the freshest one anybody has.
 */
function revertSavedMatch(
  snapshot: FavouritesSnapshot, matchId: string, entryBefore: SavedMatch | null,
): FavouritesSnapshot {
  if (!entryBefore) {
    return { ...snapshot, savedMatches: removeSaved(snapshot.savedMatches, matchId) };
  }
  const current = allSaved(snapshot.savedMatches).find(entry => entry.matchId === matchId) ?? null;
  // No row at all — the optimistic removal took it out, or it was never there. Nothing fresher
  // than the captured copy exists, so that copy goes back whole, fixture and all.
  if (!current) {
    return { ...snapshot, savedMatches: insertSaved(snapshot.savedMatches, entryBefore) };
  }
  return {
    ...snapshot,
    savedMatches: replaceSaved(snapshot.savedMatches, {
      ...current,
      note: entryBefore.note,
      savedAt: entryBefore.savedAt,
      updatedAt: entryBefore.updatedAt,
    }),
  };
}

/**
 * The instant a fixture kicks off, or null when we were not given one.
 *
 * DELIBERATELY NOT `kickoffMsOf` (further down this file, for the feed). That one falls back to
 * the calendar date at midnight UTC, which is right for ORDERING a fixture into its day and wrong
 * for deciding whether it has started: it would make every fixture on today's date look overdue
 * from midnight onwards, and start a poll for each one. A fixture whose payload carries no
 * kick-off time is not watched for a kick-off we do not know.
 */
function kickoffInstantOf(match: Match): number | null {
  const parsed = match.kickoffUtc ? Date.parse(match.kickoffUtc) : NaN;
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
 * `syncLivePoll()` MUST NOT GATE ITS INTERVAL ON `savedMatches.live` ALONE. A fixture that is
 * still upcoming leaves that bucket empty, so no interval would run, so nothing would notice the
 * kick-off: the poll that discovers the transition would be gated on the state it exists to
 * discover. A reader with the page in front of them would watch "Coming up" all through the
 * first half, because the focus refresh only fires on the way BACK to a tab and nothing else
 * re-reads anything.
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
 * Whether `match` is inside the window in which it is worth watching for a kick-off.
 *
 * ONE RULE, used by the saved-match watch and by the followed-fixture watch further down, so the
 * two cannot drift apart: still `scheduled` (a postponed or cancelled fixture will not kick off
 * at this time), a kick-off time we were actually given, and now between the lead and the grace.
 */
function isDueToStart(match: Match, now: number): boolean {
  if (match.status !== 'scheduled') return false;
  const kickoff = kickoffInstantOf(match);
  if (kickoff === null) return false;
  return now >= kickoff - KICKOFF_WATCH_LEAD_MS && now <= kickoff + KICKOFF_WATCH_GRACE_MS;
}

/** When `match` starts being worth watching, or null when that moment has passed or is unknown. */
function watchStartOf(match: Match, now: number): number | null {
  if (match.status !== 'scheduled') return null;
  const kickoff = kickoffInstantOf(match);
  if (kickoff === null) return null;
  const from = kickoff - KICKOFF_WATCH_LEAD_MS;
  // Already inside its window: the interval has it, and a wake for a moment in the past would
  // fire in a tight loop.
  return from > now ? from : null;
}

/** The soonest moment any of `matches` starts being worth watching, or null when none does. */
function nextWatchStart(matches: Match[], now: number): number | null {
  let soonest: number | null = null;
  matches.forEach(match => {
    const from = watchStartOf(match, now);
    if (from === null) return;
    if (soonest === null || from < soonest) soonest = from;
  });
  return soonest;
}

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
 * A WRITE whose answer came back after the session that issued it had ended.
 *
 * WHY THIS IS NOT THE SAME AS A DISCARDED READ, AND WHY IT IS NOT SILENT. A read that is thrown
 * away costs nothing: nobody asked for it and nothing happened. A write DID happen — the save,
 * the note, the follow reached the server and was applied to the account that started it. Two
 * things then have to be true at once. Nothing of it may reach the reader who is here now, which
 * is the store's job and is why not one field is written. And the component that asked for it
 * must not be told it worked, because "worked" would be read as "worked for the person looking at
 * this screen", which is exactly the sentence that is false. So the promise REJECTS with this.
 *
 * `settled` says what the server actually did for the old account, and the message says it in
 * words, because `getErrorMessage` renders `err.message` and every caller in this project puts
 * that straight into a toast. Neither the message nor this object names the match, the note or
 * the account: the old reader's private note must not be carried into the new reader's screen by
 * the error any more than by the data.
 */
export class DiscardedWrite extends Error {
  /** What the server did for the account that issued the write, before the session ended. */
  readonly settled: 'applied' | 'failed';

  constructor(settled: 'applied' | 'failed') {
    super(settled === 'applied'
      ? 'That change finished after the account that started it was signed out. It was applied to '
        + 'that account, and is not part of the session you are in now.'
      : 'That change did not finish, and the account that started it has since been signed out. '
        + 'Nothing was changed for the account signed in now.');
    this.name = 'DiscardedWrite';
    this.settled = settled;
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
 * FIVE PIECES OF BOOKKEEPING DECIDE WHETHER AN ANSWER MAY BE APPLIED. A read is one round trip;
 * anything can happen during it, and two writes are two round trips that can finish in either
 * order. Every guard in this class is one of these or a conjunction of them, so a new guard
 * belongs on this list — and a reader looking for all of them will find all of them here.
 *
 *   `session` — WHOSE STORE IS THIS STILL? Bumped by every identity change (signing in, signing
 *   out, one account replacing another on the same machine) and by `reset()`. Captured when a
 *   request is ISSUED and read again when its answer lands. It guards reads AND writes, and it
 *   is the only one of the five that can date a write against the reader: `writes` cannot,
 *   because a write cannot be older than itself, but any write can belong to somebody who has
 *   since left. A read whose session has moved is dropped WITHOUT A
 *   TRACE — no data, no error, no `loadedAt`, no focus watcher, no poll — because `reset()`
 *   cannot cancel a request already on the wire and this is the only place it can be stopped. So
 *   is a write, on all six of its answer paths (save, unsave and follow, each with a success and
 *   a rollback): no data, because a private note is in that payload; no pending flag; no
 *   rollback; and it rejects with `DiscardedWrite` rather than resolving, because the write did
 *   happen for the account that started it and a caller told it succeeded HERE would be wrong.
 *
 *   `writes` — DID THE READER CHANGE SOMETHING WHILE THIS READ WAS OUT? Bumped by every local
 *   change: the optimistic step, the reconciliation with the answer, and the rollback. A
 *   snapshot the server built before that change cannot contain it, so applying it would
 *   silently undo the reader's own action — the star going back off on its own. Such a read is
 *   discarded AND REPLACED by a fresh one (`readUntilCurrent`), because the reader is still owed
 *   the server's current answer and not merely the absence of a wrong one. Reads only.
 *
 *   `writesOnKey`, stamped from `lastWriteTicket` — WHAT IS STILL ON THE WIRE FOR THIS KEY? One
 *   ticket per write, taken when the write is ISSUED and dropped when it settles, held in a set
 *   per followed id and per saved match. Two answers can arrive in the opposite order to the
 *   writes that caused them, and each describes the world as the server saw it before it had
 *   seen the other, so the last ANSWER is not the reader's last INTENT: that is an unfollow
 *   undone by an older sibling's answer, or a corrected note replaced by the version it
 *   corrected. An answer with a newer ticket than its own still in the set writes nothing at
 *   all — that write owns the id, its value and its pending flag, and states the end result
 *   itself. An answer with nothing newer outstanding is applied — its session having already
 *   been checked — and `answeredTicket` on the baseline is the one thing left that can stop it:
 *   a newer answer that has already spoken for the key.
 *
 *   `snapshotsApplied` — HAS A READ LANDED SINCE THIS WRITE WENT OUT? Counted, never timed. The
 *   fields an answer did not author (the whole fixture on a save answer, the whole followed list
 *   on a follow answer) are frozen at the instant the server processed the write, so only a read
 *   applied since then can hold anything newer. The three above cannot answer this: they see
 *   local events, and a change made on the reader's phone reaches this tab through a read.
 *   `saveMatch` asks it about the fixture, `toggleFollow` about the list.
 *
 *   `writesInFlight` — DID THIS WRITE HAVE THE WIRE TO ITSELF? Read through
 *   `nothingElseInFlight()` before the write is issued and paired with `lastWriteTicket` being
 *   unchanged when the answer lands, which together mean no other write overlapped this one at
 *   either end. It is the other half of `toggleFollow`'s question, because a follow answer's
 *   whole list cannot speak for an id another write of the reader's own was changing at the
 *   same time.
 *
 * WHEN A GUARD SAYS AN ANSWER IS OLD, THE ANSWER IS NARROWED, NOT HALVED AT RANDOM. Out of
 * session or superseded, it writes nothing; merely overtaken by a read, it is still believed
 * about the fields its own write authored — the note and its two timestamps, the one followed
 * id — and disbelieved about the rest. Rules 2 to 5 at the top of this file are that same point
 * stated from the caller's side.
 *
 * A SIXTH PIECE OF BOOKKEEPING MOSTLY ANSWERS A DIFFERENT QUESTION, and is kept off the list
 * above for that reason: the VALUE in `saveBaselines` and `followBaselines` decides not whether
 * an answer may be applied but WHAT A FAILURE PUTS BACK: the last thing the server has been
 * seen to say about one key, whether an answer stated it, a read brought it in, or it is the row
 * the chain opened on. Their `answeredTicket` is the exception and belongs squarely to the
 * third: it is how an answer learns that a newer one has already stated what its key holds.
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
   * An answer can only be told apart from one belonging to another account if the store holds an
   * identity to compare it against. `reset()` on sign-out is not that signal on its own: a
   * sign-out immediately followed by a different sign-in looks, from in here, like one continuous
   * session. It is a key rather than the user object — `useFavourites` passes the signed-in id —
   * and nothing is done with it but comparison.
   */
  private accountId: string | null = null;

  private session = 0;

  private writes = 0;

  /**
   * WHICH WRITES ARE STILL ON THE WIRE FOR EACH KEY: for every followed id and every saved match
   * with a write outstanding, the tickets of those writes.
   *
   * `session` and `writes` cannot answer this. `session` only knows that the reader has not
   * changed, and `writes` counts local changes without saying which key they were about — so to
   * those two, both two writes on the same id and two writes whose answers speak about each
   * other's ids look like one write followed by another, and the LAST ANSWER wins. That is the
   * wrong winner: the reader's last INTENT is what the screen must end up agreeing with, and the
   * network decides the order of answers, not the reader.
   *
   * A ticket joins its key's set when the write is issued and leaves when the write settles, so
   * the set is exactly the writes on that key that have yet to be answered. A NEWER TICKET THAN
   * ITS OWN STILL IN THE SET is what makes an answer stand aside: that write owns the value and
   * the pending flag and will state the end result when it answers. Nothing newer in the set is
   * the opposite finding — no other answer is coming for this key — and it is half of
   * `writeSuperseded`, the half that lets an old answer through rather than dropping it.
   *
   * A SET RATHER THAN THE NEWEST TICKET ALONE, because "is a newer write still running?" cannot
   * be read off a single stamp: the newest-issued write can settle first and leave two older
   * ones outstanding, and a stamp cleared at that point says the same thing as a chain that
   * never existed. The key is dropped when its set empties, and the baseline below with it.
   */
  private writesOnKey = new Map<string, Set<number>>();

  private lastWriteTicket = 0;

  /**
   * How many writes are on the wire right now, across every key.
   *
   * Only `toggleFollow` needs it, and only for one question: may this answer's WHOLE-LIST field
   * be believed? Not on its own — see `snapshotsApplied` — but it is half the answer: a write
   * that raced another write cannot speak for the id that other write was about.
   */
  private writesInFlight = 0;

  /**
   * HOW MANY READ SNAPSHOTS HAVE BEEN APPLIED, ever, in this store.
   *
   * THE ONLY WAY TO DATE A WRITE ANSWER AGAINST A READ, and therefore the guard behind rule 5:
   * every field a write did not author is frozen at the instant the server processed it, and
   * only a read applied since then can be newer. `session`, `writesOnKey` and `writesInFlight`
   * see local events; a change made on the reader's phone reaches this tab through a READ and is
   * invisible to all three. Both callers compare this counter across their own round trip —
   * `toggleFollow` for the whole followed list (the phone's club, otherwise taken straight back
   * off the dashboard by an answer built before it existed) and `saveMatch` for the fixture (a
   * result, otherwise un-finished by a note edit that succeeded). Unchanged means nothing landed
   * underneath the write, and then the answer is the fresher copy.
   *
   * A counter rather than `loadedAt` because `loadedAt` is a clock reading: two snapshots inside
   * one millisecond leave it unchanged, and this question must never answer "nothing landed"
   * when something did.
   */
  private snapshotsApplied = 0;

  /**
   * THE LAST SAVE ROW THE SERVER CONFIRMED for every match with a write on the wire, and the only
   * thing a failed save or unsave may put back.
   *
   * A ROLLBACK RESTORES CONFIRMED TRUTH, NEVER A VALUE AN EARLIER IN-FLIGHT WRITE INVENTED. Each
   * write captures the row as the store holds it, and while a write for that match is already
   * running the store is holding THAT write's optimistic guess — so a second write's rollback,
   * built from its own capture, reinstates the first write's note. With both edits failed the
   * server holds neither, and the reader is left looking at the one they typed first as though it
   * had been saved.
   *
   * The entry is opened by the first write of a chain, from the store itself, and that is the one
   * moment at which the store's own row for the key is the server's last word about it. No write
   * of ours is in flight to have changed it optimistically, and every path that ends a chain
   * leaves the key on something the server said — an answer applied, or a rollback to the value
   * the server had confirmed.
   *
   * Every write that overlaps the chain inherits the entry, and an answer replaces it —
   * INCLUDING AN ANSWER THAT WRITES NOTHING TO THE STORE, which is still the server's own
   * statement about the key. So does a read, while no answer has spoken for the key: see
   * `confirmBaselinesFromRead`. `closeWrite` drops the entry once the LAST write on that key has
   * settled, so nothing here outlives the writes it belongs to, and `reset()` clears both maps
   * for the same reason it clears `writesOnKey`: a key left behind would hand the next account a
   * baseline built from the previous one's rows.
   *
   * NO ENTRY AND AN ENTRY WORTH `null` SAY DIFFERENT THINGS, and the wrapper is what keeps them
   * apart: no entry means no chain is running for this key, while `value: null` is a statement —
   * the server holds no save for that match, so a failure leaves the row absent.
   *
   * `answeredTicket` IS WHICH WRITE THE VALUE CAME FROM, and it is here for the same reason
   * `writesOnKey` is: two answers can arrive in the opposite order to the writes that produced
   * them, and the later-issued one is the reader's later intent. It does two jobs with one
   * number — it keeps an older answer from replacing a value a newer one already stated, and it
   * is the second half of `writeSuperseded`, where it keeps that same older answer out of the
   * store. It starts at 0, which no ticket ever is, so the row the chain opened with loses to
   * the first answer that lands.
   */
  private saveBaselines = new Map<string, Baseline<SavedMatch | null>>();

  /** The same, for the follow state of one team or league id. See `saveBaselines`. */
  private followBaselines = new Map<string, Baseline<ConfirmedFollow>>();

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
   * Every mutation below is guarded by `session` and `writes`, the two of the five described on
   * the class that a read is subject to. Nothing is written on a discarded read — not the state,
   * not `loadedAt`, not the watcher and not the poll — because the only honest trace of a
   * request made for a session that has ended is none.
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
      // Counted, not timed: `loadedAt` is a clock reading and two snapshots applied inside one
      // millisecond share it. A write that has to know whether a snapshot landed while it was on
      // the wire needs a value that always changes. See `snapshotsApplied`.
      this.snapshotsApplied += 1;
      // This snapshot is the server's latest word on every key a write is still outstanding for,
      // and those writes' failures have to put back what it says rather than what they found.
      this.confirmBaselinesFromRead(snapshot);
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
    // Every write on the wire now belongs to the session that just ended and will be refused by
    // `session` before its ticket is ever consulted. Dropping them keeps this map from carrying
    // one reader's keys into the next reader's session, where they would make a first write on
    // an id look as though something else were still running on it.
    this.writesOnKey.clear();
    this.writesInFlight = 0;
    // And the values those writes would have rolled back to. A note or a follow the previous
    // reader confirmed is theirs; inherited by a first write in the next reader's session it
    // would be restored onto their row by a failure that has nothing to do with them.
    this.saveBaselines.clear();
    this.followBaselines.clear();
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
    // `upcoming` is everything that is neither live nor finished, postponed and cancelled
    // included. Those two are not about to kick off and `isDueToStart` will not watch them.
    const upcoming = this.state.data?.savedMatches.upcoming ?? [];
    return upcoming.filter(entry => isDueToStart(entry.match, now)).length;
  }

  /** When the next saved fixture starts being worth watching, or null when none does. */
  private nextKickoffWatchAt(now: number = Date.now()): number | null {
    const upcoming = this.state.data?.savedMatches.upcoming ?? [];
    return nextWatchStart(upcoming.map(entry => entry.match), now);
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

  /**
   * True when the answer to a write issued in `session` belongs to a session that has ended.
   *
   * NOTHING is written when it does — not the data, not the pending flags, not a poll. There is
   * no stale flag to tidy up either: `reset()` replaced the whole state, pending lists included,
   * at the moment the session changed. Clearing one here would only notify the new session's
   * subscribers about a write it never made, and `without()` on a list that no longer holds the
   * id would still hand every one of them a new state object.
   */
  private answerIsStale(session: number): boolean {
    return this.session !== session;
  }

  /** The key a write's ordering is tracked under. Namespaced so a team and a league id cannot collide. */
  private static keyFor(kind: 'team' | 'league' | 'match', id: string): string {
    return `${kind}:${id}`;
  }

  /**
   * The id `keyFor` built a key around.
   *
   * The kind is NOT recoverable by reading the prefix back, and a caller that needs it must ask
   * `keyFor` instead: `followBaselines` is keyed by both 'team' and 'league', so a bare id says
   * nothing about which list it belongs to. `confirmBaselinesFromRead` rebuilds the team key and
   * compares, rather than trusting a prefix it would then have to keep in step with `keyFor`.
   */
  private static idIn(key: string): string {
    return key.slice(key.indexOf(':') + 1);
  }

  /** True when no write at all is on the wire. Read BEFORE issuing, never after. */
  private nothingElseInFlight(): boolean {
    return this.writesInFlight === 0;
  }

  /** Add a new write to this key's outstanding set, and hand back the ticket that identifies it. */
  private issueWrite(key: string): number {
    this.lastWriteTicket += 1;
    const outstanding = this.writesOnKey.get(key) ?? new Set<number>();
    outstanding.add(this.lastWriteTicket);
    this.writesOnKey.set(key, outstanding);
    this.writesInFlight += 1;
    return this.lastWriteTicket;
  }

  /**
   * True when this answer may not touch the store, because a newer write has spoken for the key
   * or is about to.
   *
   * TWO WAYS TO BE SPOKEN FOR, AND "A NEWER WRITE EXISTED" IS NEITHER OF THEM.
   *   A newer write on this key is STILL ON THE WIRE. It owns the value and the pending flag and
   *   will state the end result when it answers, so this answer writes nothing at all — not the
   *   value, not the pending flag, not a rollback. Clearing the flag here would stop the control
   *   spinning while a write on it is still genuinely running.
   *
   *   A newer write's answer has ALREADY STATED what the key holds (`answeredTicket` on the
   *   baseline). This one cannot improve on it: with two saves confirmed and answered in the
   *   opposite order, applying the older answer afterwards would put back the note the newer one
   *   replaced.
   *
   * WITH NEITHER TRUE, AN ANSWER IS APPLIED HOWEVER OLD THE WRITE BEHIND IT. Nothing newer is
   * coming for this key and nothing newer has come, so this is the most recent thing the server
   * has told this tab about it, and discarding it would leave the screen on a guess: a save the
   * server accepted dropped because the unsave issued after it failed and answered first, or the
   * bookmark that unsave's rollback removed left off the screen the server still holds it on.
   *
   * ASKED BEFORE THE ANSWER IS RECORDED in the baseline, everywhere it is asked, or a write finds
   * its own ticket sitting in `answeredTicket` and reads it as somebody else's.
   */
  private writeSuperseded(key: string, ticket: number): boolean {
    const outstanding = this.writesOnKey.get(key);
    if (outstanding && Array.from(outstanding).some(other => other > ticket)) return true;
    // One key can only be in one of the two maps — `keyFor` namespaces a match against a
    // followed id — so this is that key's baseline wherever it lives, and 0 where no chain is
    // running for it.
    const held = this.saveBaselines.get(key) ?? this.followBaselines.get(key);
    return ticket <= (held?.answeredTicket ?? 0);
  }

  /**
   * This write is over, whatever it did.
   *
   * Called on every path that reaches an answer, the ones that wrote nothing included — such a
   * write is no longer in flight, and leaving it counted would make the next write believe it
   * had company forever. THE KEY IS RELEASED ONLY WHEN THE LAST WRITE ON IT HAS SETTLED, which
   * is not always the newest-issued one: an answer still to come for an older write has to be
   * able to see that nothing newer is outstanding, and to find the chain's baseline where it
   * left it. The paths that reject with `DiscardedWrite` deliberately do NOT call this:
   * `reset()` cleared all of it, and a write from a session that has ended must not touch a
   * counter belonging to this one.
   */
  private closeWrite(key: string, ticket: number): void {
    const outstanding = this.writesOnKey.get(key);
    outstanding?.delete(ticket);
    if (outstanding && outstanding.size === 0) {
      this.writesOnKey.delete(key);
      // Nothing is left on this key to roll back or to reconcile, so the chain is over and its
      // baseline has nobody to serve. The next write on this key opens a new one from the store,
      // which by then holds what the last answer of this chain stated. Both maps are asked
      // because the key says which of them can hold it, and one deletion is always a no-op.
      this.saveBaselines.delete(key);
      this.followBaselines.delete(key);
    }
    this.writesInFlight = Math.max(0, this.writesInFlight - 1);
  }

  /**
   * Open this key's confirmed baseline, unless a chain for it is already running.
   *
   * `asStoredNow` is only ever read when this write opens the chain, and that is the one moment
   * at which the store's own row is the server's last word about the match: nothing of ours is in
   * flight to have changed it optimistically.
   */
  private openSaveBaseline(key: string, asStoredNow: SavedMatch | null): void {
    if (!this.saveBaselines.has(key)) {
      this.saveBaselines.set(key, { answeredTicket: 0, value: asStoredNow });
    }
  }

  /**
   * The row this key's rollback must put back.
   *
   * The entry lives for as long as any write on the key is outstanding, and the write asking is
   * one of those, so it is there. The null is the honest reading of its absence either way: no
   * save the server has confirmed.
   */
  private saveBaseline(key: string): SavedMatch | null {
    return this.saveBaselines.get(key)?.value ?? null;
  }

  /**
   * Take the server's answer as the confirmed truth for this key.
   *
   * Called on both save paths whatever the answer went on to do to the store, because an answer
   * that may not touch the store is still the server speaking: it is exactly what a later write
   * in the same chain has to roll back to. `null` is an unsave's answer: the server holds no
   * save for this match now.
   *
   * Nothing is opened here. A key with no chain running has nobody to hand the value to, and an
   * entry left in the map would be inherited by a write that should read the store instead.
   *
   * AN OLDER ANSWER THAT ARRIVES LATER LOSES, here and in `writeSuperseded`, which reads this
   * same number: with two saves confirmed in the opposite order to the writes that made them,
   * the earlier write's answer neither replaces the value here nor reaches the screen. The rule
   * is the file's rule — the reader's later intent wins over the network's later packet.
   */
  private confirmSaveBaseline(key: string, ticket: number, row: SavedMatch | null): void {
    const held = this.saveBaselines.get(key);
    if (held && ticket > held.answeredTicket) {
      this.saveBaselines.set(key, { answeredTicket: ticket, value: row });
    }
  }

  /**
   * Take an applied snapshot as the confirmed value for every chain no answer has spoken for.
   *
   * A READ IS THE SERVER SPEAKING ABOUT A KEY JUST AS AN ANSWER IS, and it is the later of the
   * two whenever the chain opened first — which it always did: the chain's opening write changes
   * the store optimistically, and `readUntilCurrent` discards any snapshot issued before a local
   * change. So a baseline still holding the row the chain opened with is describing the server
   * as of a moment this snapshot has overtaken, and a rollback to it would undo what the
   * snapshot brought in: a note the reader set on their phone, taken off the screen by the
   * failure of an edit that was on the wire when it arrived.
   *
   * A VALUE AN ANSWER STATED IS LEFT ALONE, and `answeredTicket` is what tells the two apart.
   * The server may have built that answer before this snapshot or after it — the read was
   * issued while the write was still on the wire, so nothing here can order them — and of the
   * two it is the answer that speaks about this key alone rather than about the whole account.
   *
   * ONLY OPEN CHAINS ARE HERE TO BE CONFIRMED, so this costs one lookup per key with a write
   * outstanding — normally none at all, a read landing mid-write being the uncommon case.
   */
  private confirmBaselinesFromRead(snapshot: FavouritesSnapshot): void {
    const saved = allSaved(snapshot.savedMatches);
    this.saveBaselines.forEach((held, key) => {
      if (held.answeredTicket !== 0) return;
      const matchId = FavouritesStore.idIn(key);
      const row = saved.find(entry => entry.matchId === matchId) ?? null;
      this.saveBaselines.set(key, { answeredTicket: 0, value: row });
    });
    this.followBaselines.forEach((held, key) => {
      if (held.answeredTicket !== 0) return;
      const id = FavouritesStore.idIn(key);
      // Which kind of follow this key is, asked of `keyFor` rather than of the prefix it writes,
      // so the two cannot drift apart.
      const isTeam = key === FavouritesStore.keyFor('team', id);
      this.followBaselines.set(key, {
        answeredTicket: 0,
        value: {
          followed: (isTeam ? snapshot.teamIds : snapshot.leagueIds).includes(id),
          // The resolved row the panel lists, which a rollback to a follow needs and an answer
          // cannot supply: `result.ids` is ids alone, and a snapshot carries the rows.
          teamRow: isTeam ? (snapshot.teams.find(team => team.id === id) ?? null) : null,
          leagueRow: isTeam ? null : (snapshot.leagues.find(league => league.id === id) ?? null),
        },
      });
    });
  }

  /** `openSaveBaseline` for a followed id. */
  private openFollowBaseline(key: string, asStoredNow: ConfirmedFollow): void {
    if (!this.followBaselines.has(key)) {
      this.followBaselines.set(key, { answeredTicket: 0, value: asStoredNow });
    }
  }

  /** `saveBaseline` for a followed id. */
  private followBaseline(key: string): ConfirmedFollow | null {
    return this.followBaselines.get(key)?.value ?? null;
  }

  /**
   * `confirmSaveBaseline` for a followed id: the server has just stated whether it is followed.
   *
   * The resolved ROWS are left as this baseline already holds them, because a follow answer
   * carries no row to replace them with: `result.ids` is ids alone. What it holds is the row the
   * chain opened on, or a fresher one a read snapshot supplied while no answer had spoken for
   * this key — `confirmBaselinesFromRead` may have replaced it, and that row is the better of
   * the two.
   *
   * SO A ROLLBACK TO A CONFIRMED FOLLOW OF AN ID THIS TAB HOLDS NO ROW FOR PUTS BACK THE ID AND
   * NOTHING ELSE. The star fills in, because that reads `teamIds`, and the panel that lists
   * clubs shows the club only once a read brings its row in. `revertTeamFollow` will not invent
   * one, and the quiet reload at the end of `toggleFollow` cannot help here: it runs on the path
   * where an answer was applied, and this value is read by a rollback.
   */
  private confirmFollowBaseline(key: string, ticket: number, following: boolean): void {
    const held = this.followBaselines.get(key);
    if (held && ticket > held.answeredTicket) {
      this.followBaselines.set(key, {
        answeredTicket: ticket, value: { ...held.value, followed: following },
      });
    }
  }

  private async toggleFollow(kind: 'team' | 'league', id: string, following: boolean): Promise<FollowResult> {
    const session = this.session;
    // Stamped BEFORE the optimistic step, so a second toggle of the same control is already the
    // owner of this id by the time the first one's answer comes back to look. `alone` is read
    // before the stamp, because this write is about to be in flight itself.
    const key = FavouritesStore.keyFor(kind, id);
    const alone = this.nothingElseInFlight();
    // Read here too, and for the same question: a snapshot applied while this write is on the
    // wire carries follows this answer's list cannot contain. See `snapshotsApplied`.
    const snapshotsAtIssue = this.snapshotsApplied;
    const ticket = this.issueWrite(key);
    const before = this.state;
    const data = before.data;
    // Captured before the optimistic step, so the rollback can invert exactly that step: what this
    // follow was, and the resolved row an unfollow is about to drop from the displayed lists.
    const wasFollowed = data
      ? (kind === 'team' ? data.teamIds.includes(id) : data.leagueIds.includes(id))
      : false;
    const teamRowBefore = data && kind === 'team'
      ? (data.teams.find(team => team.id === id) ?? null) : null;
    const leagueRowBefore = data && kind === 'league'
      ? (data.leagues.find(league => league.id === id) ?? null) : null;
    // What a failure of this write, or of any write that overlaps it, must put back. Opened from
    // the three captures above only when this write is the first on the id: with a toggle of the
    // same control already on the wire, those three describe ITS optimistic guess.
    const asCaptured: ConfirmedFollow = {
      followed: wasFollowed, teamRow: teamRowBefore, leagueRow: leagueRowBefore,
    };
    this.openFollowBaseline(key, asCaptured);
    const changedData = data !== null;
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

    let result: FollowResult;
    try {
      result = await favouritesApi.follow(kind, id, following);
    } catch (error) {
      // The rollback is the leakiest of the three paths: restoring `before.data` here, the WHOLE
      // snapshot, would across a change of account land the previous reader's entire favourites
      // state in this one's.
      if (this.answerIsStale(session)) throw new DiscardedWrite('failed');
      /*
       * A NEWER TOGGLE OF THIS SAME CONTROL HAS SPOKEN FOR THE ID — it is still on the wire, or
       * its answer has already landed — so this failure is not the current state of anything.
       * Rolling back here would put the id back to what it was two intents ago, over the newer
       * write's state, and clearing the pending flag while that newer write is still running
       * would stop the control spinning with a round trip left to go. The reader is still told
       * their attempt failed; the store simply lets the write that replaced it speak for the id.
       */
      if (this.writeSuperseded(key, ticket)) { this.closeWrite(key, ticket); throw error; }
      // Read before `closeWrite`, which drops the baseline once the last write on this id has
      // settled.
      const confirmed = this.followBaseline(key) ?? asCaptured;
      this.closeWrite(key, ticket);
      const current = this.state.data;
      // Put back the follow state the server last confirmed, and nothing else. Leaving the
      // optimistic state up after a failure would show a follow that does not exist on the
      // server; restoring the whole snapshot would throw away a refresh that legitimately landed
      // while the write was in flight.
      this.noteLocalWrite();
      this.set({
        ...(changedData && current
          ? {
            data: kind === 'team'
              ? revertTeamFollow(current, id, confirmed.followed, confirmed.teamRow)
              : revertLeagueFollow(current, id, confirmed.followed, confirmed.leagueRow),
          }
          : {}),
        ...(kind === 'team'
          ? { pendingTeamIds: without(this.state.pendingTeamIds, id) }
          : { pendingLeagueIds: without(this.state.pendingLeagueIds, id) }),
      });
      throw error;
    }

    if (this.answerIsStale(session)) throw new DiscardedWrite('applied');
    // Asked before the answer is recorded below, which would otherwise leave this write reading
    // its own ticket in `answeredTicket` as somebody else's.
    const superseded = this.writeSuperseded(key, ticket);
    // The server has stated what it holds for this id, so that is what a failure of any write
    // still running on it has to go back to — even where this answer writes nothing to the
    // store itself.
    this.confirmFollowBaseline(key, ticket, result.following);
    /*
     * SPOKEN FOR BY A NEWER TOGGLE OF THE SAME ID. The reader has since asked for the opposite,
     * or asked again; that write owns the id and the pending flag, and it will state the end
     * result when it answers, or already has. Applying this one would let the order the network
     * happened to deliver two answers in decide what the screen says, over the order the reader
     * asked in. The caller still gets the result: it is a true statement about what the server
     * did.
     */
    if (superseded) { this.closeWrite(key, ticket); return result; }
    this.closeWrite(key, ticket);
    const current = this.state.data;
    // The reconciliation is a second local write: a read issued between the optimistic change
    // and this line is older than the server's own answer too.
    this.noteLocalWrite();
    /*
     * The server's answer is the truth about the id this write was FOR, and reconciling against
     * it rather than trusting the optimistic guess is what makes a refused follow (limit
     * reached) show up as the star going back off. How much of the REST of the answer may be
     * believed is `followIdsAfterWrite`'s subject: the whole list only while this write had the
     * wire to itself AND no read snapshot landed underneath it, and otherwise this id alone.
     *
     * THE RESOLVED LIST IS RECONCILED TOO, and that is the same lesson as `unsaveMatch` below.
     * Assigning ids alone assumed the optimistic step — which drops the row from `teams` on an
     * unfollow — was still standing. A refresh landing in between puts the row back, and the
     * panel that lists what you follow reads `teams`, not `teamIds`: the competition or club
     * you had just unfollowed stayed in the list, contradicting its own star. Nothing is ADDED
     * here, because a follow we hold no row for has no row to add; that is what the reload a
     * few lines down is for.
     */
    const serverListIsCurrent = alone
      && this.lastWriteTicket === ticket
      && this.snapshotsApplied === snapshotsAtIssue;
    const ids = current
      ? followIdsAfterWrite(
        result.ids,
        kind === 'team' ? current.teamIds : current.leagueIds,
        id, result.following, serverListIsCurrent,
      )
      : result.ids;
    this.set({
      data: current
        ? (kind === 'team'
          ? {
            ...current,
            teamIds: ids,
            teams: current.teams.filter(team => ids.includes(team.id)),
          }
          : {
            ...current,
            leagueIds: ids,
            leagues: current.leagues.filter(league => ids.includes(league.id)),
          })
        : current,
      ...(kind === 'team'
        ? { pendingTeamIds: without(this.state.pendingTeamIds, id) }
        : { pendingLeagueIds: without(this.state.pendingLeagueIds, id) }),
    });
    // A follow that resolved to a team/league we hold no row for only appears in the resolved
    // lists after a reload; refresh quietly so the dashboard fills in rather than staying blank.
    if (result.changed && result.following) void this.load().catch(() => undefined);
    return result;
  }

  /**
   * Save a match (or edit its note), optimistically.
   *
   * Optimism has a limit here: the payload of a save is the fixture itself, and we can only show
   * one we already have. `match` must be supplied when the fixture is not already in the store —
   * without it the save still runs, but the entry appears only once the server's copy comes back.
   */
  saveMatch = async (matchId: string, options?: { note?: string | null; match?: SavedMatch['match'] }): Promise<SaveMatchResult> => {
    const session = this.session;
    // Stamped before the optimistic step. Two note edits on one match, or a note edit and a
    // removal, are two writes on the same key: one outstanding set and one baseline between
    // them, and a ticket each to be ordered by.
    const key = FavouritesStore.keyFor('match', matchId);
    // Read before the write goes out, and compared again on the success path: it is the only
    // thing that can tell whether the answer's fixture or the store's is the older one.
    const snapshotsAtIssue = this.snapshotsApplied;
    const ticket = this.issueWrite(key);
    const before = this.state;
    const existing = this.savedEntry(matchId);
    // What a failure of this write, or of any write that overlaps it, must put back. `existing`
    // is only the server's last word while nothing of ours is on the wire for this match; with a
    // note edit already running it is that edit's optimistic note, which no rollback may restore.
    this.openSaveBaseline(key, existing);
    const fixture = options?.match ?? existing?.match ?? null;
    // Omitted note means "leave the existing note alone" — the API's rule, mirrored here so the
    // optimistic entry shows the same note the server will keep.
    const note = options?.note === undefined ? (existing?.note ?? null) : (options.note || null);

    // Whether the optimistic step actually touched `data`. Without it there is nothing to revert,
    // and reverting anyway would remove an entry a refresh legitimately brought in.
    const changedData = Boolean(before.data && fixture);
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

    let result: SaveMatchResult;
    try {
      result = await favouritesApi.saveMatch(matchId, options?.note);
    } catch (error) {
      if (this.answerIsStale(session)) throw new DiscardedWrite('failed');
      // A newer write on this match has spoken for it — still on the wire, and owning the note
      // and the pending flag with it, or answered already. Rolling back here would undo that
      // newer intent.
      if (this.writeSuperseded(key, ticket)) { this.closeWrite(key, ticket); throw error; }
      // Read before `closeWrite`, which drops the baseline once the last write on this match has
      // settled.
      const confirmed = this.saveBaseline(key);
      this.closeWrite(key, ticket);
      const current = this.state.data;
      this.noteLocalWrite();
      this.set({
        // Back to the row the server last confirmed — the note it holds, or absent where it
        // holds no save for this match at all. Only the reader's own fields move:
        // `revertSavedMatch` leaves whatever fixture the store holds now exactly where it is.
        ...(changedData && current ? { data: revertSavedMatch(current, matchId, confirmed) } : {}),
        pendingMatchIds: without(this.state.pendingMatchIds, matchId),
      });
      throw error;
    }

    /*
     * THE SAVE REACHED THE SERVER FOR SOMEBODY WHO IS NO LONGER HERE.
     *
     * `result` is that reader's own save row and it carries their PRIVATE NOTE. Inserting it
     * below would put that note into whoever is signed in now — the single worst thing this
     * store can do — so nothing at all is written and the caller is told which reader it worked
     * for. There is no pending flag to clear: `reset()` emptied that list at the boundary.
     */
    if (this.answerIsStale(session)) throw new DiscardedWrite('applied');
    // Asked before the answer is recorded below, which would otherwise leave this write reading
    // its own ticket in `answeredTicket` as somebody else's.
    const superseded = this.writeSuperseded(key, ticket);
    /*
     * THE SERVER NOW HOLDS THIS ROW, SO IT IS WHAT A FAILURE ON THIS MATCH GOES BACK TO.
     *
     * Recorded whether or not the answer goes on to reach the store. An answer a newer write has
     * spoken for may not touch what the reader sees, but it is still the server's own statement
     * about the note, and that newer write is precisely the one that will need it: if this edit
     * saved and the next one fails, the note the reader is left with must be this one and not
     * the one the chain started from.
     */
    this.confirmSaveBaseline(key, ticket, result);
    /*
     * SPOKEN FOR BY A NEWER WRITE ON THE SAME MATCH. This answer is the server's row as it stood
     * after THIS write, and a later one — a second note edit, or a removal — is still on the
     * wire or has already been answered. Inserting it would let whichever answer the network
     * delivered last decide what the note says, so a reader who corrected a note and watched the
     * first version come back would be looking at an intent they had already replaced.
     */
    if (superseded) { this.closeWrite(key, ticket); return result; }
    this.closeWrite(key, ticket);
    const current = this.state.data;
    this.noteLocalWrite();
    // The row as the store holds it NOW, which is not the copy `existing` captured before the
    // optimistic step: a refresh landing while this write was on the wire may have replaced it.
    const held = current
      ? (allSaved(current.savedMatches).find(entry => entry.matchId === matchId) ?? null)
      : null;
    /*
     * WHICH OF THE TWO FIXTURES IS THE OLDER ONE.
     *
     * The answer's fixture is frozen at the instant the server processed the write. With no read
     * applied since this write went out, nothing the store holds for this match can be later
     * than that instant, so the ANSWER is the newer copy and is taken. When a read HAS been
     * applied the two cannot be ordered from here — the snapshot may have been built either side
     * of the write — and the store's copy is kept, because that is the one that can carry a
     * result this write's own transaction never saw. `session` dates this answer against the
     * account and `writesOnKey` against other writes on this match; neither sees a read, which
     * is what `snapshotsApplied` is counted for.
     *
     * THE PRESENCE OF A ROW IS NOT THE TEST. The optimistic step above inserts one for every
     * save made with a fixture, so `held` can be nothing but this write's own guess — built from
     * whatever copy the caller had on screen, which is exactly the copy that can be stale.
     */
    const readLandedUnderneath = this.snapshotsApplied !== snapshotsAtIssue;
    this.set({
      /*
       * A read landed, so the answer speaks for the note and its timestamps and not for the
       * fixture. A note edit is issued while the fixture is live and scoreless; the server
       * processes it and builds its answer around that live copy; the fixture then finishes 3-1
       * and a refresh brings the result in; the answer arrives last. Handing it to `insertSaved`,
       * which files a row by `match.status`, would put the played match back under "In play now"
       * with its final score gone — the symptom `revertSavedMatch` fixes on the failure path,
       * reached here by an edit that worked. A save authors the note, `saved_at` and
       * `updated_at`, so those three are taken and the fixture is left as it stands.
       *
       * No read landed, so the answer is the freshest copy of the fixture anybody here has, and
       * it is taken whole. It is the ONLY way a fixture the reader is looking at can be brought
       * up to date by the save itself: a day page rendered two hours ago still shows the match
       * as scheduled and hands that copy to `options.match`, and the answer to starring it
       * carries the finished score. `insertSaved` re-files the row, so the bucket follows the
       * status it just learned.
       */
      data: current
        ? {
          ...current,
          savedMatches: held && readLandedUnderneath
            ? replaceSaved(current.savedMatches, {
              ...held,
              note: result.note,
              savedAt: result.savedAt,
              updatedAt: result.updatedAt,
            })
            : insertSaved(current.savedMatches, result),
        }
        : current,
      pendingMatchIds: without(this.state.pendingMatchIds, matchId),
    });
    // Saving a fixture that is in play, or one that kicks off in ten minutes, is a reason to
    // start watching that did not exist a moment ago.
    this.syncLivePoll();
    return result;
  };

  /** Unsave a match, optimistically. Unsaving something that was not saved is not an error. */
  unsaveMatch = async (matchId: string): Promise<UnsaveMatchResult> => {
    const session = this.session;
    // The same key `saveMatch` stamps: a removal and a note edit on one match are two writes on
    // the same thing, sharing the outstanding set that orders their answers and the baseline
    // that either one's failure goes back to.
    const key = FavouritesStore.keyFor('match', matchId);
    const ticket = this.issueWrite(key);
    const before = this.state;
    // The row as it stood, captured before the optimistic removal, so a failed removal puts back
    // the reader's own note rather than a bare entry. It is the chain's baseline where this
    // removal is the first write on the match; where it is not, the note edit already on the
    // wire wrote that row optimistically and the baseline opened before it stays.
    const existing = this.savedEntry(matchId);
    this.openSaveBaseline(key, existing);
    const changedData = before.data !== null;
    this.noteLocalWrite();
    if (before.data) {
      this.set({
        data: { ...before.data, savedMatches: removeSaved(before.data.savedMatches, matchId) },
        pendingMatchIds: withId(before.pendingMatchIds, matchId),
      });
    } else {
      this.set({ pendingMatchIds: withId(before.pendingMatchIds, matchId) });
    }

    let result: UnsaveMatchResult;
    try {
      result = await favouritesApi.unsaveMatch(matchId);
    } catch (error) {
      if (this.answerIsStale(session)) throw new DiscardedWrite('failed');
      // A newer write on this match has spoken for it, so putting the row back would undo that
      // newer intent — and where that write is still running, the pending flag this path clears
      // is its flag and not ours.
      if (this.writeSuperseded(key, ticket)) { this.closeWrite(key, ticket); throw error; }
      // Read before `closeWrite`, which drops the baseline once the last write on this match has
      // settled. A null baseline is a statement and is applied: the server holds no save for
      // this match, so the row the optimistic removal took out must stay out.
      const confirmed = this.saveBaseline(key);
      this.closeWrite(key, ticket);
      const current = this.state.data;
      this.noteLocalWrite();
      this.set({
        ...(changedData && current
          ? { data: revertSavedMatch(current, matchId, confirmed) }
          : {}),
        pendingMatchIds: without(this.state.pendingMatchIds, matchId),
      });
      throw error;
    }

    if (this.answerIsStale(session)) throw new DiscardedWrite('applied');
    // Asked before the answer is recorded below, which would otherwise leave this write reading
    // its own ticket in `answeredTicket` as somebody else's.
    const superseded = this.writeSuperseded(key, ticket);
    // The save is gone from the server, so a failure of any write still running on this match
    // must leave the row absent rather than putting back the note this chain opened with.
    this.confirmSaveBaseline(key, ticket, null);
    // Spoken for: the reader has saved this match again since, and that write will state the end
    // result or already has. Removing the row here would carry out an intent they have replaced.
    if (superseded) { this.closeWrite(key, ticket); return result; }
    this.closeWrite(key, ticket);
    const current = this.state.data;
    this.noteLocalWrite();
    /*
     * STATE THE END RESULT; DO NOT ASSUME THE OPTIMISTIC REMOVAL IS STILL STANDING.
     *
     * Clearing the pending flag and nothing else would assume the entry this path removed a
     * moment ago is still gone. A refresh landing between the two — and it is NOT discarded by
     * the read guard, because it was issued after the local removal it would undo — carries a
     * snapshot in which the match is still saved. The removal would then complete, the spinner
     * would go away, and the bookmark the reader successfully deleted would be left sitting on
     * the screen looking saved. `saveMatch` above asserts its end state; this is the same
     * assertion for the other direction.
     *
     * Unconditional, including when `result.removed` is false: "there was nothing to remove" and
     * "it was removed" describe the same end state — the server does not hold this save.
     */
    this.set({
      ...(current ? { data: { ...current, savedMatches: removeSaved(current.savedMatches, matchId) } } : {}),
      pendingMatchIds: without(this.state.pendingMatchIds, matchId),
    });
    // The fixture that was being watched may be the one just removed.
    this.syncLivePoll();
    return result;
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
export const FEED_FOLLOWED_CAP: Record<FeedPhase, number> = { live: 20, unresolved: 8, result: 8, upcoming: 12 };

/** Requests in flight at once while fanning out over the follows. Polite, not fast. */
const FEED_CONCURRENCY = 4;

/**
 * HOW MANY FIXTURES THE KICK-OFF WATCH WILL ASK ABOUT ONE AT A TIME.
 *
 * A Saturday three o'clock can bring a whole followed competition to kick-off in the same minute.
 * Past this many, asking per fixture stops being the cheap option and one rebuild of the feed —
 * at most one request per follow, and it answers for every fixture at once — is fewer requests
 * for a better answer. Six is below the fifteen a full rebuild can cost and above the one or two
 * a kick-off usually means.
 */
const KICKOFF_TARGETED_MAX = 6;

export const feedApi = {
  /** Everything stored for one team, both directions. A pure database read on the backend. */
  async teamFixtures(teamId: string): Promise<Match[]> {
    const { data } = await apiClient.get<{ team: ApiTeam; upcoming?: ApiMatch[]; recent?: ApiMatch[] }>(
      `/api/v1/teams/${encodeURIComponent(teamId)}`);
    return [...(data.upcoming ?? []), ...(data.recent ?? [])].map(mapApiMatch);
  },

  /**
   * ONE fixture, by id. A pure database read: `GET /api/v1/matches/{match_id}` resolves the id
   * and serialises the stored row (`MatchDataService.match_by_id`). It takes no `refresh`
   * parameter and reaches no provider, which is what makes it usable for the kick-off watch
   * below — asking about the two fixtures that are actually starting costs two stored reads,
   * where rebuilding the whole feed costs one per follow, up to fifteen.
   */
  async matchById(matchId: string): Promise<Match> {
    const { data } = await apiClient.get<ApiMatch>(`/api/v1/matches/${encodeURIComponent(matchId)}`);
    return mapApiMatch(data);
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
  /** The interval that re-reads the handful of followed fixtures that are due to kick off. */
  private kickoffPoll: ReturnType<typeof setInterval> | null = null;
  /** The one-shot timer that wakes this store when the next followed fixture is nearly due. */
  private kickoffWake: ReturnType<typeof setTimeout> | null = null;
  /** True while a kick-off sweep is on the wire, so two cannot overlap. */
  private sweeping = false;

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
    const stopWake = onReaderReturns(() => { this.syncWatches(); this.refreshIfStale(); });
    // Following or unfollowing changes what belongs in the feed, and so does signing out. Watching
    // the favourites store is what makes a newly followed team's fixtures appear without a reload.
    const stopFollowing = favouritesStore.subscribe(() => this.onFavouritesChanged());
    const onHidden = () => { if (!tabIsVisible()) this.stopWatches(); };
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onHidden);
    // Same reason as in FavouritesStore: a pause has to stop this fan-out the moment it is asked
    // for, and this one costs a request per follow per minute.
    const stopWatchingPreferences = personalPreferencesStore.subscribe(() => this.syncWatches());
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
    this.stopWatches();
  }

  /** Both reasons this feed re-reads anything, decided together so they cannot disagree. */
  private syncWatches(): void {
    this.syncLivePoll();
    this.syncKickoffWatch();
  }

  private stopWatches(): void {
    this.stopLivePoll();
    this.stopKickoffWatch();
  }

  /**
   * Whether this feed may re-read anything by itself right now.
   *
   * The same four conditions in both watches: somebody is looking at it, the tab is in front,
   * there is a window at all, and the reader has not switched automatic updates off or paused
   * everything optional.
   */
  private mayPoll(): boolean {
    return this.listeners.size > 0 && tabIsVisible() && typeof window !== 'undefined'
      && personalPreferencesStore.isOn('liveUpdates');
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
   * IT IS NOT THE ONLY REASON TO READ. On its own this is gated on the state it would discover —
   * a fixture reached only through a FOLLOW never becomes live here, because nothing looks until
   * something is already live. `syncKickoffWatch` below is the half that closes that.
   */
  private syncLivePoll(): void {
    // `isPlayableNow` and not the stored status: a fixture whose result has not arrived keeps
    // `live` until one does, and polling it every LIVE_REFRESH_MS spends a request, again and
    // again, on a row whose minute stopped moving hours ago. A result that arrives later is picked
    // up by the next ordinary load of the feed.
    const inPlay = this.state.fixtures.some(entry => isPlayableNow(entry.match));
    const shouldPoll = inPlay && this.mayPoll();
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

  /**
   * NOTICING A KICK-OFF FOR A FIXTURE THE READER NEVER SAVED.
   *
   * THE GAP THIS CLOSES. A saved fixture discovers its own kick-off: `FavouritesStore` wakes at
   * the right moment and re-reads (see `savedDueToStart`). A fixture that is in this feed only
   * because the reader follows one of the clubs or the competition had no equivalent, so it sat
   * under "Coming up" through the first half unless the reader happened to leave the tab and come
   * back. Same page, same reader, two different answers depending on how the fixture got there.
   *
   * WHY THIS IS AFFORDABLE WHEN THE OBVIOUS VERSION IS NOT. Cost is the real objection, and a
   * fair one: this store's whole-feed read is a REBUILD, one request per follow, up to fifteen,
   * and running that every two minutes for every pending kick-off is a different order of load
   * for a fixture nobody asked for by name. GRANULARITY IS WHAT MAKES IT CHEAP.
   * `GET /api/v1/matches/{id}` is a stored read of one row, so the fixtures that are actually
   * starting can be asked about directly: the ordinary Tuesday-night kick-off is ONE request,
   * not fifteen. Past
   * `KICKOFF_TARGETED_MAX` at once the arithmetic flips and one rebuild is cheaper, so that is
   * what it does instead.
   *
   * WHAT IS WATCHED, AND WHEN NOTHING IS. Only a fixture the record still says will be played,
   * and only between `KICKOFF_WATCH_LEAD_MS` before its time and `KICKOFF_WATCH_GRACE_MS` after —
   * the same window, from the same helpers, as the saved-match watch, so the two cannot drift.
   * Outside that window the store holds a single one-shot timer and issues nothing at all. It
   * runs only while somebody is subscribed, the tab is in front, and the reader has automatic
   * updates on and nothing paused; the hidden-tab handler and the preference subscription in
   * `attach()` stop it the moment any of that stops being true.
   *
   * STILL BETTER SERVED BY ONE ENDPOINT. A single `GET /api/v1/me/feed`, already written up for
   * the backend's owner above, would make both this and the rebuild one request. This is the
   * honest version of the watch that can be built from the endpoints that exist.
   */
  private syncKickoffWatch(): void {
    this.stopKickoffWatch();
    if (!this.mayPoll()) return;
    const now = Date.now();
    if (this.fixturesDueToStart(now).length > 0) {
      this.kickoffPoll = setInterval(() => {
        if (!tabIsVisible()) return;
        void this.sweepKickoffs();
      }, KICKOFF_REFRESH_MS);
      return;
    }
    // Nothing is due. One timer, no requests, until the next fixture is nearly on.
    const from = nextWatchStart(this.state.fixtures.map(entry => entry.match), now);
    if (from === null) return;
    const delay = Math.min(Math.max(from - now, 250), KICKOFF_WAKE_MAX_MS);
    this.kickoffWake = setTimeout(() => {
      this.kickoffWake = null;
      // A clamped wake finds nothing due and simply re-arms; a real one sweeps.
      if (this.fixturesDueToStart().length > 0) void this.sweepKickoffs();
      else this.syncKickoffWatch();
    }, delay);
  }

  /** Followed fixtures inside their kick-off window, by the rule `isDueToStart` states. */
  private fixturesDueToStart(now: number = Date.now()): FollowedFixture[] {
    return this.state.fixtures.filter(entry => isDueToStart(entry.match, now));
  }

  /**
   * Ask about the fixtures that are starting, and merge what comes back.
   *
   * A fixture whose read FAILS is left exactly as it was and says nothing: this is a background
   * question the reader did not ask, `unreadable` means "a follow we could not read" and this is
   * not one, and an error here would claim something about the fixture that we do not know.
   */
  private async sweepKickoffs(): Promise<void> {
    if (this.sweeping || this.inFlight) return;
    const due = this.fixturesDueToStart();
    if (due.length === 0) { this.syncKickoffWatch(); return; }
    // More of them than a rebuild costs: ask once for everything instead of once for each.
    if (due.length > KICKOFF_TARGETED_MAX) {
      await this.load();
      this.syncKickoffWatch();
      return;
    }

    const session = favouritesStore.sessionId();
    this.sweeping = true;
    let settled: PromiseSettledResult<Match>[];
    try {
      settled = await mapWithLimit(due, FEED_CONCURRENCY, entry => feedApi.matchById(entry.match.id));
    } finally {
      this.sweeping = false;
    }
    // The reader signed out, or somebody else signed in, while these were on the wire. The same
    // rule as everywhere else in this file: their answer is not shown to whoever is here now.
    if (favouritesStore.sessionId() !== session) return;

    const updated = new Map<string, Match>();
    settled.forEach((result, index) => {
      if (result.status !== 'fulfilled') return;
      // The id we asked about, not the one that came back: a resolved alias must still land on
      // the row it was asked for.
      updated.set(due[index].match.id, result.value);
    });
    if (updated.size > 0) {
      this.set({
        fixtures: this.state.fixtures.map(entry => {
          const fresh = updated.get(entry.match.id);
          return fresh ? { ...entry, match: fresh } : entry;
        }),
      });
    }
    // A fixture that has now kicked off belongs to the in-play poll; one that has not is still
    // inside its window and stays with this one, until the grace runs out.
    this.syncWatches();
  }

  private stopKickoffWatch(): void {
    if (this.kickoffPoll !== null) {
      clearInterval(this.kickoffPoll);
      this.kickoffPoll = null;
    }
    if (this.kickoffWake !== null) {
      clearTimeout(this.kickoffWake);
      this.kickoffWake = null;
    }
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
        this.stopWatches();
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
      this.stopWatches();
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
      // Whether anything is in play, or about to be, is only known once the fixtures are in hand.
      this.syncWatches();
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
/**
 * The four questions a returning reader has, in the order they ask them.
 *
 * `unresolved` is the one that is not about football. It holds a fixture whose result passed its
 * deadline and never came: the row still says LIVE or SCHEDULED because that is the last thing a
 * provider said, and putting it under "In play now" would make this page assert, in a heading, a
 * match that finished hours ago. It is not a result either — nobody reported one — so it cannot
 * go under Results, and it certainly is not coming up. It needed a group of its own.
 */
export type FeedPhase = 'live' | 'unresolved' | 'result' | 'upcoming';

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

/**
 * Same rule as `bucketOf`, named for the feed: anything neither in play nor played is still ahead
 * — except that a status past the backend's deadline for a result is no longer evidence of
 * anything, and is sorted by that fact instead.
 *
 * The delay is read before the status precisely because the status is what went wrong: `live` and
 * `scheduled` both survive a result that never arrives, and both then read as confident claims
 * about a match in progress. See src/utils/resultDelay.ts.
 */
function phaseOf(match: Match, now: number = Date.now()): FeedPhase {
  if (resultDelay(match, now)) return 'unresolved';
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
      phase: phaseOf(match, now),
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
    // Most recently due first: the longest-stuck fixture is the least likely to move now.
    unresolved: (a, b) => byTime(a, b, -1),
    result: (a, b) => byTime(a, b, -1),
    upcoming: (a, b) => byTime(a, b, 1),
  };

  return (['live', 'unresolved', 'result', 'upcoming'] as const).map(phase => {
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
