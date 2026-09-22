import apiClient from '@/services/api-client'

/**
 * "When do these competitions play next?", asked once per browsing session.
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
 * Only an ANSWER is kept. A failure to answer is not one: the endpoint reports every calendar
 * failure as HTTP 200 with `known: false`, so keeping those here would pin one bad minute —
 * Redis down, a sweep in flight, a provider timing out — to the whole session, and no amount of
 * reloading a day would get past it. `null` means nothing is remembered and the next empty day
 * asks again — and an answer is dropped back to `null` the moment the kickoff it names is behind
 * us, because from then on it describes the past. See `stillAhead`.
 */
let answered: UpcomingAnswer | null = null

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
 * Whether a remembered answer still describes the future.
 *
 * The endpoint filters its calendar against the clock of the request that asked, which is what
 * stops a reader being told football resumes on a day that has passed. That filter is applied
 * once, to the answer; remembering the answer for the life of the tab would outlive it. A tab
 * left open across the resumption — over a weekend, or simply overnight — would go on naming a
 * fixture that has since been played as the next one there is.
 *
 * So the earliest kickoff of the answer is also its expiry: once that moment is behind us the
 * answer has stopped being about the future and the next reader of an empty day asks again. An
 * answer that names no instant cannot be judged this way and is kept, which is safe because an
 * answer with no kickoff makes no claim about when football resumes.
 */
function stillAhead(answer: UpcomingAnswer, now: number): boolean {
  const earliest = answer.next_kickoff ? Date.parse(answer.next_kickoff) : NaN
  return Number.isNaN(earliest) || earliest > now
}

/** The shared answer, fetching it if this session has not been given one yet. Never rejects. */
export function upcomingAnswer(): Promise<UpcomingAnswer | null> {
  if (answered !== null && !stillAhead(answered, Date.now())) answered = null
  if (answered !== null) return Promise.resolve(answered)
  if (pending !== null) return pending
  pending = fetchUpcoming().then(result => {
    pending = null
    if (result !== null && result.known) answered = result
    return result
  })
  return pending
}
