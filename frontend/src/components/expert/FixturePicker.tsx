import React, { useCallback, useEffect, useId, useMemo, useState } from 'react'
import clsx from 'clsx'
import { ArrowRightIcon, MagnifyingGlassIcon } from '@heroicons/react/24/outline'
import { Match } from '@/types'
import { footballDataService } from '@/services/football-data.service'
import { localDateString, STORED_ONLY } from '@/services/match-data-source'
import { filterLiveAndScheduledMatches, hasMatchKickedOff } from '@/utils/matchFilters'
import { getErrorMessage } from '@/utils/errors'
import { FORECAST_COVERAGE_CLASS, FORECAST_COVERAGE_LABEL, forecastCoverage } from '@/utils/forecastCoverage'
import CompetitionChip from '@/components/ui/CompetitionChip'
import EmptyState from '@/components/ui/EmptyState'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { formatIsoDate, formatNumber, formatTime, zoneLabel } from '@/i18n'
import { useLocale, useT } from '@/i18n/react'

/**
 * One filtered fixture list — the expert's way of saying which match they are writing about.
 *
 * WHAT THIS REPLACES. The picker used to be two lists, "Today" and "Tomorrow", each rendered as a
 * tall three-column card carrying the venue, the internal UUID and the provider's fixture id. A
 * busy Saturday meant scrolling past forty cards to find one match, the football context (when it
 * kicks off, which competition) was buried under identifiers no expert has any use for, and the
 * fixed three-column team grid pushed the page sideways on a phone: a 23-match day measured 11 CSS
 * pixels of horizontal overflow at 390px.
 *
 * WHAT IT IS NOW. One list, one day at a time, narrowed by competition and by team name. Each row
 * is a single control: kick-off, the two clubs, the competition, and what is already published on
 * it. No UUID and no provider id anywhere — those live behind the composer's advanced section, for
 * the rare case where somebody genuinely has one to paste.
 *
 * NO PROVIDER CALL IS MADE. Every read passes `STORED_ONLY`, so the backend answers from rows it
 * already holds: paging through a week of dates spends nothing from the forecast allowance.
 *
 * IN THE READER'S LANGUAGE AND ZONE (QA finding 7). Every word is the catalogue's `expert.picker.*`
 * (with `matchday.relative.*`, `fixture.live`, `brief.noForecastHeld` and `expert.retry` from core),
 * where it used to be twenty-two English literals; ExpertMatchSelectionPage rendered a translated
 * copy of this list in the meantime. The kick-off is formatted from `kickoffUtc` on every render in
 * the zone the reader CHOSE — `match.time` is the mapper's one-off formatting and only the fallback
 * for a payload with no instant — and the zone is a dependency of the fetch, because the day asked
 * for is a UTC window bounded by that zone's offsets. The day and the zone are spelled out above
 * the list, so nobody has to infer which calendar day the times belong to.
 *
 * THE FORECAST BADGE SAYS WHICH OF FOUR THINGS IS TRUE (QA finding 9): current, stored but out of
 * date, kept for reference after kick-off, or absent — utils/forecastCoverage.ts, from the list
 * payload alone. A published expert prediction is a SEPARATE badge beside it, never a replacement:
 * what an expert has published says nothing about the model's forecast.
 */
export interface FixturePickerProps {
  onChoose: (match: Match) => void
  /** The action each row offers, e.g. `expert.action.writePrediction`. Already translated. */
  actionLabel: string
  /** Day to open on. Defaults to today in the reader's chosen zone. */
  initialDate?: string
  /** Rendered above the list, inside the same card. */
  heading?: React.ReactNode
  className?: string
}

/** Today, tomorrow, the day after. Relative to the reader's chosen zone, never the device's. */
const DAY_OFFSETS = [0, 1, 2] as const

/** The competitions present in a day's fixtures, with how many each has. */
interface CompetitionOption {
  id: string
  name: string
  logo: string | null
  count: number
}

/**
 * One fixture as a single control.
 *
 * Every text node that can be long sits in a `min-w-0` box and truncates, the kick-off column has a
 * fixed narrow width, and the badges wrap onto their own line. That combination is what keeps the
 * row inside 390px however long a club is called.
 *
 * The row's accessible name is its aria-label — `expert.picker.rowAction`, which the live suite
 * matches by "Write a prediction:" and which is unchanged — and an aria-label hides the badges from
 * a screen reader. So the badges are the button's accessible DESCRIPTION, in the order they are
 * drawn: the forecast, the expert prediction, the kicked-off warning.
 */
const PickerRow: React.FC<{ match: Match; actionLabel: string; onChoose: (match: Match) => void }> = ({
  match, actionLabel, onChoose,
}) => {
  const t = useT()
  const coverage = forecastCoverage(match)
  const live = match.status === 'live' || match.status === 'halftime'
  // Re-derived from the instant on every render, in the chosen zone.
  const kickoff = formatTime(match.kickoffUtc) ?? match.time
  /*
   * Kicked off — by the clock or by the status — so a prediction published now is never scored.
   * The fixture is still offered (that is the posting policy, unchanged); the row says what a
   * publish on it would be.
   */
  const kickedOff = hasMatchKickedOff(match)
  const badgeId = useId()
  const forecastId = `${badgeId}-forecast`
  const expertId = `${badgeId}-expert`
  const kickedOffId = `${badgeId}-kicked-off`
  const describedBy = [forecastId, match.expertPrediction ? expertId : null, kickedOff ? kickedOffId : null]
    .filter(Boolean).join(' ')

  return (
    <li className="border-b border-dark-800 last:border-b-0">
      <button
        type="button"
        onClick={() => onChoose(match)}
        className="focus-ring-inset tap-target-row flex w-full flex-col gap-1 px-2 py-2.5 text-left transition-colors hover:bg-dark-800/60 sm:px-3"
        aria-label={t('expert.picker.rowAction', {
          action: actionLabel,
          home: match.homeTeam.name,
          away: match.awayTeam.name,
          competition: match.league.name,
          time: kickoff,
        })}
        aria-describedby={describedBy}
      >
        <div className="flex w-full items-center gap-2">
          <span className="flex w-12 flex-shrink-0 flex-col items-center text-center">
            {live
              ? <span className="text-[11px] font-semibold uppercase tracking-wide text-success-300">{t('fixture.live')}</span>
              : <time className="num text-sm font-semibold text-white" dateTime={match.kickoffUtc ?? undefined}>{kickoff}</time>}
          </span>

          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm text-white">{match.homeTeam.name}</span>
            <span className="block truncate text-sm text-secondary-100">{match.awayTeam.name}</span>
            <span className="block truncate text-[11px] text-secondary-400">{match.league.name}</span>
          </span>

          <span className="flex flex-shrink-0 items-center gap-1 text-primary-300">
            <span className="hidden text-xs font-medium sm:inline">{actionLabel}</span>
            <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
          </span>
        </div>

        <span className="flex flex-wrap gap-1 pl-14">
          <span id={forecastId} data-testid="picker-forecast" className={clsx('rounded-full px-2 py-0.5 text-[11px]', FORECAST_COVERAGE_CLASS[coverage])}>
            {t(FORECAST_COVERAGE_LABEL[coverage])}
          </span>
          {match.expertPrediction && (
            <span id={expertId} data-testid="picker-expert" className="rounded-full bg-primary-900/60 px-2 py-0.5 text-[11px] text-primary-200">
              {t('expert.picker.expertPublished')}
            </span>
          )}
          {kickedOff && (
            <span id={kickedOffId} data-testid="picker-kicked-off" className="rounded-md bg-warning-900/40 px-2 py-0.5 text-[11px] text-warning-200">
              {t('expert.picker.kickedOff')}
            </span>
          )}
        </span>
      </button>
    </li>
  )
}

const FixturePicker: React.FC<FixturePickerProps> = ({
  onChoose, actionLabel, initialDate, heading, className,
}) => {
  const t = useT()
  // The zone is read rather than assumed: it decides which calendar day "today" is, which UTC
  // window the backend is asked for, and what every kick-off below says. A change to it has to
  // reach all three, so it is a dependency of the fetch and not only of the formatting.
  const { zone } = useLocale()
  const [date, setDate] = useState(() => initialDate ?? localDateString(0))
  const [matches, setMatches] = useState<Match[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [competitionIds, setCompetitionIds] = useState<string[]>([])
  const [onlyWithoutExpert, setOnlyWithoutExpert] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)

  const retry = useCallback(() => setReloadToken(token => token + 1), [])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        // STORED_ONLY: the backend answers from what it already holds and makes no provider
        // request, so moving between days costs nothing from the daily allowance.
        const result = await footballDataService.getFixturesByDate(date, STORED_ONLY)
        if (!cancelled) setMatches(result)
      } catch (err) {
        console.error('Failed to load fixtures for the picker:', err)
        // A failed request is not an empty day. The list is cleared and the failure is stated:
        // the SERVER'S own words when it gave any, else its two translated sentences (503, timed
        // out), else nothing beyond the title — never a reason nobody gave. (`describeError`,
        // which this used, synthesised two English sentences of its own.)
        if (!cancelled) {
          setError(getErrorMessage(err, ''))
          setMatches([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
    // `zone` appears in nothing above and is a dependency on purpose — do not "clean it up".
    // The day this asks the backend for is a window bounded by the reader's own UTC offsets, so a
    // change of zone is a change of request even when the calendar date in the control has not
    // moved. Without it, a reader who switches zone keeps the previous zone's day of fixtures.
  }, [date, reloadToken, zone])

  /** Finished, postponed and cancelled fixtures are not something to publish a forecast on. */
  const openFixtures = useMemo(() => filterLiveAndScheduledMatches(matches), [matches])

  const competitions = useMemo<CompetitionOption[]>(() => {
    const byId = new Map<string, CompetitionOption>()
    openFixtures.forEach(match => {
      const id = match.league.id || match.league.name
      const existing = byId.get(id)
      if (existing) existing.count += 1
      else byId.set(id, { id, name: match.league.name, logo: match.league.logo ?? null, count: 1 })
    })
    return Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name))
  }, [openFixtures])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return openFixtures.filter(match => {
      if (competitionIds.length > 0 && !competitionIds.includes(match.league.id || match.league.name)) return false
      if (onlyWithoutExpert && match.expertPrediction) return false
      if (!needle) return true
      return match.homeTeam.name.toLowerCase().includes(needle)
        || match.awayTeam.name.toLowerCase().includes(needle)
        || match.league.name.toLowerCase().includes(needle)
    })
  }, [openFixtures, competitionIds, onlyWithoutExpert, query])

  const toggleCompetition = (id: string, next: boolean) => {
    setCompetitionIds(prev => (next ? [...prev, id] : prev.filter(entry => entry !== id)))
  }

  const clearFilters = () => {
    setQuery('')
    setCompetitionIds([])
    setOnlyWithoutExpert(false)
  }

  const filtersActive = query.trim() !== '' || competitionIds.length > 0 || onlyWithoutExpert

  /** Today / Tomorrow / In two days, recomputed each render so a zone change moves them. */
  const dayChips = DAY_OFFSETS.map(offset => ({
    day: localDateString(offset),
    label: offset === 0
      ? t('matchday.relative.today')
      : offset === 1
        ? t('matchday.relative.tomorrow')
        : t('expert.picker.dayAfterTomorrow'),
  }))

  return (
    <div className={clsx('card overflow-hidden', className)}>
      {heading && <div className="border-b border-dark-700 p-4">{heading}</div>}

      {/* ------------------------------------------------------------------ day */}
      <div className="border-b border-dark-700 p-3 sm:p-4">
        <label htmlFor="picker-date" className="form-label">{t('expert.picker.dayLabel')}</label>
        {/* The date input takes a full line below `sm`: squeezed into a shared row at 390px a
            native date control clips its own value, and "09" is not a date. */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            id="picker-date"
            type="date"
            value={date}
            onChange={event => event.target.value && setDate(event.target.value)}
            className="form-input num w-full py-2 sm:w-auto"
          />
          <div className="flex flex-wrap gap-2">
            {dayChips.map(chip => (
              <button
                key={chip.day}
                type="button"
                onClick={() => setDate(chip.day)}
                aria-pressed={date === chip.day}
                className={clsx(
                  'focus-ring rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
                  date === chip.day ? 'bg-primary-700 text-white' : 'bg-dark-800 text-secondary-200 hover:bg-dark-700',
                )}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>
        {/* Which calendar day, and in which zone, the kick-offs below belong to. A native date
            input states neither in words, and an expert judging whether a fixture is still
            prematch needs both. */}
        <p className="mt-2 text-xs text-secondary-400" data-testid="picker-day-shown">
          {t('expert.picker.dayShown', { date: formatIsoDate(date, false) })}
          {' · '}
          {t('matchday.timesIn', { zone: zoneLabel() })}
        </p>
      </div>

      {/* ------------------------------------------------------------------ filters */}
      <div className="space-y-3 border-b border-dark-700 p-3 sm:p-4">
        <div>
          <label htmlFor="picker-search" className="sr-only">{t('expert.picker.searchLabel')}</label>
          <div className="relative">
            <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-400" aria-hidden="true" />
            <input
              id="picker-search"
              type="search"
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder={t('expert.picker.searchPlaceholder')}
              className="form-input w-full py-2 pl-9"
            />
          </div>
        </div>

        {competitions.length > 1 && (
          // The chip strip scrolls inside itself. The page never scrolls sideways because of it.
          <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 no-scrollbar" role="group" aria-label={t('expert.picker.competitionGroup')}>
            {competitions.map(competition => (
              <CompetitionChip
                key={competition.id}
                name={competition.name}
                logo={competition.logo}
                count={competition.count}
                selected={competitionIds.includes(competition.id)}
                onToggle={next => toggleCompetition(competition.id, next)}
                size="sm"
                className="flex-shrink-0"
              />
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="flex items-center gap-2 text-xs text-secondary-200">
            <input
              type="checkbox"
              checked={onlyWithoutExpert}
              onChange={event => setOnlyWithoutExpert(event.target.checked)}
              className="focus-ring h-4 w-4 rounded border-dark-600 bg-dark-800 text-primary-500"
            />
            {t('expert.picker.onlyWithoutExpert')}
          </label>
          {filtersActive && (
            <button type="button" onClick={clearFilters} className="focus-ring text-xs font-medium text-primary-300 hover:text-primary-200">
              {t('expert.picker.clearFilters')}
            </button>
          )}
        </div>

        {/* One sentence, not a sentence assembled around a styled number: the count sits inside
            the message so each language decides where it goes and what agrees with it. */}
        <p className="num text-xs text-secondary-400" aria-live="polite" data-testid="picker-count">
          {loading
            ? t('expert.picker.loading')
            : t('expert.picker.showing', {
              shown: formatNumber(visible.length),
              total: formatNumber(openFixtures.length),
            })}
        </p>
      </div>

      {/* ------------------------------------------------------------------ the list */}
      {loading ? (
        <div className="p-8"><LoadingSpinner /></div>
      ) : error !== null ? (
        <div className="p-4">
          <EmptyState
            tone="failed"
            title={t('expert.picker.loadFailed')}
            description={error || undefined}
            variant="inline"
            action={
              <button type="button" onClick={retry} className="btn btn-sm btn-secondary">
                {t('expert.retry')}
              </button>
            }
          />
        </div>
      ) : visible.length === 0 ? (
        <div className="p-4">
          <EmptyState
            tone="empty"
            title={filtersActive ? t('expert.picker.emptyFilteredTitle') : t('expert.picker.emptyDayTitle')}
            description={filtersActive ? t('expert.picker.emptyFilteredBody') : t('expert.picker.emptyDayBody')}
            variant="inline"
            action={filtersActive
              ? <button type="button" onClick={clearFilters} className="btn btn-sm btn-secondary">{t('expert.picker.clearFilters')}</button>
              : undefined}
          />
        </div>
      ) : (
        <ul>
          {visible.map(match => (
            <PickerRow key={match.id} match={match} actionLabel={actionLabel} onChoose={onChoose} />
          ))}
        </ul>
      )}
    </div>
  )
}

export default FixturePicker
