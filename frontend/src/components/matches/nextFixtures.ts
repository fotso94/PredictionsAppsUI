import apiClient from '@/services/api-client'

/**
 * "When do these competitions play next?", asked once for as long as the answer holds.
 *
 * A different question from the one the matchday list asks. The list reads the days this
 * installation has stored; this reads the providers' competition calendars, through
 * `/matches/upcoming`, which costs one provider request per competition and is cached
 * server-side for hours behind a single-flight guard.
 *
 * Only the empty state asks it, so a day with fixtures on it never does.
 */

export interface UpcomingFixture {
  competition: { key: string | null; name: string | null }
  home: string | null
  away: string | null
  kickoff_utc: string | null
}

export interface UpcomingAnswer {
  /**
   * False when no calendar could be read at all. `fixtures` is then empty for want of an answer
   * rather than for want of football, and the reassuring sentence is not available.
   */
  known: boolean
  /** The earliest kickoff of the whole answer, not of the capped list. */
  next_kickoff: string | null
  fixtures: UpcomingFixture[]
  /**
   * Covered competitions nobody could be asked about. Normally empty; when it is not, the
   * fixtures speak only for the competitions that answered and one of these may play earlier,
   * so `next_kickoff` is the earliest of what was read rather than the date football resumes.
   */
  unanswered: string[]
}

/** How many fixtures to name. An empty state, not a round-by-round calendar. */
export const NAMED_FIXTURES = 3

/**
 * The answer, once this session has one, shared by every empty day the reader visits.
 *
 * The backend's own cache is what stops the providers being asked again; this stops OUR backend
 * being asked once per empty day the reader scrolls through, which across an international break
 * is the difference between one request and eighteen.
 *
 * ONLY AN ANSWER IS KEPT HERE. A failure to answer is not one and is not kept as one: it goes to
 * `failure` below, which holds it for minutes where this holds an answer for hours. `null` means
 * nothing is remembered, and an answer is dropped back to `null` once it has stopped being
 * current, which is the earlier of the kickoff it names and its own age. See `stillCurrent`.
 */
let answered: UpcomingAnswer | null = null

/** When `answered` was taken. Every answer expires on this as well as on the kickoff it names. */
let answeredAt = 0

/**
 * The last time this session ASKED AND WAS NOT ANSWERED, with the instant it happened.
 *
 * KEPT FOR MINUTES, NOT HOURS, AND FOR A DIFFERENT REASON FROM AN ANSWER. Every calendar failure
 * reaches the browser as a success: the endpoint reports an outage behind it, a sweep already in
 * flight, its own growing backoff and its daily share of the request allowance all as HTTP 200
 * with `known: false`, while a request that fails outright — or comes back as something this
 * endpoint did not say — arrives here as `null`. Keeping either in `answered` would pin one bad
 * minute to six hours of the session, and no amount of reloading a day would get past it.
 *
 * REMEMBERING NOTHING IS THE OTHER MISTAKE, AND IT IS THE EXPENSIVE ONE. Nothing remembered means
 * nothing to serve, so every empty day opened and every return to the tab asks again — one
 * request per return, indefinitely, at exactly the moment the thing being asked is already
 * failing or already refusing to spend. The stress and the traffic arrive together.
 *
 * `answer` is what a caller is handed while this stands, and it is whatever the failure really
 * was: the endpoint's own `known: false` where it said that, `null` where the request did not
 * come back. So a remembered failure renders as the silence it is and never as football news.
 */
let failure: { answer: UpcomingAnswer | null; at: number } | null = null

/**
 * How long a failure stands before it is worth asking again.
 *
 * TWO MINUTES, THE SHORTEST INTERVAL IN WHICH THE CALENDAR PATH BEHIND THIS ENDPOINT CAN HAVE
 * TRIED AGAIN. A sweep holds its lock for 120 seconds and does not release it on failure, and a
 * failed sweep waits at least 120 seconds before another is paid for, doubling from there
 * (`CALENDAR_HEAD_LOCK_SECONDS` and `CALENDAR_HEAD_BACKOFF_BASE_SECONDS` in
 * backend/app/services/match_data_service.py). Re-asking inside that window cannot be told
 * anything new; it can only add load to something already in trouble.
 *
 * DELIBERATELY THE SHORTEST DEFENSIBLE NUMBER, not the backoff's forty-minute ceiling. A failure
 * held here is one a reader cannot get past by opening another day, and it also covers failures
 * the calendar path never saw — a gateway having a bad second, a dropped connection — which can
 * clear sooner than the backend's own floor. The cost of that is up to two minutes more of a date
 * the reader was already looking at, which is the cheaper of the two mistakes available.
 */
const FAILURE_TTL_MS = 2 * 60 * 1000

/**
 * The request currently open, shared so that several empty days rendering at once — or a reader
 * moving between days faster than the network answers — cost one request rather than one each.
 */
let pending: Promise<UpcomingAnswer | null> | null = null

async function fetchUpcoming(): Promise<UpcomingAnswer | null> {
  try {
    const { data } = await apiClient.get<Partial<UpcomingAnswer>>('/api/v1/matches/upcoming', {
      params: { limit: NAMED_FIXTURES },
    })
    // A body without the `known` flag is not this endpoint answering. Accepting it would let
    // anything that returns 200 decide what an empty matchday claims about football.
    if (typeof data?.known !== 'boolean') return null
    return {
      known: data.known,
      next_kickoff: data.next_kickoff ?? null,
      fixtures: Array.isArray(data.fixtures) ? data.fixtures : [],
      // An answer that does not name its gaps is read as having none: that is what the field
      // means when the endpoint sends it empty, and the only thing a missing field can mean.
      unanswered: Array.isArray(data.unanswered) ? data.unanswered : [],
    }
  } catch {
    // Nothing is rendered for a request that failed: we asked and could not find out, which is
    // what the surrounding empty state already says.
    return null
  }
}

/**
 * How long ANY answer may be kept, whatever instant it names.
 *
 * SIX HOURS, DELIBERATELY THE SAME NUMBER THE ENDPOINT CACHES A CALENDAR HEAD FOR
 * (`CALENDAR_HEAD_TTL_SECONDS` in backend/app/services/match_data_service.py). The two are one
 * decision and have to move together: holding longer than the backend does leaves the tab behind
 * a calendar the backend has already renewed.
 *
 * ASKING AGAIN SOONER WOULD NOT BE POINTLESS — IT WOULD BE THE WRONG EXPIRY FOR THE JOB. The
 * endpoint re-filters the calendar it holds against the clock of each request and recomputes
 * `known` from what survives (backend/app/api/v1/endpoints/matches.py), so one cached calendar
 * head does answer differently inside a single TTL window of its own: a kickoff passes, the date
 * moves to the fixture behind it, and a head whose last fixture has been played comes back
 * `known: false`. Every one of those changes is driven by the clock alone, which is what the
 * kickoff half of `stillCurrent` expires against — exactly, at the instant it happens, without
 * asking anybody. Polling for them on a shorter age would be paying for what this tab can work
 * out for itself.
 *
 * WHAT AGE IS ACTUALLY FOR is the other class of change, the one no clock here can derive: a
 * postponement, a competition added, a calendar read empty that has since filled in. Those reach
 * a reader only through a calendar the backend swept again — and, its cache holding, its own six
 * hours is the floor on when that can have happened.
 *
 * Long enough that scrolling a break's worth of empty days costs one request; short enough that a
 * tab left open learns of a revised calendar on the first sweep that could possibly carry one.
 */
const ANSWER_TTL_MS = 6 * 60 * 60 * 1000

/**
 * Whether a remembered answer still describes the future, recently enough to go on repeating.
 *
 * TWO LIMITS, AND AN ANSWER LIVES ONLY UNTIL THE FIRST OF THEM.
 *
 * THE KICKOFF IT NAMES. The endpoint filters its calendar against the clock of the request that
 * asked, which is what stops a reader being told football resumes on a day that has passed. That
 * filter is applied once, to the answer. A tab left open across the resumption — over a weekend,
 * or simply overnight — would go on naming a fixture that has since been played as the next one
 * there is, so the earliest kickoff of the answer is also an expiry.
 *
 * ITS AGE. A kickoff eighteen days out is no expiry at all, and eighteen days out is exactly what
 * an international break looks like: one answer would stand for the whole break, and a reader
 * whose tab has been open since Monday would still be reading Monday's calendar on Friday.
 * Fixtures are postponed, competitions are added and a calendar read empty fills in, none of
 * which moves the kickoff already named — so age is the second expiry, and it binds every answer.
 *
 * That includes the ones naming no instant at all, which make the strongest claim this component
 * has: `known` with no fixtures renders "the calendars list nothing to come". An answer with
 * nothing to expire against is the last one that should be allowed to stand unchallenged.
 */
function stillCurrent(answer: UpcomingAnswer, takenAt: number, now: number): boolean {
  if (now - takenAt >= ANSWER_TTL_MS) return false
  const earliest = answer.next_kickoff ? Date.parse(answer.next_kickoff) : NaN
  // An answer naming no instant, or one we cannot read, has its age and nothing else to go on.
  return Number.isNaN(earliest) || earliest > now
}

/**
 * What this session has to say, asking only when it has nothing current to say it with.
 *
 * Three things can stand between a caller and the network, in this order: an answer that is still
 * current, a failure too recent to be worth repeating, and a request already in flight. Never
 * rejects: a caller is given the endpoint's own `known: false`, or `null`, and renders that.
 */
export function upcomingAnswer(): Promise<UpcomingAnswer | null> {
  const now = Date.now()
  const current = answered !== null && stillCurrent(answered, answeredAt, now)
  if (current) return Promise.resolve(answered)
  if (failure !== null && now - failure.at >= FAILURE_TTL_MS) failure = null
  /*
   * AN EXPIRED ANSWER IS STILL BETTER THAN NO ANSWER, so it is not thrown away until something
   * replaces it. `answered` is kept past its expiry precisely so that this line has something to
   * fall back on: when the last attempt could not find out, a reader who has just changed day —
   * and whose component therefore starts with nothing on screen — is shown the calendar we last
   * knew rather than "we could not find out". Nulling it at expiry would make the component's own
   * rule, that a read may improve a notice and never subtract from it, hold only for as long as
   * one instance stays mounted.
   *
   * The refresh below still runs on the next call the failure memory allows, so this is a grace
   * period and not a second cache: nothing here extends how long an answer is treated as current.
   */
  if (failure !== null) return Promise.resolve(answered ?? failure.answer)
  if (pending !== null) return pending
  pending = fetchUpcoming().then(result => {
    pending = null
    if (result !== null && result.known) {
      answered = result
      answeredAt = Date.now()
      failure = null
    } else {
      // Not an answer: the endpoint could not find out, or the request never came back. What we
      // last knew is deliberately left in `answered` — expired, so it can never be served as
      // current, but available to the line above while this failure is remembered.
      failure = { answer: result, at: Date.now() }
    }
    return result
  })
  return pending
}

/**
 * Run `handler` when the reader comes back to this tab. Returns the disposer.
 *
 * Both events are listened for because neither alone covers both ways back: switching browser
 * tabs fires `visibilitychange`, while switching applications fires `focus` with the document
 * never having been hidden. A TAB THAT IS NOT IN FRONT DOES NOTHING — the visibility test is what
 * keeps a backgrounded window from working — and the two events arriving together for one return
 * cost nothing, because `upcomingAnswer()` serves both from the same answer, the same remembered
 * failure, or the same request in flight.
 *
 * A THIRD COPY OF EIGHT LINES, AND THE THIRD FILE TO SAY SO. src/services/favourites.service.ts
 * holds this function module-private, and src/pages/MatchDetailPage.tsx carries a copy with a
 * note asking for one shared helper — exported from that service, or lifted into src/utils — the
 * moment those files can be edited together. Neither is reachable from here, and a second meaning
 * for "the reader came back" would be worse than a copy: the saved-matches store, the match page
 * and this note have to wake on the same signal or they will disagree about what a return is.
 */
export function onReaderReturns(handler: () => void): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined
  const wake = () => { if (document.visibilityState === 'visible') handler() }
  window.addEventListener('focus', wake)
  document.addEventListener('visibilitychange', wake)
  return () => {
    window.removeEventListener('focus', wake)
    document.removeEventListener('visibilitychange', wake)
  }
}
