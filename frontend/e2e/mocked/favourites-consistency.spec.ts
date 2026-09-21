import { test, expect, Page, Route, Request } from '@playwright/test';
import {
  ApiMatch, ApiTeamRef, Json, baseMatches, dayPayload, fixtureAt, registerAuthHandler, stubBackend,
} from '../support/api-stub';

/**
 * RACES IN THE FAVOURITES STORE, EACH DRIVEN BY HOLDING ONE RESPONSE OPEN.
 *
 * `src/services/favourites.service.ts` keeps one optimistic store for everything a reader follows
 * and has saved. Every defect proved here is the same shape: a request that was issued while one
 * thing was true, and whose answer was applied after it had stopped being true.
 *
 *   1. A READ THAT OUTLIVES ITS SESSION. `reset()` clears the state and drops the in-flight
 *      HANDLE, but it cannot stop the request. Apply its continuation unconditionally and the
 *      previous reader's saved matches land in the store AFTER they signed out — and, if somebody
 *      else has signed in by then, in that person's session. The failure path is the same hole:
 *      an older read's 503 puts the new session into `error`.
 *   2. A READ OLDER THAN A LOCAL WRITE. A save or a follow applies optimistically and reconciles
 *      against the server's own answer. A read issued BEFORE that write carries a snapshot which
 *      predates it, so applying it silently undoes the reader's action and the star goes back off.
 *   3. A WRITE THAT OUTLIVES ITS SESSION — the same hole as 1, across all six paths: save, unsave
 *      and follow, each with a success and a rollback. Unguarded, a save resolving after a change
 *      of account inserts the previous reader's save row, PRIVATE NOTE INCLUDED, into the new
 *      reader's store, and a rollback that restores `before.data` restores that reader's WHOLE
 *      favourites snapshot. Sections 4 and 5 below.
 *   4. A REFRESH THAT LANDS IN THE MIDDLE OF A WRITE. Not stale by either counter — it was issued
 *      after the local change, so nothing discards it — and it carries the server state from
 *      before the write committed. A success path that only clears the pending flag, assuming its
 *      own optimistic removal still stands, leaves the refresh's copy of the bookmark on screen
 *      after the removal has succeeded; so `unsaveMatch` asserts its end state. Section 6 below.
 *   5. A WRITE APPLIED FOR MORE THAN IT WROTE, in both directions. A save row carries the whole
 *      fixture, which no save writes. Roll back by reinserting the row captured before the write
 *      and a failed NOTE edit rewrites the MATCH: a fixture that finished while the edit was on
 *      the wire returns to the live, scoreless copy the edit started from, and goes back under
 *      "In play now" with it. The SUCCESS path reaches the same hole through the answer, whose
 *      `.match` is frozen at the instant the server processed the write — so the same played
 *      match goes back under "In play now" after an edit that worked perfectly. Section 7 below,
 *      which holds the line in the other direction too: the answer is only the older copy when a
 *      READ landed while the write was on the wire, and with no read in between it is the
 *      freshest fixture the tab has — refusing it would freeze the copy on screen instead.
 *      A follow answer's `ids` is the same shape of payload: section 9.
 *   6. TWO ANSWERS THAT ARRIVE IN THE OPPOSITE ORDER TO THEIR WRITES. Each answer states the
 *      server's world as of ITS OWN processing, which predates every write the server had not
 *      seen yet — so the answer to an earlier unfollow still lists the team a later unfollow has
 *      since removed, and a note edit's answer still carries the text a later edit has replaced.
 *      Let whichever answer lands last win and the reader's last INTENT loses to the network's
 *      last packet. Section 8 below.
 *
 * EVERY TEST HERE IS MOCKED-ONLY, and the names say so. Each one needs a response held open for a
 * known length of time — across a sign-out, across a change of account, or across a refresh —
 * which cannot be arranged against the real backend without slowing it down for everything else
 * using it. e2e/live/* covers the same journeys at their normal speed, where the ordering cannot
 * be chosen and so the race cannot be reached on purpose.
 *
 * COST. Every /api/v1 route is intercepted, so nothing here reaches the network and no provider
 * request is possible. `refresh=true` is never sent by anything this file drives.
 *
 * NOTHING HERE IS A WAGER. Saving and following are bookmarks; no assertion below stakes, scores
 * or settles anything.
 */

/* ------------------------------------------------------------------------------- the readers */

interface Person extends Json {
  user_id: string;
  email: string;
  full_name: string;
  role: 'regular';
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
}

const person = (suffix: string, name: string): Person => ({
  user_id: `00000000-0000-4000-8000-0000000000${suffix}`,
  email: `qa.${name}@predictions-local.dev`,
  full_name: `QA ${name}`,
  role: 'regular',
  is_active: true,
  is_verified: true,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-05T09:00:00Z',
});

/** Two different people on one machine. The point of half this file is that they stay different. */
const FIRST = person('c1', 'First');
const SECOND = person('c2', 'Second');

/**
 * Opaque strings that never leave the browser context. The stub accepts anything and no real
 * backend is contacted, so these are not credentials and unlock nothing.
 */
const ACCESS_TOKEN = 'e2e-consistency-access-token';
const REFRESH_TOKEN = 'e2e-consistency-refresh-token';

/** Mirrors TOKEN_STORAGE_KEYS in src/services/api-client.ts. */
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

/* -------------------------------------------------------------------------- the stubbed world */

/**
 * Two captured fixtures with different clubs in them, so "whose saved match is this?" can be
 * answered by reading the screen.
 */
const FIXTURE_ONE = baseMatches()[0];
const FIXTURE_TWO = baseMatches().find(
  match => (match.home as ApiTeamRef).name !== (FIXTURE_ONE.home as ApiTeamRef).name,
) as ApiMatch;
const CLUB_ONE = (FIXTURE_ONE.home as ApiTeamRef).name;
const CLUB_TWO = (FIXTURE_TWO.home as ApiTeamRef).name;
const TEAM = FIXTURE_ONE.home as ApiTeamRef;
/** A second club, so two unfollows can be told apart on screen and in the stub's rows. */
const TEAM_OTHER = FIXTURE_TWO.home as ApiTeamRef;

/**
 * FOCUS_REFRESH_MIN_AGE_MS in src/services/favourites.service.ts, mirrored.
 *
 * It is a coalescing guard: a snapshot younger than this is not re-read when the tab comes back,
 * because `focus` and `visibilitychange` routinely arrive as a pair. Waiting it out is what makes
 * "come back to the tab" a reliable way to put a background read on the wire.
 */
const FOCUS_GUARD_MS = 5_000;

interface SavedRow {
  match: ApiMatch;
  savedAt: string;
  /** The reader's own private note on this save, exactly as the API stores and returns one. */
  note: string | null;
}

/**
 * The first reader's private note.
 *
 * A save row carries one, `GET /me/favourites` returns it and `PUT /me/saved-matches/{id}` returns
 * it again, so it travels inside every payload the write tests hold open. It is the single most
 * private thing this store handles and therefore the sharpest probe for a leak: a string that can
 * only have come from the first reader's row, searched for on the second reader's screen.
 */
const FIRST_NOTE = 'Leaving work at five to be home for kick-off.';

/**
 * A note, the edit that replaces it, and the correction that replaces THAT.
 *
 * Three distinct strings, because the last two sections turn on exactly which of them is on the
 * screen when everything has settled: one where a failed edit must leave no trace, and one where
 * only the later of two edits may stand however their answers arrive.
 */
const NOTE_BEFORE = 'Check the late team news before this one.';
const NOTE_EDITED = 'Watch the left back, booked twice this month.';
const NOTE_CORRECTED = 'It is the right back to watch, not the left.';

/**
 * A fixture behind a follow rather than a save.
 *
 * Built at call time and placed two days out so it falls inside the feed's window whichever day
 * the suite is run on, with clubs of its own so it can never be confused with a saved row.
 */
const followedFixture = (): ApiMatch =>
  fixtureAt(new Date(Date.now() + 2 * 86_400_000).toISOString(), 'Marshgate United', 'Sandhill Rovers');

/** One person's rows on the server: what they saved and what they follow. */
class Reader {
  saved = new Map<string, SavedRow>();

  teamIds: string[] = [];

  /** The note this reader's save rows carry when a test seeds one. */
  note: string | null = null;

  constructor(readonly person: Person) {}

  /**
   * Save `match`, or edit the note on a save that already exists.
   *
   * `note` follows the API's own rule rather than being normalised away: omitted leaves the
   * stored note alone, and null or '' clears it. A stub that ignored the body and always wrote
   * the reader's seeded note could not tell one note edit from another, which is exactly what
   * the out-of-order test has to distinguish.
   */
  save(match: ApiMatch, note?: string | null): void {
    const existing = this.saved.get(match.id);
    this.saved.set(match.id, {
      match,
      savedAt: existing?.savedAt ?? new Date().toISOString(),
      note: note === undefined ? (existing?.note ?? this.note) : (note || null),
    });
  }
}

/** A read the test is holding open, and the handle that lets it land. */
interface HeldRead {
  /** Resolves when the application has actually issued the read and the stub is sitting on it. */
  arrived: Promise<void>;
  /** Let it land, with `status` 200 for a snapshot or anything else for a failure. */
  release: (status?: number) => void;
}

/**
 * One response the test is sitting on, in the two separate moments a response really has.
 *
 * `released` is when the stub server PROCESSES the request — applies it to its rows and builds
 * the answer — and `delivered` is when that answer goes on the wire. Most tests here need only
 * the first and let the second happen at once. An out-of-order test needs both, because the
 * defect it proves requires one write to be processed BEFORE another and answered AFTER it, and
 * a single gate can only say "nothing has happened yet" or "everything has". `processed` is how
 * the stub tells the test the first moment has actually passed, so the next write can be
 * released knowing for certain that it is the second the server sees.
 */
interface Hold {
  announce: () => void;
  released: Promise<number>;
  delivered: Promise<void>;
  processed: () => void;
}

/**
 * The stand-in for the signed-in half of the backend.
 *
 * It is a little server rather than a fixed payload because every assertion here is about WHEN an
 * answer arrives relative to something else. A frozen payload cannot hold a response open.
 */
class World {
  readonly first = new Reader(FIRST);

  readonly second = new Reader(SECOND);

  /** Who `/auth/me` currently answers as, or nobody. */
  signedIn: Reader | null = null;

  /** Every `GET /api/v1/me/favourites` the application issued, answered or not. */
  favouriteReads = 0;

  /** Every `GET /api/v1/teams/{id}`: the follow fan-out, which only a followed team causes. */
  teamReads = 0;

  /** Teams `GET /api/v1/teams/{id}` knows about. */
  knownTeams: ApiTeamRef[] = [TEAM];

  /** What `GET /api/v1/teams/{id}` reports that team has coming up. Empty unless a test sets it. */
  teamFixtures: ApiMatch[] = [];

  /**
   * The stub's stored fixture rows — the ones the backend's scheduler keeps current.
   *
   * A captured fixture is the default for every id, so a test that does not care about kick-offs
   * and results carries on as before. A test that does puts its own row here and moves it on.
   */
  private fixtures = new Map<string, ApiMatch>();

  private hold: Hold | null = null;

  private writeHold: Hold | null = null;

  /** Holds queued for a particular id, in the order the writes on it will arrive. */
  private writeHoldsById = new Map<string, Hold[]>();

  arm(hold: Hold): void {
    this.hold = hold;
  }

  /** The armed hold, once. A second read is answered at once rather than queued behind the first. */
  takeHold(): Hold | null {
    const held = this.hold;
    this.hold = null;
    return held;
  }

  armWrite(hold: Hold): void {
    this.writeHold = hold;
  }

  /**
   * Queue a hold for the next write on `id`.
   *
   * Keyed, and a queue rather than a slot, because both defects in this section need more than
   * one write open at once: two ids held apart so their answers can be released in the reverse
   * order, and two writes on ONE id so the older answer can be released last.
   */
  armWriteOn(id: string, hold: Hold): void {
    const queue = this.writeHoldsById.get(id) ?? [];
    queue.push(hold);
    this.writeHoldsById.set(id, queue);
  }

  /** The hold this write should wait on: the one queued for its id, else the unkeyed one. */
  takeWriteHold(id: string): Hold | null {
    const queue = this.writeHoldsById.get(id);
    if (queue && queue.length > 0) return queue.shift() ?? null;
    const held = this.writeHold;
    this.writeHold = null;
    return held;
  }

  /** Put a fixture into the stored rows, in place of the captured copy of it. */
  storeFixture(match: ApiMatch): void {
    this.fixtures.set(match.id, match);
  }

  /** The stored row for one fixture: the captured copy unless a test has moved it on. */
  fixtureById(matchId: string): ApiMatch | null {
    return this.fixtures.get(matchId) ?? baseMatches().find(match => match.id === matchId) ?? null;
  }

  /**
   * What the backend's scheduler does to a stored fixture, and the only thing that moves one
   * between the saved-match buckets.
   *
   * It reaches every reader's save row for that fixture, because a save row is a view of the
   * stored fixture rather than a copy of it — which is precisely why a rollback that puts a
   * captured save row back puts an old FIXTURE back with it.
   */
  schedulerMoves(matchId: string, patch: Partial<ApiMatch>): void {
    const stored = this.fixtureById(matchId);
    if (!stored) throw new Error(`the stub holds no fixture ${matchId}`);
    const moved = { ...stored, ...patch };
    this.fixtures.set(matchId, moved);
    [this.first, this.second].forEach(reader => {
      const row = reader.saved.get(matchId);
      if (row) row.match = moved;
    });
  }

  readerFor(email: string): Reader | null {
    if (email === FIRST.email) return this.first;
    if (email === SECOND.email) return this.second;
    return null;
  }
}

function makeHold(): { hold: Hold; held: HeldRead } {
  let announce!: () => void;
  const arrived = new Promise<void>(resolve => { announce = resolve; });
  let unlock!: (status: number) => void;
  const released = new Promise<number>(resolve => { unlock = resolve; });
  return {
    // Processing and delivery are the same moment for a one-gate hold: the answer goes out as
    // soon as the server has built it, which is what an ordinary slow response looks like.
    hold: { announce, released, delivered: Promise.resolve(), processed: () => undefined },
    held: { arrived, release: (status = 200) => unlock(status) },
  };
}

function holdNextFavouritesRead(world: World): HeldRead {
  const { hold, held } = makeHold();
  world.arm(hold);
  return held;
}

/**
 * Hold the next WRITE — a save, an unsave or a follow — open.
 *
 * THE EFFECT LANDS WHEN THE HOLD IS RELEASED, NOT WHEN THE REQUEST ARRIVES, and that is the
 * opposite of the read hold a few lines up on purpose. A read is answered from the state the
 * server held when the request arrived, so its body is built then. A write that is still in
 * flight is one the server has not committed, so anything READ in the meantime must still see
 * the old value — which is exactly the window a refresh lands in, and the whole of section 6.
 * Releasing with a status other than 200 leaves the effect unapplied, the way a write that
 * failed leaves it.
 */
function holdNextWrite(world: World): HeldRead {
  const { hold, held } = makeHold();
  world.armWrite(hold);
  return held;
}

/**
 * A write held open by the id in its path, with its processing and its answer released apart.
 *
 * This is how an ordering is CHOSEN rather than hoped for. Two of these, committed in one order
 * and delivered in the other, put the server and the browser into exactly the disagreement the
 * defect needs — every time, on any machine, at any speed.
 */
interface OrderedWrite {
  /** Resolves when the stub is sitting on the request. */
  arrived: Promise<void>;
  /** Let the server apply it. Resolves once it has, and its answer exists. */
  commit: (status?: number) => Promise<void>;
  /** Let that answer go on the wire. */
  deliver: () => void;
}

function holdWriteOn(world: World, id: string): OrderedWrite {
  let announce!: () => void;
  const arrived = new Promise<void>(resolve => { announce = resolve; });
  let unlock!: (status: number) => void;
  const released = new Promise<number>(resolve => { unlock = resolve; });
  let openTheWire!: () => void;
  const delivered = new Promise<void>(resolve => { openTheWire = resolve; });
  let applied!: () => void;
  const wasApplied = new Promise<void>(resolve => { applied = resolve; });
  world.armWriteOn(id, { announce, released, delivered, processed: applied });
  return {
    arrived,
    commit: (status = 200) => { unlock(status); return wasApplied; },
    deliver: () => openTheWire(),
  };
}

/** What a stubbed write endpoint has to know: how it settles, and when it may answer. */
interface WriteGate {
  /** 200 unless the test released this write as a failure. */
  status: number;
  /** Announce that the write has been applied, then wait for the go-ahead to answer. */
  answer: () => Promise<void>;
}

/** Wait on whatever hold is armed for `id`. An unheld write settles and answers immediately. */
async function heldWrite(world: World, id: string): Promise<WriteGate> {
  const hold = world.takeWriteHold(id);
  if (!hold) return { status: 200, answer: () => Promise.resolve() };
  hold.announce();
  const status = await hold.released;
  return { status, answer: () => { hold.processed(); return hold.delivered; } };
}

const savedEntry = (row: SavedRow): Json => ({
  match_id: row.match.id,
  note: row.note,
  saved_at: row.savedAt,
  updated_at: row.savedAt,
  match: row.match,
});

function savedMatchesPayload(reader: Reader): Json {
  const rows = Array.from(reader.saved.values());
  const live = rows.filter(row => row.match.status === 'live' || row.match.status === 'halftime');
  const finished = rows.filter(row => row.match.status === 'finished');
  const upcoming = rows.filter(row => !live.includes(row) && !finished.includes(row));
  return {
    upcoming: upcoming.map(savedEntry),
    live: live.map(savedEntry),
    finished: finished.map(savedEntry),
    counts: {
      upcoming: upcoming.length,
      live: live.length,
      finished: finished.length,
      total: rows.length,
    },
  };
}

function favouritesPayload(world: World, reader: Reader): Json {
  return {
    teams: world.knownTeams.filter(team => reader.teamIds.includes(team.id)),
    leagues: [],
    team_ids: [...reader.teamIds],
    league_ids: [],
    unresolved: { teams: [], leagues: [] },
    saved_matches: savedMatchesPayload(reader),
    limits: { teams: 10, leagues: 5 },
  };
}

/**
 * Sign-in, sign-out and `/auth/me`, keyed on the address that was typed into the form.
 *
 * Two accounts share one browser here, so the session cannot be a boolean: the sign-in that
 * matters most in this file is the one where a DIFFERENT person arrives on the same machine.
 */
async function stubAuth(page: Page, world: World): Promise<void> {
  const handler = async (route: Route, request: Request): Promise<void> => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/auth/, '');

    if (path === '/login' || path === '/register') {
      const body = (request.postDataJSON() ?? {}) as { email?: string };
      const reader = world.readerFor(body.email ?? '');
      if (!reader) return json({ detail: 'Incorrect email or password' }, 401);
      world.signedIn = reader;
      return json({
        access_token: ACCESS_TOKEN,
        refresh_token: REFRESH_TOKEN,
        token_type: 'bearer',
        user: reader.person,
      });
    }
    if (path === '/logout') {
      world.signedIn = null;
      return json({ message: 'Logged out successfully' });
    }
    if (path === '/me') {
      return world.signedIn
        ? json(world.signedIn.person)
        : json({ detail: 'Not authenticated' }, 401);
    }
    if (path === '/refresh') {
      return world.signedIn
        ? json({ access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN, token_type: 'bearer' })
        : json({ detail: 'Invalid refresh token' }, 401);
    }
    return json({ detail: 'Not found' }, 404);
  };

  registerAuthHandler(page, handler);
  await page.route('**/api/v1/auth/**', handler);
}

/**
 * The signed-in endpoints.
 *
 * Registered AFTER stubBackend so Playwright reaches these first: stubBackend answers anything it
 * does not model with an empty object, and an empty object on `PUT /me/saved-matches/{id}` is a
 * payload the mapper cannot read.
 */
async function stubAccount(page: Page, world: World): Promise<void> {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  await page.route('**/api/v1/me/**', async (route: Route, request: Request) => {
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1\/me/, '');
    const method = request.method();

    // Counted before anything else: the question these tests ask most often is whether the
    // application issued a request at all, and a 401 is still a request.
    if (path === '/favourites') world.favouriteReads += 1;

    const reader = world.signedIn;
    // Every /me endpoint is authenticated. Answering a tokenless request would let a sign-out
    // failure look like a success. This is the 401 the real backend gives an anonymous caller.
    if (!reader) return json(route, { detail: 'Not authenticated' }, 401);

    if (path === '/favourites') {
      /*
       * THE BODY IS COMPUTED NOW, NOT WHEN THE HOLD IS RELEASED.
       *
       * That is the whole fidelity of this file. A held read is a read the server answered from
       * the state it held at the moment the request arrived; building the payload after the
       * release would model a read that answered from the future, which is the opposite of the
       * race under test.
       */
      const body = favouritesPayload(world, reader);
      const hold = world.takeHold();
      if (hold) {
        hold.announce();
        const status = await hold.released;
        if (status !== 200) return json(route, { detail: 'Simulated upstream failure' }, status);
      }
      return json(route, body);
    }

    if (path === '/saved-matches') return json(route, savedMatchesPayload(reader));

    const savedMatch = /^\/saved-matches\/(.+)$/.exec(path);
    if (savedMatch) {
      const matchId = decodeURIComponent(savedMatch[1]);
      if (method === 'PUT') {
        // The STORED row, not the captured one: a test that has moved this fixture on to a
        // result must have the save row follow it, the way the real save row does.
        const known = world.fixtureById(matchId);
        if (!known) return json(route, { detail: 'Match not found' }, 404);
        const gate = await heldWrite(world, matchId);
        if (gate.status !== 200) {
          await gate.answer();
          return json(route, { detail: 'Simulated upstream failure' }, gate.status);
        }
        const body = (request.postDataJSON() ?? {}) as { note?: string | null };
        const created = !reader.saved.has(matchId);
        reader.save(known, 'note' in body ? (body.note ?? null) : undefined);
        const row = reader.saved.get(matchId) as SavedRow;
        const answer = { ...savedEntry(row), created };
        await gate.answer();
        return json(route, answer);
      }
      if (method === 'DELETE') {
        const gate = await heldWrite(world, matchId);
        if (gate.status !== 200) {
          await gate.answer();
          return json(route, { detail: 'Simulated upstream failure' }, gate.status);
        }
        const removed = reader.saved.delete(matchId);
        await gate.answer();
        return json(route, { match_id: matchId, removed });
      }
    }

    const follow = /^\/favourites\/(teams|leagues)\/(.+)$/.exec(path);
    if (follow) {
      const id = decodeURIComponent(follow[2]);
      const following = method === 'PUT';
      const gate = await heldWrite(world, id);
      if (gate.status !== 200) {
        await gate.answer();
        return json(route, { detail: 'Simulated upstream failure' }, gate.status);
      }
      const before = [...reader.teamIds];
      reader.teamIds = following
        ? (before.includes(id) ? before : [...before, id])
        : before.filter(entry => entry !== id);
      /*
       * THE LIST IS BUILT HERE, WHEN THIS WRITE IS PROCESSED, AND NOT WHEN IT IS ANSWERED.
       *
       * That is the whole of the out-of-order defect below. The real endpoint serialises the
       * follow list as it stands at the end of ITS OWN transaction, so the answer to an earlier
       * write still contains a follow a later write has since removed. Building the body at
       * delivery time would quietly repair the very thing under test.
       */
      const answer = {
        kind: follow[1] === 'teams' ? 'team' : 'league',
        id,
        following,
        changed: before.length !== reader.teamIds.length,
        ids: [...reader.teamIds],
        limit: 10,
      };
      await gate.answer();
      return json(route, answer);
    }

    return json(route, {});
  });

  // `GET /api/v1/teams/{id}`: the team page, and the follow fan-out. Registered by regex so
  // `/teams/search`, which the header search depends on, keeps going to stubBackend.
  await page.route(/\/api\/v1\/teams\/(?!search)[^/?#]+$/, async (route: Route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '');
    world.teamReads += 1;
    const team = world.knownTeams.find(entry => entry.id === id) ?? null;
    if (!team) return json(route, { detail: 'Team not found' }, 404);
    return json(route, { team, upcoming: world.teamFixtures, recent: [] });
  });
}

async function stubWorld(page: Page, world: World): Promise<void> {
  // `GET /api/v1/matches/{id}` answers from the same stored rows the save rows are views of, so
  // the match page and the dashboard cannot disagree about whether a fixture has finished.
  await stubBackend(page, { day: iso => dayPayload(iso), matchById: id => world.fixtureById(id) });
  await stubAuth(page, world);
  await stubAccount(page, world);
}

/**
 * Start the document already signed in as `reader`.
 *
 * These tests are not about how a session is created — e2e/mocked/journey-proof.spec.ts proves
 * that — so the token is seeded the way e2e/support/auth.ts seeds it and the application still
 * boots the session itself through `/auth/me`.
 */
async function startSignedIn(page: Page, world: World, reader: Reader): Promise<void> {
  world.signedIn = reader;
  await page.addInitScript(([accessKey, refreshKey, access, refresh]) => {
    window.localStorage.setItem(accessKey, access);
    window.localStorage.setItem(refreshKey, refresh);
  }, [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, ACCESS_TOKEN, REFRESH_TOKEN]);
}

/* ------------------------------------------------------------------------------ small helpers */

/**
 * Come back to this tab.
 *
 * Both events, because `onReaderReturns` listens for both and neither alone covers both ways back:
 * switching browser tabs fires `visibilitychange`, switching applications fires `focus`.
 */
async function returnToTheTab(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.dispatchEvent(new Event('focus'));
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

/**
 * Sign out the way a reader has to: through the account menu in the header.
 *
 * Found by its popup role rather than its name, because the name changes with the width — below
 * Tailwind's `sm` the visible first name is not rendered and the button falls back to an `sr-only`
 * "Account menu".
 */
async function signOutThroughTheHeader(page: Page): Promise<void> {
  const accountMenu = page.locator('header button[aria-haspopup]').last();
  await expect(accountMenu, 'the account menu must be reachable at this width').toBeVisible();
  await accountMenu.click();
  const signOut = page.getByRole('menuitem', { name: /sign out/i });
  await expect(signOut).toBeVisible();
  await signOut.click();
  await page.waitForURL('**/login**');
  /*
   * Wait for the sign-in form to be COMMITTED, not merely for the address to change.
   *
   * `waitForURL` resolves on the history entry; React renders the new screen a moment later, and
   * on that screen `useFavourites` runs its signed-out branch. Releasing a held response inside
   * that window lands it before anything has had the chance to react to the sign-out, which is a
   * narrower and luckier race than the one these tests are about — a reader whose request takes a
   * second is well past it. Every test here therefore starts from a settled signed-out screen.
   */
  await expect(page.getByRole('heading', { name: /sign in to your account/i })).toBeVisible();
  await page.waitForTimeout(250);
}

/** Sign in through the real form, as a second person on this machine would. */
async function signInThroughTheForm(page: Page, who: Person): Promise<void> {
  await expect(page).toHaveURL(/\/login/);
  await page.locator('input[type="email"], input[name="email"]').first().fill(who.email);
  await page.locator('input[type="password"]').first().fill('local-only-e2e-fixture');
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

/**
 * Whatever the toast layer currently has on screen.
 *
 * MATCHED BY THE CONTAINER, NOT BY ROLE. react-hot-toast marks its own fixed-position container
 * `data-rht-toaster` and puts one child in it per live toast and nothing else, so every element
 * this matches is a toast and every toast is matched — including a `toast.custom`, whose own
 * markup decides what role it carries, if any.
 *
 * THE ATTRIBUTES A TOAST CARRIES ARE NOT ENOUGH TO RECOGNISE ONE BY. `role="status"` with
 * `aria-live="polite"` is the correct marking for any line that announces itself, and the
 * application uses it: `RouteLoading` in src/App.tsx announces a slow route chunk exactly that
 * way, with the testid on its wrapper rather than on the announcing element itself. A locator
 * built from those two attributes therefore matches a route spinner, and the wait below, for the
 * toast layer to be empty, would sometimes be waiting for a chunk to arrive instead.
 */
const toastsOnScreen = (page: Page) => page.locator('[data-rht-toaster] > *');

/**
 * Walk to the dashboard through the header menu rather than `page.goto`.
 *
 * `page.goto` is a full document load, which would throw away the in-flight request every test in
 * this file is holding open. A reader gets there by pressing a link, and so does this.
 *
 * THE TOAST LAYER IS WAITED OUT FIRST, BECAUSE IT SITS ON THIS BUTTON. The Toaster is fixed to
 * the top right, and at the 390px this file also runs at, the toast raised by the sign-out a
 * moment earlier spans the account menu button: measured there, `elementFromPoint` at the
 * button's centre returns the toast, not the button. Playwright's own actionability check then
 * retries the click blindly until the toast's four seconds are up, and spends the test's budget
 * doing it — which is what a full run under load turns into an interception failure here.
 * Waiting for the toast by name costs the same time and says what it is waiting for. The overlap
 * itself is the Toaster's placement in src/main.tsx, which is not this file's to change.
 *
 * THE CONTAINER IS ASSERTED BEFORE ITS CHILDREN ARE COUNTED. "No toasts on screen" and "the
 * selector matches nothing at all" are the same result to `toHaveCount(0)`, so a toast layer this
 * file could no longer find would turn the wait into a no-op that passes — and the interception
 * it exists to prevent would come back as an occasional failure somewhere else. One toast layer
 * is mounted for the whole application, in src/main.tsx.
 */
async function goToDashboardThroughTheHeader(page: Page): Promise<void> {
  await expect(page.locator('[data-rht-toaster]'),
    'the toast layer must be findable, or the wait below is a no-op').toHaveCount(1);
  await expect(toastsOnScreen(page),
    'a toast covering the header would intercept the click below').toHaveCount(0);
  const accountMenu = page.locator('header button[aria-haspopup]').last();
  await expect(accountMenu, 'the account menu must be reachable at this width').toBeVisible();
  await accountMenu.click();
  await page.getByRole('menuitem', { name: /^dashboard$/i }).click();
  await page.waitForURL('**/dashboard');
}

/** Let a released response be received and React finish with it. */
async function landed(page: Page, release: () => void): Promise<void> {
  const response = page.waitForResponse(r => r.url().includes('/api/v1/me/favourites'));
  release();
  await response;
  await page.waitForTimeout(500);
}

/** The same for a held WRITE: `part` is enough of the path to recognise it by. */
async function landedWrite(page: Page, part: string, release: () => void): Promise<void> {
  const response = page.waitForResponse(r => r.url().includes(part));
  release();
  await response;
  await page.waitForTimeout(500);
}

const SAVE_PATH = '/api/v1/me/saved-matches/';
const FOLLOW_PATH = '/api/v1/me/favourites/teams/';

const savedRows = (page: Page) => page.getByTestId('saved-match');
const savedRow = (page: Page, matchId: string) =>
  page.locator(`[data-testid="saved-match"][data-match-id="${matchId}"]`);
const starIn = (page: Page, matchId: string) =>
  savedRow(page, matchId).getByTestId('save-match-button');

/**
 * Somebody else arrives on this machine while the first reader's write is still on the wire.
 *
 * One slow request and two taps: it is not an exotic ordering, and it is the one that decides
 * whether a private note can cross from one account to another.
 */
async function anotherReaderTakesOver(page: Page, who: Person): Promise<void> {
  await signOutThroughTheHeader(page);
  await signInThroughTheForm(page, who);
  await goToDashboardThroughTheHeader(page);
}

/** Wait out the coalescing guard so that coming back to the tab really issues a read. */
async function letTheSnapshotGoStale(page: Page): Promise<void> {
  await page.waitForTimeout(FOCUS_GUARD_MS + 500);
}

/** Come back to the tab and wait for the refresh it causes to have landed and rendered. */
async function refreshThroughTheTab(page: Page): Promise<void> {
  const response = page.waitForResponse(r => r.url().includes('/api/v1/me/favourites'));
  await returnToTheTab(page);
  await response;
  await page.waitForTimeout(500);
}

/* ------------------------------------------------------ 1. a read that outlives its session */

test('MOCKED-ONLY: a favourites read held open across sign-out is discarded, not kept for the next session', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const held = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await held.arrived;
  await expect(page.getByTestId('feed-loading'), 'the read under test must really be held open')
    .toBeVisible();

  await signOutThroughTheHeader(page);

  /*
   * What the server holds moves on while nobody is signed in — the reader removed this save from
   * their phone. The held response therefore carries a snapshot that is wrong in a way the screen
   * can show, which is what makes the assertions below about DATA and not only about timing.
   */
  world.first.saved.clear();
  await landed(page, () => held.release());

  // NO DATA on the signed-out screen, and nothing said about a failure either.
  await expect(page.getByTestId('saved-matches')).toHaveCount(0);
  await expect(savedRows(page)).toHaveCount(0);
  expect(await page.locator('body').innerText()).not.toContain(CLUB_ONE);

  // The same person signs back in. A response kept from the previous session is not just a stale
  // pixel: the store would still be `ready`, so `ensureLoaded()` finds nothing to do and the
  // dashboard is built from it WITHOUT reading anything — a match the server no longer holds,
  // presented as what this reader has saved.
  const readsBeforeSignIn = world.favouriteReads;
  await signInThroughTheForm(page, FIRST);
  await goToDashboardThroughTheHeader(page);

  expect(world.favouriteReads,
    'a new session must read the reader\'s favourites, not inherit the discarded response')
    .toBeGreaterThan(readsBeforeSignIn);
  await expect(page.getByTestId('saved-matches-empty'),
    'the server holds no saves for this reader, so that is what the feed must say').toBeVisible();
  await expect(savedRows(page).filter({ hasText: CLUB_ONE })).toHaveCount(0);
});

test('MOCKED-ONLY: a favourites read discarded at sign-out leaves no focus watcher behind it', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const held = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await held.arrived;

  await signOutThroughTheHeader(page);
  const readsAtSignOut = world.favouriteReads;

  await landed(page, () => held.release());

  /*
   * A response that is applied after sign-out does not only leave data behind: its continuation
   * calls `watchForReturns()` and `syncLivePoll()` as well, re-arming both for a session that
   * has ended. The reader is gone; every request that watcher makes can only ever be a 401 sent
   * on their behalf.
   */
  await page.waitForTimeout(FOCUS_GUARD_MS + 1_000);
  await returnToTheTab(page);
  await page.waitForTimeout(700);
  expect(world.favouriteReads,
    'a signed-out tab coming back to the front must not re-request the previous reader\'s favourites')
    .toBe(readsAtSignOut);
});

/* ---------------------------------------------- 2. a read that outlives the account it read for */

test('MOCKED-ONLY: a favourites read from the previous account does not land in the next account\'s session', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  world.second.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const held = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await held.arrived;

  // A different person signs in on the same machine while the first one's read is still on the
  // wire. This is the ordering that leaks data across people, and it is quicker than it sounds:
  // one slow request and two taps.
  await signOutThroughTheHeader(page);
  await signInThroughTheForm(page, SECOND);
  await goToDashboardThroughTheHeader(page);
  await expect(savedRows(page).filter({ hasText: CLUB_TWO }),
    'the second reader\'s own feed must be on screen before the stale read lands').toHaveCount(1);

  await landed(page, () => held.release());

  await expect(savedRows(page).filter({ hasText: CLUB_ONE }),
    'the first reader\'s saved match must never appear inside the second reader\'s session')
    .toHaveCount(0);
  await expect(savedRows(page).filter({ hasText: CLUB_TWO }),
    'and the second reader\'s own saved match must still be there').toHaveCount(1);
  await expect(page.getByTestId('saved-matches-failed')).toHaveCount(0);
});

test('MOCKED-ONLY: a favourites read that FAILS after the account changed does not fail the new session', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  world.second.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const held = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await held.arrived;

  await signOutThroughTheHeader(page);
  await signInThroughTheForm(page, SECOND);
  await goToDashboardThroughTheHeader(page);
  await expect(savedRows(page).filter({ hasText: CLUB_TWO })).toHaveCount(1);

  // The catch branch has the same hole as the success branch: an older read's failure was written
  // into whatever session happened to be current when it arrived.
  await landed(page, () => held.release(503));

  await expect(page.getByTestId('saved-matches-failed'),
    'a read that belonged to somebody else\'s session must not put this one into error')
    .toHaveCount(0);
  await expect(savedRows(page).filter({ hasText: CLUB_TWO })).toHaveCount(1);
  expect(await page.locator('body').innerText()).not.toMatch(/feed could not be loaded/i);
});

/* ------------------------------------------------- 3. a read older than the reader's own write */

test('MOCKED-ONLY: a favourites read that predates a save does not undo the save', async ({ page }) => {
  const world = new World();
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'false');

  // Put a background refresh on the wire the way the application really puts one there — by the
  // reader coming back to the tab — and hold it open.
  await page.waitForTimeout(FOCUS_GUARD_MS + 500);
  const held = holdNextFavouritesRead(world);
  await returnToTheTab(page);
  await held.arrived;
  const readsWhileHeld = world.favouriteReads;

  await star.click();
  await expect(star).toHaveAttribute('data-saved', 'true');
  await expect(star).toHaveAttribute('data-pending', 'false');
  expect(world.first.saved.size, 'the save really reached the server').toBe(1);

  await landed(page, () => held.release());

  await expect(star, 'a snapshot older than the save must not put the control back to unsaved')
    .toHaveAttribute('data-saved', 'true');
  // Discarded, and then read again: the store owes the reader the server's current answer, not
  // just the absence of a wrong one.
  expect(world.favouriteReads,
    'a discarded read must be replaced by a fresh one, not silently dropped')
    .toBeGreaterThan(readsWhileHeld);
  await expect(star).toHaveAttribute('data-saved', 'true');
});

test('MOCKED-ONLY: a favourites read that predates a follow does not undo the follow', async ({ page }) => {
  const world = new World();
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/teams/${TEAM.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('follow-button').first();
  await expect(star).toHaveAttribute('data-following', 'false');

  await page.waitForTimeout(FOCUS_GUARD_MS + 500);
  const held = holdNextFavouritesRead(world);
  await returnToTheTab(page);
  await held.arrived;

  await star.click();
  await expect(star).toHaveAttribute('data-following', 'true');
  await expect(star).toHaveAttribute('data-pending', 'false');
  expect(world.first.teamIds, 'the follow really reached the server').toEqual([TEAM.id]);

  await landed(page, () => held.release());

  await expect(star, 'a snapshot older than the follow must not put the control back')
    .toHaveAttribute('data-following', 'true');
});

test('MOCKED-ONLY: a favourites read that predates an unfollow does not reinstate it', async ({ page }) => {
  const world = new World();
  world.first.teamIds = [TEAM.id];
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/teams/${TEAM.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('follow-button').first();
  await expect(star).toHaveAttribute('data-following', 'true');

  await page.waitForTimeout(FOCUS_GUARD_MS + 500);
  const held = holdNextFavouritesRead(world);
  await returnToTheTab(page);
  await held.arrived;

  await star.click();
  await expect(star).toHaveAttribute('data-following', 'false');
  await expect(star).toHaveAttribute('data-pending', 'false');
  expect(world.first.teamIds, 'the unfollow really reached the server').toEqual([]);

  await landed(page, () => held.release());

  await expect(star, 'a snapshot older than the unfollow must not put the follow back')
    .toHaveAttribute('data-following', 'false');
});

/* --------------------------------------- 4. a write that outlives the account that issued it */

/**
 * SIX PATHS, AND EVERY ONE OF THEM USED TO APPLY UNCONDITIONALLY.
 *
 * `saveMatch`, `unsaveMatch` and `toggleFollow` each have a success path and a rollback, and none
 * of the six checked whose session the answer belonged to. The successes wrote the previous
 * reader's server row into the new reader's store — for a save, that row carries their PRIVATE
 * NOTE. The rollbacks were worse: every one of them restored `before.data`, the whole favourites
 * snapshot captured before the write went out, so a failed write in a session that had ended put
 * one reader's entire saved-and-followed state into another's.
 *
 * Each test below starts the write as the first reader, lets a second reader sign in on the same
 * machine while it is in flight, and then releases it. Nothing of the first reader's may appear,
 * and the second reader's own state must be exactly as they left it.
 */

test('MOCKED-ONLY: a SAVE released after another account signs in does not put the first reader\'s row — or their private note — into the second\'s', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  // BOTH readers have this fixture saved. That is what makes the leak visible rather than
  // theoretical: the row is on screen either way, and only the note says whose it is.
  world.second.save(FIXTURE_ONE);
  world.second.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'false');

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;
  await expect(star, 'the save under test must really be in flight').toHaveAttribute('data-pending', 'true');

  await anotherReaderTakesOver(page, SECOND);
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(1);
  await expect(page.getByTestId('saved-match-note-text'),
    'the second reader wrote no notes, so there are none on screen before the release').toHaveCount(0);

  await landedWrite(page, SAVE_PATH, () => held.release());

  expect(world.first.saved.has(FIXTURE_ONE.id),
    'the save really did happen on the server, for the reader who asked for it').toBe(true);
  expect(await page.locator('body').innerText(),
    'the first reader\'s private note must not reach the second reader\'s screen by any route')
    .not.toContain(FIRST_NOTE);
  await expect(page.getByTestId('saved-match-note-text'),
    'and no note at all must have appeared on a row that had none').toHaveCount(0);
  await expect(savedRows(page), 'the second reader\'s own two saves, unchanged').toHaveCount(2);
  await expect(starIn(page, FIXTURE_ONE.id),
    'a pending flag from the session that ended would spin here for a write that is not happening')
    .toHaveAttribute('data-pending', 'false');
  await expect(page.getByTestId('saved-matches-failed')).toHaveCount(0);
});

test('MOCKED-ONLY: a SAVE that FAILS after another account signs in does not roll the first reader\'s snapshot into the second\'s', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  // The first reader's snapshot has something in it that the second reader's has not. That is
  // what a rollback written as `data: before.data` hands over wholesale.
  world.first.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(page.getByTestId('saved-matches-empty'),
    'the second reader has saved nothing, and that is what their dashboard says').toBeVisible();

  await landedWrite(page, SAVE_PATH, () => held.release(500));

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the save really did fail on the server').toBe(false);
  await expect(savedRows(page),
    'a rollback belonging to a session that has ended must not put its snapshot here').toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  expect(await page.locator('body').innerText()).not.toContain(FIRST_NOTE);
  expect(await page.locator('body').innerText()).not.toContain(CLUB_TWO);
});

test('MOCKED-ONLY: an UNSAVE released after another account signs in does not remove the second reader\'s bookmark', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  world.first.save(FIXTURE_ONE);
  // The same fixture, saved by both. A removal applied into the wrong session deletes it here.
  world.second.save(FIXTURE_ONE);
  world.second.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'true');

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(1);

  await landedWrite(page, SAVE_PATH, () => held.release());

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the removal really happened, for the first reader')
    .toBe(false);
  await expect(savedRow(page, FIXTURE_ONE.id),
    'the second reader\'s own bookmark for the same fixture must survive it').toHaveCount(1);
  await expect(savedRows(page)).toHaveCount(2);
  await expect(starIn(page, FIXTURE_ONE.id)).toHaveAttribute('data-pending', 'false');
  await expect(starIn(page, FIXTURE_ONE.id)).toHaveAttribute('data-saved', 'true');
});

test('MOCKED-ONLY: an UNSAVE that FAILS after another account signs in does not restore the first reader\'s saves into the second\'s session', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  world.first.save(FIXTURE_ONE);
  world.first.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'true');

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();

  await landedWrite(page, SAVE_PATH, () => held.release(500));

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the removal really did fail on the server').toBe(true);
  await expect(savedRows(page)).toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  expect(await page.locator('body').innerText()).not.toContain(FIRST_NOTE);
});

test('MOCKED-ONLY: a FOLLOW released after another account signs in does not follow anything for the second reader', async ({ page }) => {
  const world = new World();
  // The followed team has a fixture, so a follow leaking into the second session would not only
  // change a hidden id list: it would fetch and show a fixture they never asked for.
  world.teamFixtures = [FIXTURE_ONE];
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/teams/${TEAM.id}`);
  await page.waitForLoadState('networkidle');
  const follow = page.getByTestId('follow-button').first();
  await expect(follow).toHaveAttribute('data-following', 'false');

  const held = holdNextWrite(world);
  await follow.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  const teamReadsBefore = world.teamReads;

  await landedWrite(page, FOLLOW_PATH, () => held.release());

  expect(world.first.teamIds, 'the follow really happened, for the first reader').toEqual([TEAM.id]);
  expect(world.second.teamIds, 'and not for the second').toEqual([]);
  expect(world.teamReads,
    'a follow injected into this session would rebuild the feed and fetch that team\'s fixtures')
    .toBe(teamReadsBefore);
  await expect(page.getByTestId('feed-match'),
    'so no fixture reached through somebody else\'s follow may appear here').toHaveCount(0);
});

test('MOCKED-ONLY: a FOLLOW that FAILS after another account signs in does not roll the first reader\'s snapshot into the second\'s', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  // Again the discriminator is something only the first reader has: their saved matches, which
  // a whole-snapshot rollback hands over along with everything else in `before.data`.
  world.first.save(FIXTURE_ONE);
  world.first.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/teams/${TEAM.id}`);
  await page.waitForLoadState('networkidle');
  const follow = page.getByTestId('follow-button').first();

  const held = holdNextWrite(world);
  await follow.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();

  await landedWrite(page, FOLLOW_PATH, () => held.release(500));

  expect(world.first.teamIds, 'the follow really did fail on the server').toEqual([]);
  await expect(savedRows(page),
    'a failed follow in a session that has ended must not deliver that session\'s saved matches')
    .toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  expect(await page.locator('body').innerText()).not.toContain(FIRST_NOTE);
});

/* ------------------------------ 5. a rollback inside ONE session reverts one thing, not the world */

test('MOCKED-ONLY: a rollback after a failed write keeps what a refresh legitimately brought in', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(1);
  await letTheSnapshotGoStale(page);

  // The reader removes the first fixture; the answer is held, so the server has not committed it.
  const held = holdNextWrite(world);
  await starIn(page, FIXTURE_ONE.id).click();
  await held.arrived;
  await expect(savedRow(page, FIXTURE_ONE.id), 'the removal is applied optimistically').toHaveCount(0);

  // Meanwhile the same reader saves a second fixture on their phone, and this tab picks it up.
  world.first.save(FIXTURE_TWO);
  await refreshThroughTheTab(page);
  await expect(savedRow(page, FIXTURE_TWO.id),
    'the refresh really brought the second fixture in').toHaveCount(1);

  // Now the removal fails. Reverting it must put the first fixture back and touch nothing else.
  await landedWrite(page, SAVE_PATH, () => held.release(500));

  await expect(savedRow(page, FIXTURE_ONE.id),
    'the removal failed, so the bookmark it removed must come back').toHaveCount(1);
  await expect(savedRow(page, FIXTURE_TWO.id),
    'and the fixture the refresh brought in must not be thrown away with it').toHaveCount(1);
  await expect(starIn(page, FIXTURE_ONE.id)).toHaveAttribute('data-pending', 'false');
});

/* --------------------------- 6. a refresh that lands in the middle of a write */

test('MOCKED-ONLY: a refresh landing between an optimistic removal and its answer does not resurrect the bookmark', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(1);
  await letTheSnapshotGoStale(page);

  const held = holdNextWrite(world);
  await starIn(page, FIXTURE_ONE.id).click();
  await held.arrived;
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(0);

  /*
   * THE RACE, REACHED. The removal has not been committed, so a read taken now honestly reports
   * the match as still saved — and nothing discards it, because it was issued AFTER the local
   * change it contradicts. The assertion below is not the behaviour anybody wants; it is the
   * proof that this test really put the two in the order the defect needs. What has to be true
   * is asserted after the release.
   */
  await refreshThroughTheTab(page);
  await expect(savedRow(page, FIXTURE_ONE.id),
    'mid-flight, the refresh legitimately shows the server\'s uncommitted state').toHaveCount(1);

  await landedWrite(page, SAVE_PATH, () => held.release());

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the removal succeeded on the server').toBe(false);
  await expect(savedRow(page, FIXTURE_ONE.id),
    'a bookmark the server has removed must not be left on the screen looking saved').toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  expect(await page.locator('body').innerText(),
    'and its private note must go with it').not.toContain(FIRST_NOTE);
});

test('MOCKED-ONLY: a refresh landing in the middle of a save does not leave the save undone', async ({ page }) => {
  const world = new World();
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'false');
  await letTheSnapshotGoStale(page);

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;
  await expect(star).toHaveAttribute('data-saved', 'true');

  // The same ordering as the test above, the other way round: the refresh reports the server's
  // state from before the save committed.
  await refreshThroughTheTab(page);

  await landedWrite(page, SAVE_PATH, () => held.release());

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the save succeeded on the server').toBe(true);
  await expect(star, 'so the control must end up saved, whatever the refresh saw mid-flight')
    .toHaveAttribute('data-saved', 'true');
  await expect(star).toHaveAttribute('data-pending', 'false');
});

test('MOCKED-ONLY: a refresh landing in the middle of an unfollow does not leave the team in the followed list', async ({ page }) => {
  /*
   * THE SAME ASSUMPTION AS THE REMOVAL ABOVE, IN THE THIRD WRITE.
   *
   * `toggleFollow`'s success assigned the server's authoritative `ids` and left the RESOLVED list
   * alone, assuming the optimistic step — which drops the row from `teams` on an unfollow — was
   * still standing. A refresh landing in between puts the row back. The panel that lists what you
   * follow renders `teams`, while the star renders `teamIds`, so the club stayed in the list with
   * its own star saying it was not followed.
   */
  const world = new World();
  world.first.teamIds = [TEAM.id];
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  await expect(page.getByTestId('followed-team')).toHaveCount(1);
  await letTheSnapshotGoStale(page);

  const held = holdNextWrite(world);
  await page.getByTestId('follow-button').first().click();
  await held.arrived;
  await expect(page.getByTestId('followed-team'), 'the unfollow is applied optimistically')
    .toHaveCount(0);

  // The race, reached: the unfollow is not committed, so a read taken now honestly still lists it.
  await refreshThroughTheTab(page);
  await expect(page.getByTestId('followed-team'),
    'mid-flight, the refresh legitimately shows the server\'s uncommitted state').toHaveCount(1);

  await landedWrite(page, FOLLOW_PATH, () => held.release());

  expect(world.first.teamIds, 'the unfollow succeeded on the server').toEqual([]);
  await expect(page.getByTestId('followed-team'),
    'a team the server no longer holds must not be left in the list of what you follow')
    .toHaveCount(0);
  await expect(page.getByTestId('following-empty')).toBeVisible();
});

/* --------------------- 7. a rollback that puts the FIXTURE back along with the note */

/**
 * A SAVE ROW IS TWO THINGS AT ONCE, AND ONLY ONE OF THEM IS THE READER'S.
 *
 * `SavedMatch` carries the reader's own fields — the private note and its timestamps — and
 * `.match`, the fixture payload the backend keeps current for everybody. A note edit writes the
 * first and nothing at all of the second, so `revertSavedMatch` must put back the first and leave
 * the second alone. Reinstating the whole row captured before the write would make the FAILURE OF
 * A NOTE EDIT REWRITE THE MATCH: whatever the backend learned about the fixture while the edit
 * was on the wire, replaced by the copy that existed when the reader started typing.
 *
 * And that is not a cosmetic revert. `insertSaved` files a row by `match.status`, so a fixture
 * that had finished goes back to being live: the result the reader came back for leaves
 * "Results", reappears under "In play now" with its score gone, and the page is then saying a
 * match that has been played is being played right now — because a note failed to save.
 */

test('MOCKED-ONLY: a note edit that fails after the result has landed leaves the finished match finished', async ({ page }) => {
  const world = new World();
  world.first.note = NOTE_BEFORE;
  /*
   * The fixture is in play, with no score yet, when the reader starts typing. That is the copy a
   * whole-row rollback would restore, and it is stale in two ways the screen can show: the wrong
   * group, and a result that has gone missing.
   */
  const inPlay: ApiMatch = { ...FIXTURE_ONE, status: 'live', minute: '63', score: null };
  world.storeFixture(inPlay);
  world.first.save(inPlay);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  const row = savedRow(page, FIXTURE_ONE.id);
  const scoreline = row.locator(`a[href="/match/${FIXTURE_ONE.id}"]`);
  await expect(row, 'the saved fixture is in play when the reader opens the page')
    .toHaveAttribute('data-feed-phase', 'live');
  await expect(row.getByTestId('saved-match-note-text')).toHaveText(NOTE_BEFORE);
  await letTheSnapshotGoStale(page);

  // The reader rewrites their note. The answer is held, so the server has not committed it and
  // anything read in the meantime still carries the note they had.
  const held = holdNextWrite(world);
  await row.getByTestId('saved-match-note-edit').click();
  await row.getByTestId('saved-match-note-input').fill(NOTE_EDITED);
  await row.getByTestId('saved-match-note-save').click();
  await held.arrived;
  await expect(starIn(page, FIXTURE_ONE.id), 'the edit under test must really be in flight')
    .toHaveAttribute('data-pending', 'true');

  // Meanwhile the match ends. The backend's scheduler moves the stored row — no provider is
  // involved on that path — and this tab picks it up when the reader comes back to it.
  world.schedulerMoves(FIXTURE_ONE.id, { status: 'finished', minute: null, score: { home: 3, away: 1 } });
  await refreshThroughTheTab(page);
  await expect(row, 'the result really landed while the edit was still on the wire')
    .toHaveAttribute('data-feed-phase', 'result');
  await expect(scoreline).toContainText('3');

  await landedWrite(page, SAVE_PATH, () => held.release(500));

  expect(world.first.saved.get(FIXTURE_ONE.id)?.note, 'the edit really did fail on the server')
    .toBe(NOTE_BEFORE);
  await expect(row, 'a note that failed to save must not un-finish the match')
    .toHaveAttribute('data-feed-phase', 'result');
  await expect(page.getByTestId('feed-group-live'),
    'and the fixture must not reappear under a heading that says it is being played now')
    .toHaveCount(0);
  await expect(page.getByTestId('feed-group-result')).toBeVisible();
  await expect(scoreline, 'the final score is the freshest thing we hold and must survive the rollback')
    .toContainText('3');
  await expect(scoreline).toContainText('1');
  await expect(row).toContainText('FT');

  // And the reader's own field, which IS what the write touched, goes back to what it was.
  await expect(row.getByTestId('saved-match-note-text')).toHaveText(NOTE_BEFORE);
  expect(await page.locator('body').innerText(),
    'the text of a note that was never saved must not be left standing as though it had been')
    .not.toContain(NOTE_EDITED);
  await expect(starIn(page, FIXTURE_ONE.id)).toHaveAttribute('data-pending', 'false');
});

/**
 * AND THE EDIT DOES NOT HAVE TO FAIL. THE SUCCESS PATH CARRIES THE SAME STALE FIXTURE.
 *
 * The test above releases its write as a failure, so it only ever exercises the rollback. The
 * write ANSWER is the other half of the same hazard: `SaveMatchResult` extends `SavedMatch`, so
 * it too carries `.match` — the fixture as the server serialised it INSIDE the transaction that
 * processed the write, which is the one fixture payload reaching this store that can be older
 * than the row the store already holds. Handing that whole row to `insertSaved`, which files by
 * `match.status`, produces the identical user-visible symptom — a played match back under "In
 * play now" with its score gone — out of a note edit that SUCCEEDED, with nothing stale and
 * nothing superseded about it.
 *
 * Both gates of `holdWriteOn` are needed to prove it: the server must PROCESS the edit while the
 * fixture is still live, and ANSWER it after the full-time result has reached this tab.
 */

test('MOCKED-ONLY: a note edit that SUCCEEDS after the result has landed leaves the finished match finished', async ({ page }) => {
  const world = new World();
  world.first.note = NOTE_BEFORE;
  // In play, no score yet: the copy the server's answer will be built around, and stale in the
  // two ways the screen can show — the wrong group, and a missing result.
  const inPlay: ApiMatch = { ...FIXTURE_ONE, status: 'live', minute: '63', score: null };
  world.storeFixture(inPlay);
  world.first.save(inPlay);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  const row = savedRow(page, FIXTURE_ONE.id);
  const scoreline = row.locator(`a[href="/match/${FIXTURE_ONE.id}"]`);
  await expect(row, 'the saved fixture is in play when the reader opens the page')
    .toHaveAttribute('data-feed-phase', 'live');
  await expect(row.getByTestId('saved-match-note-text')).toHaveText(NOTE_BEFORE);
  await letTheSnapshotGoStale(page);

  const edit = holdWriteOn(world, FIXTURE_ONE.id);
  await row.getByTestId('saved-match-note-edit').click();
  await row.getByTestId('saved-match-note-input').fill(NOTE_EDITED);
  await row.getByTestId('saved-match-note-save').click();
  await edit.arrived;
  await expect(starIn(page, FIXTURE_ONE.id), 'the edit under test must really be in flight')
    .toHaveAttribute('data-pending', 'true');

  // The server commits the edit and builds its answer HERE, while the fixture is still live and
  // scoreless — the frozen copy the rest of this test is about. It does not go on the wire yet.
  await edit.commit();
  expect(world.first.saved.get(FIXTURE_ONE.id)?.note, 'this edit really did succeed on the server')
    .toBe(NOTE_EDITED);

  // Then the match ends, and the reader comes back to the tab in that window.
  world.schedulerMoves(FIXTURE_ONE.id, { status: 'finished', minute: null, score: { home: 3, away: 1 } });
  await refreshThroughTheTab(page);
  await expect(row, 'the result really landed while the answer was still on the wire')
    .toHaveAttribute('data-feed-phase', 'result');
  await expect(scoreline).toContainText('3');

  // And now the answer the server built two moves ago arrives, successfully.
  await landedWrite(page, SAVE_PATH, () => edit.deliver());

  await expect(row, 'a note edit that SAVED must not un-finish the match either')
    .toHaveAttribute('data-feed-phase', 'result');
  await expect(page.getByTestId('feed-group-live'),
    'and it must not put the fixture back under a heading that says it is being played now')
    .toHaveCount(0);
  await expect(page.getByTestId('feed-group-result')).toBeVisible();
  await expect(scoreline, 'the final score is the freshest thing we hold and the answer is not newer')
    .toContainText('3');
  await expect(scoreline).toContainText('1');
  await expect(row).toContainText('FT');

  // The note and its timestamps ARE what this write authored, so the edit stands.
  await expect(row.getByTestId('saved-match-note-text'),
    'the edit the server accepted is what the reader must be left looking at').toHaveText(NOTE_EDITED);
  await expect(starIn(page, FIXTURE_ONE.id)).toHaveAttribute('data-pending', 'false');
});

/**
 * AND THE OTHER DIRECTION, WHICH IS THE ORDINARY ONE.
 *
 * The two tests above are both cases where a READ landed while the write was on the wire, which
 * is what makes the answer's fixture the older of the two. With no read in between there is
 * nothing newer than the answer, and refusing it is a regression rather than a guard: the store
 * would be left holding whatever copy the caller happened to be looking at, for ever, because
 * `saveMatch` never re-reads.
 *
 * That copy is routinely stale, and the page most likely to hand one over is the one most saves
 * come from. A day page renders its fixtures once and does not poll; the row's star passes the
 * fixture it drew, so the entry appears at once rather than only when the server's copy comes
 * back. Star a match two hours after that page was drawn and the save answer is the first fresh
 * fixture this tab has seen — including the result, if it has one.
 *
 * The feed row here stands in for that day page, by the same mechanism: its `onToggleSave` passes
 * `entry.match`, the copy the fan-out gave it, and nothing refreshes it in between.
 */

test('MOCKED-ONLY: a save answer carrying a FRESHER fixture than the tab holds is adopted, result and all', async ({ page }) => {
  const world = new World();
  world.first.teamIds = [TEAM.id];
  /*
   * Kick-off three hours ago, which is past KICKOFF_WATCH_GRACE_MS: a stale `scheduled` row that
   * old starts no kick-off watch and no poll, so the only thing that can bring this fixture up
   * to date in this test is the save answer itself.
   */
  const asTheTabHasIt = fixtureAt(
    new Date(Date.now() - 3 * 3_600_000).toISOString(), 'Marshgate United', 'Sandhill Rovers');
  // What the follow fan-out gives this tab: scheduled, no score. Never refreshed after this.
  world.teamFixtures = [asTheTabHasIt];
  // What the backend actually holds by now. `PUT /me/saved-matches/{id}` answers from this row.
  world.storeFixture({ ...asTheTabHasIt, status: 'finished', minute: null, score: { home: 2, away: 1 } });
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  const followedRow = page.locator(
    `[data-testid="feed-match"][data-match-id="${asTheTabHasIt.id}"]`);
  await expect(followedRow, 'the tab is showing the fixture as its own copy has it: not yet played')
    .toHaveAttribute('data-feed-phase', 'upcoming');

  const save = holdWriteOn(world, asTheTabHasIt.id);
  await followedRow.getByTestId('save-match-button').click();
  await save.arrived;
  const savedRowNow = savedRow(page, asTheTabHasIt.id);
  await expect(savedRowNow, 'the optimistic entry is the tab\'s own stale copy, as it must be')
    .toHaveAttribute('data-feed-phase', 'upcoming');
  await expect(starIn(page, asTheTabHasIt.id),
    'the save under test must really be in flight').toHaveAttribute('data-pending', 'true');

  // The server processes the save against the row it holds, so its answer carries the result.
  const readsBefore = world.favouriteReads;
  await save.commit();
  await landedWrite(page, SAVE_PATH, () => save.deliver());
  expect(world.favouriteReads,
    'nothing may read the snapshot here: the answer must be the only fresh thing in this test')
    .toBe(readsBefore);

  await expect(savedRowNow, 'the answer is the newer of the two fixtures and must be adopted whole')
    .toHaveAttribute('data-feed-phase', 'result');
  await expect(page.getByTestId('feed-group-result')).toBeVisible();
  const scoreline = savedRowNow.locator(`a[href="/match/${asTheTabHasIt.id}"]`);
  await expect(scoreline, 'including the score the tab had no way of knowing').toContainText('2');
  await expect(scoreline).toContainText('1');
  await expect(savedRowNow).toContainText('FT');
  await expect(starIn(page, asTheTabHasIt.id)).toHaveAttribute('data-pending', 'false');
  expect(world.first.saved.has(asTheTabHasIt.id), 'and the save itself really happened')
    .toBe(true);
  expect(world.favouriteReads,
    'checked again at the end: an assertion above retries for ten seconds, and a read landing '
    + 'inside that window would bring the result in by itself and prove nothing')
    .toBe(readsBefore);
});

/* ------------------------- 8. two answers that arrive in the order the network chose */

/**
 * THE SERVER'S SECOND ANSWER IS NOT THE READER'S SECOND INTENT.
 *
 * Every write here is answered with the state the server held when it processed THAT write, and
 * a write the server has not seen yet cannot be in it. Two writes in quick succession therefore
 * produce two answers that disagree, each of them honest about a different instant. Applying
 * whichever one arrives last lets the network, not the reader, choose the end state.
 *
 * Both tests below choose the ordering rather than hoping for it: each write is held at two
 * points, so the stub can be made to PROCESS them in one order and ANSWER them in the other.
 * There is no sleeping and nothing to lose a race with.
 */

test('MOCKED-ONLY: two unfollows answered in the reverse order leave both teams unfollowed', async ({ page }) => {
  const world = new World();
  world.knownTeams = [TEAM, TEAM_OTHER];
  world.first.teamIds = [TEAM.id, TEAM_OTHER.id];
  // A fixture behind the follows, so a follow left standing by mistake is not just an id in a
  // list nobody sees: it puts a match on the dashboard of somebody who follows neither club.
  world.teamFixtures = [followedFixture()];
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  await expect(page.getByTestId('followed-team')).toHaveCount(2);
  await expect(page.getByTestId('feed-match'),
    'the fixture behind the follows is in the feed to begin with').toHaveCount(1);

  const rowFor = (team: ApiTeamRef) => page.getByTestId('followed-team').filter({ hasText: team.name });

  const firstOff = holdWriteOn(world, TEAM.id);
  await rowFor(TEAM).getByTestId('follow-button').click();
  await firstOff.arrived;
  const secondOff = holdWriteOn(world, TEAM_OTHER.id);
  await rowFor(TEAM_OTHER).getByTestId('follow-button').click();
  await secondOff.arrived;
  await expect(page.getByTestId('followed-team'), 'both unfollows are applied optimistically')
    .toHaveCount(0);

  /*
   * The server processes them in the order it received them. The answer to the FIRST is built
   * here, before the second has been applied, so it still lists the second team — truthfully,
   * about an instant that is already over by the time anybody reads it.
   */
  await firstOff.commit();
  await secondOff.commit();
  expect(world.first.teamIds, 'the server holds neither follow any more').toEqual([]);

  // The answers come back the other way round: the second one, and then the first one's older
  // list. This is the whole defect — one packet arriving after another.
  await landedWrite(page, `${FOLLOW_PATH}${TEAM_OTHER.id}`, () => secondOff.deliver());
  await landedWrite(page, `${FOLLOW_PATH}${TEAM.id}`, () => firstOff.deliver());

  await expect(page.getByTestId('followed-team'),
    'an older answer must not put back a follow a newer one has already removed').toHaveCount(0);
  await expect(page.getByTestId('following-empty'),
    'the panel that lists what you follow says you follow nothing').toBeVisible();
  await expect(page.getByTestId('feed-match'),
    'so no fixture may be left in the feed on the strength of a follow that is gone')
    .toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty'),
    'and the feed must agree with it: nothing followed, nothing saved, nothing to show')
    .toBeVisible();
});

test('MOCKED-ONLY: two note edits on one match answered in the reverse order leave the LAST edit standing', async ({ page }) => {
  const world = new World();
  world.first.note = NOTE_BEFORE;
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  const row = savedRow(page, FIXTURE_ONE.id);
  await expect(row.getByTestId('saved-match-note-text')).toHaveText(NOTE_BEFORE);

  const firstEdit = holdWriteOn(world, FIXTURE_ONE.id);
  await row.getByTestId('saved-match-note-edit').click();
  await row.getByTestId('saved-match-note-input').fill(NOTE_EDITED);
  await row.getByTestId('saved-match-note-save').click();
  await firstEdit.arrived;

  /*
   * HOW A SECOND WRITE ON ONE MATCH IS REACHED, because the interface guards one control and not
   * the other. The star is inert while a write on its match is in flight — `pendingMatchIds` is
   * shared — but the note editor's "Saving…" is React state inside one mounted component. The
   * reader, waiting on a slow answer, opens the fixture to look at something and comes back; the
   * editor they come back to is a fresh one that knows nothing about the write still running.
   * Two writes on one match, both live, without either control being pressed twice.
   */
  await row.locator(`a[href="/match/${FIXTURE_ONE.id}"]`).click();
  await page.waitForURL(`**/match/${FIXTURE_ONE.id}`);
  await goToDashboardThroughTheHeader(page);
  await expect(row.getByTestId('saved-match-note-text'),
    'the first edit is on screen optimistically, its answer still held').toHaveText(NOTE_EDITED);

  const secondEdit = holdWriteOn(world, FIXTURE_ONE.id);
  await row.getByTestId('saved-match-note-edit').click();
  await row.getByTestId('saved-match-note-input').fill(NOTE_CORRECTED);
  await row.getByTestId('saved-match-note-save').click();
  await secondEdit.arrived;

  // The server applies them in the order it received them, so what it ends up holding is the
  // correction — the reader's last intent, and the only thing that may be on screen at the end.
  await firstEdit.commit();
  await secondEdit.commit();
  expect(world.first.saved.get(FIXTURE_ONE.id)?.note, 'the server holds the correction')
    .toBe(NOTE_CORRECTED);

  // And the answers come back the other way round.
  await landedWrite(page, SAVE_PATH, () => secondEdit.deliver());
  await landedWrite(page, SAVE_PATH, () => firstEdit.deliver());

  await expect(row.getByTestId('saved-match-note-text'),
    'the reader\'s last edit must stand, not the last answer to arrive').toHaveText(NOTE_CORRECTED);
  expect(await page.locator('body').innerText(),
    'the superseded edit must not be put back over the one that replaced it')
    .not.toContain(NOTE_EDITED);
  await expect(starIn(page, FIXTURE_ONE.id),
    'and nothing may be left looking as though a write on this match is still running')
    .toHaveAttribute('data-pending', 'false');
});

/* ------------ 9. an answer's WHOLE-LIST field, older than the snapshot it lands on */

/**
 * A FOLLOW ANSWER CARRIES THE WHOLE FOLLOWED LIST, AND THE FOLLOW WROTE ONE ID OF IT.
 *
 * Same class as section 7, one payload over: the part of a write answer that the write did not
 * author is a snapshot frozen when the server processed it. `writeOwner` and `writesInFlight`
 * see local writes only, so a change made somewhere else entirely — the reader's phone — is
 * invisible to both, reaches this tab inside a refresh, and is deleted by an answer built before
 * it existed unless the refresh itself is counted. The older of two honest server views
 * overwriting the newer.
 *
 * Both gates again, because the whole point is an answer built at one instant and applied at a
 * later one, with a refresh in between.
 */

test('MOCKED-ONLY: an unfollow answer must not delete a follow a refresh brought in from another device', async ({ page }) => {
  const world = new World();
  world.knownTeams = [TEAM, TEAM_OTHER];
  world.first.teamIds = [TEAM.id];
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const rowFor = (team: ApiTeamRef) => page.getByTestId('followed-team').filter({ hasText: team.name });

  await page.goto('/dashboard');
  await expect(rowFor(TEAM), 'one club followed to begin with').toHaveCount(1);
  await expect(page.getByTestId('followed-team')).toHaveCount(1);
  await letTheSnapshotGoStale(page);

  const off = holdWriteOn(world, TEAM.id);
  await rowFor(TEAM).getByTestId('follow-button').click();
  await off.arrived;
  await expect(page.getByTestId('followed-team'), 'the unfollow is applied optimistically')
    .toHaveCount(0);

  // The server processes the unfollow and builds its answer now: `ids` as the account stands at
  // this instant, which is nothing at all.
  await off.commit();
  expect(world.first.teamIds, 'the unfollow is committed on the server').toEqual([]);

  /*
   * THEN THE READER FOLLOWS THE OTHER CLUB ON THEIR PHONE. Nothing about that can reach this tab
   * except through a read, and the answer already sitting on the wire was built before it
   * happened, so that answer's list cannot contain it.
   */
  world.first.teamIds = [TEAM_OTHER.id];
  await refreshThroughTheTab(page);
  await expect(rowFor(TEAM_OTHER), 'the refresh brings the phone\'s follow into this tab')
    .toHaveCount(1);

  await landedWrite(page, `${FOLLOW_PATH}${TEAM.id}`, () => off.deliver());

  await expect(rowFor(TEAM_OTHER),
    'a list built before the phone\'s follow existed must not delete it').toHaveCount(1);
  await expect(page.getByTestId('followed-team'),
    'and nothing else may be invented either — one club followed, the one the server holds')
    .toHaveCount(1);
  await expect(rowFor(TEAM),
    'while the unfollow this write DID author still stands').toHaveCount(0);
  expect(world.first.teamIds, 'which is exactly what the server holds').toEqual([TEAM_OTHER.id]);
});
