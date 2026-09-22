import React, { useEffect, useState } from 'react'
import { backendInstant, formatIsoDate, formatTime, zonedDateString } from '@/i18n'
import { useLocale } from '@/i18n/react'
import useAuth from '@/hooks/useAuth'
import { usePersonalPreferences } from '@/services/favourites.service'
import { UpcomingAnswer, onReaderReturns, upcomingAnswer } from './nextFixtures'

/**
 * Whether what a read came back with may replace what is on screen.
 *
 * A READ EXISTS TO IMPROVE WHAT IS THERE AND MAY NEVER SUBTRACT FROM IT. Two of the things it can
 * come back with are not answers: `null`, a request that did not come back with one, and a reply
 * whose `known` is false, which is the endpoint saying nobody could tell it — an outage behind
 * it, or its own backoff and daily ceiling refusing another calendar sweep. Neither is worth
 * more than the named fixtures a reader is in the middle of reading, and putting either in their
 * place takes away what we already had because we went looking for something better. A date some
 * hours old is a smaller error than a blank where a date was.
 *
 * SO A READ THAT CANNOT ANSWER KEEPS THE NOTICE THAT IS THERE, which is the promise the fixture
 * page makes on the same trigger: see `read('return')` in src/pages/MatchDetailPage.tsx, where a
 * failed re-read keeps the fixture on screen and changes only what can be said about its age.
 *
 * WITH NOTHING ON SCREEN THERE IS NOTHING TO LOSE, and then anything beats a blank: "we could not
 * find out" is the honest sentence for a reader who has been told nothing at all, and
 * `previous === null` is what lets them have it.
 */
function noticeAfter(
  previous: UpcomingAnswer | null, result: UpcomingAnswer | null,
): UpcomingAnswer | null {
  if (result === null) return previous
  return result.known || previous === null ? result : previous
}

/**
 * What an empty matchday can add: when these competitions play next, and who plays.
 *
 * From 2026-09-21 the six covered competitions were in the international break, the first fixture
 * in any of them eighteen days out. Every matchday list in between was correctly empty, and "no
 * matches stored for this date" was a true sentence that left the reader nowhere to go. This is
 * the rest of the sentence.
 *
 * WHAT IT WILL NOT SAY. Nothing is rendered until an answer arrives, and an answer whose `known`
 * is false is reported as not knowing — or, when it arrives over a notice already on screen,
 * changes nothing at all; see `noticeAfter` above. A fixture is never invented, and a silence is
 * never dressed up as "no football is scheduled": the outcomes below are different states, and
 * the two that look alike on screen — nothing asked yet and nothing knowable — are the two that
 * must never be shown as a fact about football.
 *
 * An answer may also be PARTIAL: read from some of the covered competitions and not the others,
 * which `unanswered` names. What is named then is still true — these fixtures are coming — but
 * it is not the whole calendar, so the sentence above the list says so and the reassuring
 * version is not used. A partial answer with no fixture in it says nothing at all about
 * football: the competitions that answered have nothing to come, and the rest were never asked.
 *
 * See nextFixtures.ts for what asking costs and how often it is really asked.
 */
const NextFixturesNote: React.FC = () => {
  const { t } = useLocale()
  const { user } = useAuth()

  /**
   * The reader's automatic-updates setting, and the pause that governs it.
   *
   * The same switch every other self-starting read in this application waits on — the
   * saved-matches store and the followed-fixtures feed both gate their polling on
   * `personalPreferencesStore.isOn('liveUpdates')` — reached through the hook that binds it to
   * whoever is signed in. A switch of this note's own would be a setting the reader was never
   * shown, could not find, and would have to turn off twice.
   */
  const automaticUpdates = usePersonalPreferences(user?.id ?? null).isOn('liveUpdates')

  const [answer, setAnswer] = useState<UpcomingAnswer | null>(null)

  useEffect(() => {
    let cancelled = false
    void upcomingAnswer().then(result => {
      if (!cancelled) setAnswer(previous => noticeAfter(previous, result))
    })
    return () => { cancelled = true }
  }, [])

  /**
   * AND AGAIN WHEN THE READER COMES BACK TO THE TAB, which is the only other time this is read.
   *
   * The sentence above this list names a kickoff, and a kickoff arrives whether or not anybody is
   * watching. Read only on mount, this note would sit in a background window calling a fixture
   * that has been played the next one there is, and across a day of that it would describe a
   * calendar that has since been revised. Coming back is both when that matters to the reader and
   * when they expect what they are looking at to be current.
   *
   * NO INTERVAL, AND THAT IS THE POINT. A timer spends on a page nobody is looking at, and the
   * spend here is not only ours: a miss reaches `/matches/upcoming`, which reads one competition
   * calendar per covered competition.
   *
   * ONE READER IS STILL ONE REQUEST. Every path goes through `upcomingAnswer()`, which holds this
   * session's answer and the request in flight, so the focus/visibilitychange pair a browser
   * sends for a single return is served twice from the same place, as is every other empty day on
   * screen at the time. A return reaches the network only when that session has nothing current
   * to serve it with: no answer — the kickoff one named has passed, or it has aged out — AND no
   * recent failure to get one, because a refusal to spend and an outage are remembered too, for
   * as long as the calendar behind the endpoint could not have tried again (`FAILURE_TTL_MS`).
   * Nothing here re-asks on a schedule of its own, and nothing asks twice for a good answer.
   *
   * WHAT COMES BACK REPLACES THE NOTICE ONLY IF IT IS BETTER THAN THE NOTICE — `noticeAfter`
   * above. A return that meets a bad minute leaves the reader reading exactly what they were.
   *
   * A HIDDEN TAB DOES NOTHING AT ALL: `onReaderReturns` tests visibility before calling anything,
   * and with automatic updates off no listener is registered in the first place.
   */
  useEffect(() => {
    if (!automaticUpdates) return undefined
    let cancelled = false
    const stop = onReaderReturns(() => {
      void upcomingAnswer().then(result => {
        if (!cancelled) setAnswer(previous => noticeAfter(previous, result))
      })
    })
    return () => { cancelled = true; stop() }
  }, [automaticUpdates])

  // Not answered yet, or asked and not answered at all. The empty state around this already says
  // that it describes what the store holds rather than what is being played, so there is nothing
  // to add and nothing that may be claimed.
  if (answer === null) return null

  if (!answer.known) {
    return (
      <span className="mt-2 block text-xs text-secondary-400" data-testid="matchday-upcoming-unknown">
        {t('matchday.upcoming.unknown')}
      </span>
    )
  }

  const partial = answer.unanswered.length > 0

  if (answer.fixtures.length === 0) {
    // "The calendars list nothing to come" is a claim about every covered competition, so it is
    // available only when every one of them was read.
    return partial ? (
      <span className="mt-2 block text-xs text-secondary-400" data-testid="matchday-upcoming-unknown">
        {t('matchday.upcoming.unknown')}
      </span>
    ) : (
      <span className="mt-2 block text-xs text-secondary-400" data-testid="matchday-upcoming-none">
        {t('matchday.upcoming.none')}
      </span>
    )
  }

  const resumesAt = backendInstant(answer.next_kickoff).at

  return (
    <span className="mt-3 block text-left" data-testid="matchday-upcoming">
      {resumesAt && (
        <span className="block text-sm font-medium text-secondary-100">
          {/*
            `next_kickoff` is the earliest of the whole answer rather than of the capped list, so
            this date stays true however few fixtures are named below. The day it falls on is read
            in the reader's CHOSEN zone, which is neither the device's nor UTC: a 23:00 UTC kickoff
            is already the next day east of Greenwich, and the date strip beside this list counts
            days the same way.

            A partial answer gets the sentence that claims less: the competitions nobody could ask
            about may play before this date, so it is the earliest fixture we know of and not the
            day football comes back.
          */}
          {t(partial ? 'matchday.upcoming.resumesPartial' : 'matchday.upcoming.resumes',
             { date: formatIsoDate(zonedDateString(0, resumesAt)) })}
        </span>
      )}
      <span className="mt-1 block text-xs text-secondary-400">{t('matchday.upcoming.heading')}</span>
      <ul className="mt-1 space-y-0.5 text-xs text-secondary-300">
        {answer.fixtures.map((fixture, index) => (
          <li key={`${fixture.kickoff_utc}-${fixture.home}-${fixture.away}-${index}`}>
            {t('matchday.upcoming.fixture', {
              home: fixture.home ?? '',
              away: fixture.away ?? '',
              competition: fixture.competition?.name ?? '',
              time: formatTime(backendInstant(fixture.kickoff_utc).at) ?? '',
            })}
          </li>
        ))}
      </ul>
    </span>
  )
}

export default NextFixturesNote
