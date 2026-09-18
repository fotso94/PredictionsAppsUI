import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowPathIcon } from '@heroicons/react/24/outline'
import DateStrip, { DateStripDay } from '@/components/ui/DateStrip'
import CompetitionChip from '@/components/ui/CompetitionChip'
import FilterSheet, { ActiveFilter, FilterSummaryBar } from '@/components/ui/FilterSheet'
import EmptyState from '@/components/ui/EmptyState'
import DataSourceNotice from '@/components/ui/DataSourceNotice'
import ForecastSyncNotice from '@/components/ui/ForecastSyncNotice'
import { footballDataService } from '@/services/football-data.service'
import { describeError } from '@/services/backend-match-data.service'
import { DataSourceMeta, STORED_ONLY, localDateString } from '@/services/match-data-source'
import type { Match } from '@/types'
import FixtureList from './FixtureList'
import MatchFilterControls from './MatchFilterControls'
import { competitionOptions, groupByCompetition } from './fixtureGrouping'
import {
  MARKET_OPTIONS, SOURCE_OPTIONS, STATUS_OPTIONS, WorkspaceState,
  activeFilterCount, clearedFilters, matchesWorkspaceFilters, readWorkspaceState, toggleValue,
  writeWorkspaceState,
} from './workspaceState'

/**
 * The matchday workspace: one date, one list of fixtures, and the smallest set of controls that
 * can get a reader from "what is on" to "show me that match".
 *
 * WHY THIS REPLACED TWO NEAR-IDENTICAL DATE PAGES. The research measured the cost of the old
 * shape: on the daily list an always-expanded panel of league, market and confidence filters filled
 * most of the first screens, so a reader who came to look at matches scrolled past a wall of
 * controls to reach one. Here the controls are a date strip and a row of competition chips — about
 * one hundred pixels — and everything else is behind a single Filters button that opens a sheet.
 * The fixtures start immediately below.
 *
 * WHAT IS ALWAYS VISIBLE. Every active filter is listed as its own removable chip, at every width.
 * A filter the reader cannot see is a filter they will not think to remove, and "no matches today"
 * produced by a forgotten competition filter is a false statement about the day.
 *
 * REQUESTS. Every read here is `STORED_ONLY` — `refresh=false`, answered from rows the backend
 * already holds. Paging through a week of dates, toggling competitions and reopening the sheet
 * therefore spend no provider allowance at all. What that costs is freshness, and freshness is not
 * hidden: the row's own provenance line and the notices above the list state how old the numbers
 * are and whether refreshes are paused.
 *
 * STATE LIVES IN THE URL. See workspaceState.ts — going into a fixture and pressing Back restores
 * the list exactly, because the browser restored the query string.
 */

export interface MatchdayWorkspaceProps {
  /** The day shown when the URL names none. */
  defaultDate: string
  /** Heading above the list, e.g. "Today's matches". */
  title: string
  /**
   * A sentence explaining what the list is. Rendered UNDER the fixtures, never above them: it was
   * measured taking four lines at 390px, and four lines of explanation in front of the first
   * fixture is exactly the problem this page was rebuilt to remove.
   */
  footnote?: string
  /**
   * Set when the route's own path already names `defaultDate` (/predictions/today). While that day
   * is selected the `date` parameter is left out of the URL, and choosing any other day moves to
   * the general workspace so the path never contradicts what is on screen.
   */
  presetRoute?: boolean
  /** `panel` is the homepage's shorter form: no date strip, a capped list, a link to the rest. */
  variant?: 'page' | 'panel'
  /** Cap on rendered fixtures. The count above the list always states the real total. */
  limit?: number
  /** Where the full workspace lives, for the panel's link. */
  moreHref?: string
  /** Extra id for the list region, so a skip link can target it. */
  listId?: string
  /** 1 when the workspace heading IS the page's heading, 2 when the page has its own above it. */
  headingLevel?: 1 | 2
}

/** Where a date change lands when the current path names a fixed day. */
const WORKSPACE_PATH = '/matches'

/** How many competition chips sit above the list before the rest move into the sheet. */
const VISIBLE_CHIPS = 8

/** One shared empty array, so "nothing loaded" does not produce a new identity every render. */
const NO_MATCHES: Match[] = []

const LONG_DATE = new Intl.DateTimeFormat(undefined, {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
})

function formatDay(date: string): string {
  const at = new Date(`${date}T12:00:00`)
  return Number.isNaN(at.getTime()) ? date : LONG_DATE.format(at)
}

function relativeDay(date: string): string | null {
  if (date === localDateString(0)) return 'Today'
  if (date === localDateString(1)) return 'Tomorrow'
  if (date === localDateString(-1)) return 'Yesterday'
  return null
}

/** What we know about the chosen day. `status` never collapses "failed" into "empty". */
interface DayData {
  status: 'loading' | 'ready' | 'error'
  date: string
  matches: Match[]
  meta: DataSourceMeta | null
  error: string | null
}

const MatchdayWorkspace: React.FC<MatchdayWorkspaceProps> = ({
  defaultDate,
  title,
  footnote,
  presetRoute = false,
  variant = 'page',
  limit,
  moreHref,
  listId = 'matchday-fixtures',
  headingLevel = 2,
}) => {
  const Heading = (headingLevel === 1 ? 'h1' : 'h2') as 'h1' | 'h2'
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [sheetOpen, setSheetOpen] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const [day, setDay] = useState<DayData>({
    status: 'loading', date: defaultDate, matches: [], meta: null, error: null,
  })

  const state = useMemo(
    () => readWorkspaceState(searchParams, defaultDate),
    [searchParams, defaultDate],
  )
  const { date } = state

  useEffect(() => {
    let cancelled = false
    setDay(current => ({ ...current, status: 'loading', date, error: null }))

    footballDataService.getFixturesByDateWithMeta(date, STORED_ONLY)
      .then(result => {
        if (cancelled) return
        setDay({ status: 'ready', date, matches: result.matches, meta: result.meta, error: null })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        // A failed request is not an empty day. The list must say the request failed and offer a
        // retry, never "no matches on this date", which would be a claim about the world made out
        // of a network error.
        setDay({ status: 'error', date, matches: [], meta: null, error: describeError(error) })
      })

    return () => { cancelled = true }
  }, [date, reloadToken])

  /** Write `next` back into the URL, moving off a fixed-day route when the day changes. */
  const apply = useCallback((next: WorkspaceState) => {
    const leavingPresetDay = presetRoute && next.date !== defaultDate
    const params = writeWorkspaceState(searchParams, next, { omitDate: presetRoute && !leavingPresetDay })
    if (leavingPresetDay) {
      // Replace rather than push: a date strip the reader is scrubbing through should not fill the
      // back button with a step per day. The fixture they open next is the entry Back returns from.
      navigate({ pathname: WORKSPACE_PATH, search: `?${params.toString()}` }, { replace: true })
      return
    }
    setSearchParams(params, { replace: true })
  }, [defaultDate, navigate, presetRoute, searchParams, setSearchParams])

  const setDate = useCallback((next: string) => {
    // Filters are carried over deliberately: changing the day is not a request to stop caring
    // about the Bundesliga.
    apply({ ...state, date: next })
  }, [apply, state])

  // Only a SUCCESSFUL load produces fixtures. While loading or after a failure this is empty, and
  // the branches below are careful never to describe that emptiness as "no matches on this date".
  const dayMatches = useMemo(
    () => (day.status === 'ready' ? day.matches : NO_MATCHES),
    [day.status, day.matches],
  )
  const competitions = useMemo(() => competitionOptions(dayMatches), [dayMatches])
  const visible = useMemo(
    () => dayMatches.filter(match => matchesWorkspaceFilters(match, state)),
    [dayMatches, state],
  )
  const shown = typeof limit === 'number' ? visible.slice(0, limit) : visible
  const groups = useMemo(() => groupByCompetition(shown), [shown])

  const days = useMemo<DateStripDay[]>(() => {
    // The strip normally runs from yesterday; when the reader has jumped to a date outside that
    // window it runs from the day before the one they chose, so the selection is always on it.
    const first = localDateString(-1)
    const last = localDateString(7)
    const anchor = date >= first && date <= last ? new Date() : new Date(`${date}T12:00:00`)
    const valid = !Number.isNaN(anchor.getTime())
    return Array.from({ length: 9 }, (_, index) => {
      const entry = localDateString(index - 1, valid ? anchor : new Date())
      return {
        date: entry,
        // Only the day we actually loaded has a count. Passing 0 for the others would claim they
        // are empty when nobody has looked at them.
        count: entry === day.date && day.status === 'ready' ? day.matches.length : undefined,
      }
    })
  }, [date, day.date, day.status, day.matches.length])

  const activeFilters = useMemo<ActiveFilter[]>(() => {
    const chips: ActiveFilter[] = []
    for (const id of state.competitions) {
      const known = competitions.find(option => option.id === id)
      chips.push({
        id: `comp:${id}`,
        group: 'Competition',
        // A competition filtered on a day that has no such fixtures still names itself, from the
        // URL, rather than turning into an anonymous chip the reader cannot identify.
        label: known?.name ?? 'Selected competition',
        onRemove: () => apply({ ...state, competitions: toggleValue(state.competitions, id, false) }),
      })
    }
    for (const market of state.markets) {
      chips.push({
        id: `market:${market}`,
        group: 'Market',
        label: MARKET_OPTIONS.find(option => option.value === market)?.label ?? market,
        onRemove: () => apply({ ...state, markets: toggleValue(state.markets, market, false) }),
      })
    }
    for (const source of state.sources) {
      chips.push({
        id: `source:${source}`,
        group: 'Source',
        label: SOURCE_OPTIONS.find(option => option.value === source)?.label ?? source,
        onRemove: () => apply({ ...state, sources: toggleValue(state.sources, source, false) }),
      })
    }
    if (state.status !== 'all') {
      chips.push({
        id: `status:${state.status}`,
        group: 'Showing',
        label: STATUS_OPTIONS.find(option => option.value === state.status)?.label ?? state.status,
        onRemove: () => apply({ ...state, status: 'all' }),
      })
    }
    return chips
  }, [apply, competitions, state])

  const filtered = activeFilterCount(state) > 0
  const relative = relativeDay(date)
  const chipRow = competitions.slice(0, VISIBLE_CHIPS)
  const hiddenChips = competitions.length - chipRow.length

  const body = () => {
    if (day.status === 'loading') {
      return (
        <div className="py-10 text-center" data-testid="matchday-loading">
          <div
            className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-b-2 border-primary-500"
            aria-hidden="true"
          />
          <p className="text-sm text-secondary-400" role="status">Loading matches&hellip;</p>
        </div>
      )
    }

    if (day.status === 'error') {
      return (
        <EmptyState
          tone="failed"
          title="These fixtures could not be loaded."
          description={
            <>
              <span className="block">{day.error}</span>
              <span className="mt-1 block text-xs text-secondary-400">
                This is a problem reaching our own service. It is not a statement about what is on
                this date.
              </span>
            </>
          }
          action={
            <button
              type="button"
              onClick={() => setReloadToken(token => token + 1)}
              className="tap-target-row focus-ring inline-flex items-center gap-2 rounded-lg bg-primary-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-800"
              data-testid="matchday-retry"
            >
              <ArrowPathIcon className="h-4 w-4" aria-hidden="true" />
              Retry
            </button>
          }
          data-testid="matchday-error"
        />
      )
    }

    if (dayMatches.length === 0) {
      return (
        <EmptyState
          tone="empty"
          title="No matches on this date."
          description={`Nothing is stored for ${formatDay(date)}. Pick another day above.`}
          data-testid="matchday-empty"
        />
      )
    }

    if (visible.length === 0) {
      return (
        <EmptyState
          tone="empty"
          title="No matches match your filters."
          description={`${dayMatches.length} ${dayMatches.length === 1 ? 'fixture is' : 'fixtures are'} stored for ${formatDay(date)}; none of them match every filter you have set.`}
          action={
            <button
              type="button"
              onClick={() => apply(clearedFilters(state))}
              className="tap-target-row focus-ring rounded-lg border border-dark-600 bg-dark-800 px-4 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
            >
              Clear all filters
            </button>
          }
          data-testid="matchday-filtered-empty"
        />
      )
    }

    return (
      <>
        <FixtureList groups={groups} />
        {moreHref && (
          <p className="mt-4 text-center">
            {/* The reader's filters travel with them: opening the full list must not quietly widen
                what they asked to see. */}
            <Link
              to={{ pathname: moreHref, search: searchParams.toString() }}
              className="tap-target-row focus-ring inline-flex items-center rounded-lg border border-dark-600 bg-dark-800 px-4 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
              data-testid="matchday-see-all"
            >
              {shown.length < visible.length
                ? `See all ${visible.length} matches`
                : 'Open the matchday workspace'}
            </Link>
          </p>
        )}
      </>
    )
  }

  return (
    <section aria-labelledby={`${listId}-heading`} data-testid="matchday-workspace">
      {/* Compact header: the day, and nothing that has to be scrolled past. */}
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <Heading id={`${listId}-heading`} className="text-xl font-bold text-white sm:text-2xl">{title}</Heading>
        <p className="text-sm text-secondary-400">
          {relative ? `${relative}, ${formatDay(date)}` : formatDay(date)}
        </p>
      </div>
      {variant === 'page' && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {/*
            `[&_[role=group]]:relative` is a workaround for a defect in DateStrip, which this
            package does not own (see the report's needs_other_owner note).
            Each day button in its horizontal scroller carries a `.sr-only` span, and `.sr-only` is
            `position: absolute`. An absolutely positioned element is only clipped by an ancestor's
            `overflow` when that ancestor is also its containing block — and the scroller is not
            positioned, so at 390px the spans for the days scrolled out of view sat at x≈500 and
            stretched the DOCUMENT to 501px. The measured result was 111px of horizontal page scroll
            on every route that renders a date strip. Making the scroller `position: relative`
            changes nothing visually and contains them; measured back to 0px of overflow.
          */}
          <DateStrip
            value={date}
            onChange={setDate}
            days={days}
            className="min-w-0 flex-1 [&_[role=group]]:relative"
          />
          {date !== localDateString(0) && (
            <button
              type="button"
              onClick={() => setDate(localDateString(0))}
              className="tap-target-row focus-ring flex-shrink-0 rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-xs font-medium text-secondary-200 transition-colors hover:bg-dark-700 hover:text-white"
              data-testid="matchday-jump-today"
            >
              Back to today
            </button>
          )}
        </div>
      )}

      {/* Competitions, always on screen. Sideways scroll inside this strip only: the page itself
          never scrolls horizontally, at any width. */}
      {competitions.length > 1 && (
        <div
          role="group"
          aria-label="Filter by competition"
          className="no-scrollbar mt-3 flex items-center gap-1.5 overflow-x-auto pb-1"
          data-testid="competition-chip-row"
        >
          {chipRow.map(competition => (
            <CompetitionChip
              key={competition.id}
              name={competition.name}
              logo={competition.logo}
              count={competition.count}
              size="sm"
              className="flex-shrink-0"
              selected={state.competitions.includes(competition.id)}
              onToggle={next => apply({
                ...state,
                competitions: toggleValue(state.competitions, competition.id, next),
              })}
            />
          ))}
          {hiddenChips > 0 && (
            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              className="tap-target-row focus-ring flex-shrink-0 rounded-full border border-dark-600 bg-dark-800 px-3 py-1 text-xs text-secondary-200 transition-colors hover:bg-dark-700 hover:text-white"
            >
              {hiddenChips} more
              <span className="sr-only"> competitions, in the filters</span>
            </button>
          )}
        </div>
      )}

      {/* The filters button, the active filters, and the resulting count — one row, always here. */}
      <FilterSummaryBar
        className="mt-2"
        activeFilters={activeFilters}
        onOpen={() => setSheetOpen(true)}
        onClearAll={filtered ? () => apply(clearedFilters(state)) : undefined}
        resultCount={day.status === 'ready' ? visible.length : null}
      />

      <DataSourceNotice meta={day.meta} className="mt-3" />
      <ForecastSyncNotice sync={day.meta?.forecastSync} className="mt-3" />

      <div id={listId} className="mt-3">
        {body()}
      </div>

      {footnote && (
        <p className="mt-4 max-w-3xl border-t border-dark-800 pt-3 text-xs leading-5 text-secondary-400">
          {footnote}
        </p>
      )}

      <FilterSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        activeFilters={activeFilters}
        onClearAll={filtered ? () => apply(clearedFilters(state)) : undefined}
        resultCount={day.status === 'ready' ? visible.length : null}
      >
        <MatchFilterControls state={state} onChange={apply} competitions={competitions} />
      </FilterSheet>
    </section>
  )
}

export default MatchdayWorkspace
