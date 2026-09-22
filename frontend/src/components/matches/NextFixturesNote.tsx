import React, { useEffect, useState } from 'react'
import { backendInstant, formatIsoDate, formatTime, zonedDateString } from '@/i18n'
import { useLocale } from '@/i18n/react'
import { UpcomingAnswer, upcomingAnswer } from './nextFixtures'

/**
 * What an empty matchday can add: when these competitions play next, and who plays.
 *
 * From 2026-09-21 the six covered competitions were in the international break, the first fixture
 * in any of them eighteen days out. Every matchday list in between was correctly empty, and "no
 * matches stored for this date" was a true sentence that left the reader nowhere to go. This is
 * the rest of the sentence.
 *
 * WHAT IT WILL NOT SAY. Nothing is rendered until an answer arrives, and an answer whose `known`
 * is false is reported as not knowing. A fixture is never invented, and a silence is never
 * dressed up as "no football is scheduled": the outcomes below are different states, and the two
 * that look alike on screen — nothing asked yet and nothing knowable — are the two that must
 * never be shown as a fact about football.
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
  const [answer, setAnswer] = useState<UpcomingAnswer | null>(null)

  useEffect(() => {
    let cancelled = false
    upcomingAnswer().then(result => { if (!cancelled) setAnswer(result) })
    return () => { cancelled = true }
  }, [])

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
