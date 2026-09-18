import React, { useCallback, useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { ArrowRightIcon, MagnifyingGlassIcon } from '@heroicons/react/24/outline'
import { Match } from '@/types'
import { footballDataService } from '@/services/football-data.service'
import { describeError } from '@/services/backend-match-data.service'
import { localDateString, STORED_ONLY } from '@/services/match-data-source'
import { filterLiveAndScheduledMatches } from '@/utils/matchFilters'
import CompetitionChip from '@/components/ui/CompetitionChip'
import EmptyState from '@/components/ui/EmptyState'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'

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
 * is a single control: kick-off, the two clubs, the competition, and whether anything is already
 * published on it. No UUID and no provider id anywhere — those live behind the composer's advanced
 * section, for the rare case where somebody genuinely has one to paste.
 *
 * NO PROVIDER CALL IS MADE. Every read passes `STORED_ONLY`, so the backend answers from rows it
 * already holds: paging through a week of dates spends nothing from the forecast allowance.
 */
export interface FixturePickerProps {
  onChoose: (match: Match) => void
  /** The action each row offers, e.g. "Choose" or "Write a prediction". */
  actionLabel?: string
  /** Day to open on. Defaults to today in the viewer's own calendar. */
  initialDate?: string
  /** Rendered above the list, inside the same card. */
  heading?: React.ReactNode
  className?: string
}

/** The competitions present in a day's fixtures, with how many each has. */
interface CompetitionOption {
  id: string
  name: string
  logo: string | null
  count: number
}

/** A published expert prediction, or a model forecast, or neither — said in words, not a colour. */
function coverageNote(match: Match): { label: string; className: string } {
  if (match.expertPrediction) {
    return { label: 'Expert prediction published', className: 'bg-primary-900/60 text-primary-200' }
  }
  if (match.providerForecast?.state === 'available') {
    return { label: 'Model forecast held', className: 'bg-dark-700 text-secondary-200' }
  }
  return { label: 'No forecast held', className: 'bg-dark-700 text-secondary-300' }
}

/**
 * One fixture as a single control.
 *
 * Every text node that can be long sits in a `min-w-0` box and truncates, the kick-off column has a
 * fixed narrow width, and the badges wrap onto their own line. That combination is what keeps the
 * row inside 390px however long a club is called.
 */
const PickerRow: React.FC<{ match: Match; actionLabel: string; onChoose: (match: Match) => void }> = ({
  match, actionLabel, onChoose,
}) => {
  const coverage = coverageNote(match)
  const live = match.status === 'live' || match.status === 'halftime'

  return (
    <li className="border-b border-dark-800 last:border-b-0">
      <button
        type="button"
        onClick={() => onChoose(match)}
        className="focus-ring-inset tap-target-row flex w-full flex-col gap-1 px-2 py-2.5 text-left transition-colors hover:bg-dark-800/60 sm:px-3"
        aria-label={`${actionLabel}: ${match.homeTeam.name} versus ${match.awayTeam.name}, ${match.league.name}, kick-off ${match.time}`}
      >
        <div className="flex w-full items-center gap-2">
          <span className="flex w-12 flex-shrink-0 flex-col items-center text-center">
            {live
              ? <span className="text-[11px] font-semibold uppercase tracking-wide text-success-300">Live</span>
              : <time className="num text-sm font-semibold text-white" dateTime={match.kickoffUtc ?? undefined}>{match.time}</time>}
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
          <span className={clsx('rounded-full px-2 py-0.5 text-[11px]', coverage.className)}>{coverage.label}</span>
        </span>
      </button>
    </li>
  )
}

const FixturePicker: React.FC<FixturePickerProps> = ({
  onChoose, actionLabel = 'Choose', initialDate, heading, className,
}) => {
  const [date, setDate] = useState(initialDate ?? localDateString(0))
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
        // A failed request is not an empty day. The list is cleared and the failure is stated.
        if (!cancelled) {
          setError(describeError(err))
          setMatches([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [date, reloadToken])

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

  return (
    <div className={clsx('card overflow-hidden', className)}>
      {heading && <div className="border-b border-dark-700 p-4">{heading}</div>}

      {/* ------------------------------------------------------------------ day */}
      <div className="border-b border-dark-700 p-3 sm:p-4">
        <label htmlFor="picker-date" className="form-label">Match day</label>
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
          {[0, 1, 2].map(offset => {
            const day = localDateString(offset)
            const label = offset === 0 ? 'Today' : offset === 1 ? 'Tomorrow' : 'In two days'
            return (
              <button
                key={day}
                type="button"
                onClick={() => setDate(day)}
                aria-pressed={date === day}
                className={clsx(
                  'focus-ring rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
                  date === day ? 'bg-primary-700 text-white' : 'bg-dark-800 text-secondary-200 hover:bg-dark-700',
                )}
              >
                {label}
              </button>
            )
          })}
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------ filters */}
      <div className="space-y-3 border-b border-dark-700 p-3 sm:p-4">
        <div>
          <label htmlFor="picker-search" className="sr-only">Filter by team or competition</label>
          <div className="relative">
            <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-400" aria-hidden="true" />
            <input
              id="picker-search"
              type="search"
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Team or competition"
              className="form-input w-full py-2 pl-9"
            />
          </div>
        </div>

        {competitions.length > 1 && (
          // The chip strip scrolls inside itself. The page never scrolls sideways because of it.
          <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 no-scrollbar" role="group" aria-label="Filter by competition">
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
            Only fixtures with no expert prediction yet
          </label>
          {filtersActive && (
            <button type="button" onClick={clearFilters} className="focus-ring text-xs font-medium text-primary-300 hover:text-primary-200">
              Clear filters
            </button>
          )}
        </div>

        <p className="text-xs text-secondary-400" aria-live="polite">
          {loading
            ? 'Loading fixtures…'
            : <>Showing <span className="num font-semibold text-secondary-200">{visible.length}</span> of {openFixtures.length} fixtures on this day.</>}
        </p>
      </div>

      {/* ------------------------------------------------------------------ the list */}
      {loading ? (
        <div className="p-8"><LoadingSpinner /></div>
      ) : error ? (
        <div className="p-4">
          <EmptyState
            tone="failed"
            title="The fixture list could not be loaded"
            description={error}
            variant="inline"
            action={
              <button type="button" onClick={retry} className="btn btn-sm btn-secondary">
                Try again
              </button>
            }
          />
        </div>
      ) : visible.length === 0 ? (
        <div className="p-4">
          <EmptyState
            tone="empty"
            title={filtersActive ? 'No fixture matches these filters' : 'No fixtures to write about on this day'}
            description={filtersActive
              ? 'Widen the filters, or move to another day.'
              : 'Finished, postponed and cancelled fixtures are left out. Try another day.'}
            variant="inline"
            action={filtersActive
              ? <button type="button" onClick={clearFilters} className="btn btn-sm btn-secondary">Clear filters</button>
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
