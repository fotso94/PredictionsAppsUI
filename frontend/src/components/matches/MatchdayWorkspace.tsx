import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowPathIcon } from '@heroicons/react/24/outline'
import DateStrip, { DateStripDay } from '@/components/ui/DateStrip'
import CompetitionChip from '@/components/ui/CompetitionChip'
import FilterSheet, { ActiveFilter, FilterSummaryBar } from '@/components/ui/FilterSheet'
import EmptyState from '@/components/ui/EmptyState'
import DataSourceNotice from '@/components/ui/DataSourceNotice'
import DataFreshness from '@/components/ui/DataFreshness'
import ForecastSyncNotice from '@/components/ui/ForecastSyncNotice'
import { forecastAvailability } from '@/components/ui/forecastStatus'
import { footballDataService } from '@/services/football-data.service'
import { describeError } from '@/services/backend-match-data.service'
import { DataSourceMeta, ProviderStatus, STORED_ONLY, localDateString } from '@/services/match-data-source'
import type { Match } from '@/types'
import FixtureList from './FixtureList'
import MatchFilterControls from './MatchFilterControls'
import { competitionOptions, groupByCompetition } from './fixtureGrouping'
import {
  MARKET_OPTIONS, SOURCE_OPTIONS, STATUS_OPTIONS, WorkspaceState,
  activeFilterCount, clearedFilters, matchesWorkspaceFilters, optionLabel, readWorkspaceState,
  toggleValue, writeWorkspaceState,
} from './workspaceState'
import type { TranslateFn } from '@/i18n'
import { formatIsoDate, zoneLabel, zonedNoon } from '@/i18n'
import { useLocale } from '@/i18n/react'

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

/*
 * The day, spelled out. Was a module-level `Intl.DateTimeFormat(undefined, …)` — the DEVICE's
 * language, built once at import — and `new Date(`${date}T12:00:00`)`, which parses in the
 * DEVICE's zone. Both are now the reader's own, and both are resolved per render so a change of
 * either repaints the heading.
 */
function formatDay(date: string): string {
  return formatIsoDate(date)
}

function relativeDay(date: string, t: TranslateFn): string | null {
  if (date === localDateString(0)) return t('matchday.relative.today')
  if (date === localDateString(1)) return t('matchday.relative.tomorrow')
  if (date === localDateString(-1)) return t('matchday.relative.yesterday')
  return null
}

/**
 * Whether this fixture has KICKED OFF. Anything that disqualifies the strong "none of these has
 * been played" claim counts, so a score is enough on its own: `serialize_match` emits one as soon
 * as the stored match has a score, which for the live-score task is from the first goal, and a
 * fixture with a goal in it is not an unplayed fixture whatever its label says.
 */
const hasKickedOff = (match: Match): boolean =>
  match.status === 'finished' || match.status === 'live' || match.status === 'halftime'
  || match.result !== undefined

/**
 * Whether this fixture is OVER. Deliberately not the same test as above: a score is evidence that
 * a fixture has started, never that it has ended, and only the status says which. Saying "it has
 * finished" of a match that is 1-0 at 57 minutes would be a fact about the data inferred from
 * something that is not that fact — the same mistake as the constant this file exists to remove,
 * one step further in.
 */
const isFinished = (match: Match): boolean => match.status === 'finished'

/**
 * What is true about scoring, of the fixtures this page actually listed.
 *
 * WHY THIS IS COMPUTED AND NOT WRITTEN DOWN. The sentence that used to live at the end of
 * MatchesPage's footnote read "Nothing on this page has been scored against a result, so no
 * accuracy is claimed for any of it." It was a string constant, so it went on saying it after
 * settlement had scored four provider forecasts — the third time a fact about the data has been
 * found asserted as a constant in this codebase.
 *
 * Deleting it would have been the wrong repair. On a page of fixtures that have not kicked off
 * the statement is true and is worth making: a reader needs to know that none of the numbers
 * above is a score. So the page works out which of the two situations it is actually in.
 *
 * WHAT THIS CAN AND CANNOT SEE. It can see, per fixture, whether it has been played — that is in
 * the payload. It cannot see whether a prediction for a played fixture was then scored, because
 * the list payload carries no settlement state. So the moment a played fixture is on screen this
 * stops answering and names the surface that can answer: the match's own page, whose brief
 * reports the measured scoring position. Refusing to answer is not the same as answering "no",
 * and answering "no" is exactly what went wrong before.
 *
 * `null` while the day is loading or failed, and for an empty list: a page with no fixtures on it
 * has nothing to say about its fixtures.
 */
/*
 * THREE WHOLE SENTENCES IN THE CATALOGUE, NOT A SENTENCE ASSEMBLED HERE.
 *
 * What this function used to do is the exact defect C4 of this package names. It built the
 * sentence out of fragments in English order — a count, an English plural of "fixture", an
 * English subject-verb agreement, a participle — and every one of those decisions belongs to the
 * language rather than to this file. In French the determiner and the pronoun agree with a noun
 * that appears later ("Aucun des 12 matchs"), the participle agrees in number ("sont terminés"),
 * and 0 and 1 are both singular. None of that is reachable by translating "fixture" and keeping
 * the assembly.
 *
 * WHAT DID NOT CHANGE is the decision the sentence encodes: which of the three statements is
 * true, and the fact that "finished" is only used when every started fixture is actually over.
 * A live fixture still gets the weaker verb, because a 1-0 at 57 minutes has kicked off and has
 * not finished.
 */
function scoringNote(fixtures: Match[], ready: boolean, t: TranslateFn): string | null {
  if (!ready || fixtures.length === 0) return null
  const started = fixtures.filter(hasKickedOff).length
  const finished = fixtures.filter(isFinished).length
  const total = fixtures.length

  if (started === 0) return t('matchday.scoring.nonePlayed', { count: total })

  const verb = started === finished ? 'finished' : 'kickedOff'
  return started === total
    ? t('matchday.scoring.allPlayed', { count: total, verb })
    : t('matchday.scoring.somePlayed', { started, total, verb })
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
  const { t } = useLocale()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [sheetOpen, setSheetOpen] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const [day, setDay] = useState<DayData>({
    status: 'loading', date: defaultDate, matches: [], meta: null, error: null,
  })
  /**
   * The backend's provider and scheduler state.
   *
   * Every read on this page is `refresh=false`, so the list itself carries no clue about how old
   * it is. This is where that comes from: the scheduler records when each kind of data last
   * refreshed, so "last updated" is a reported fact rather than a guess about who last browsed.
   *
   * `null` is kept distinct from "not loaded yet" by `statusLoaded`: a failed status request must
   * read as "we cannot say how current this is", never as "it is current".
   */
  const [status, setStatus] = useState<ProviderStatus | null>(null)
  const [statusLoaded, setStatusLoaded] = useState(false)

  const state = useMemo(
    () => readWorkspaceState(searchParams, defaultDate),
    [searchParams, defaultDate],
  )
  const { date } = state
  /**
   * Today, in the reader's chosen zone, recomputed on every render.
   *
   * Everything on this page that means "today" reads this one value, so the heading, the strip,
   * the jump button and the empty state's suggestion can never disagree — and because it changes
   * when the zone changes, the memos that depend on it rebuild without needing the zone itself
   * as a dependency they do not read.
   */
  const todayIso = localDateString(0)

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
        // retry, never the "nothing stored for this date" state below — that state reports what
        // the store holds, and a network error tells us nothing about what the store holds.
        setDay({ status: 'error', date, matches: [], meta: null, error: describeError(error) })
      })

    return () => { cancelled = true }
  }, [date, reloadToken])

  // Reloaded with the list, so pressing Retry also re-asks how current the data is. The status
  // endpoint reads Redis and the database only: it makes no provider request.
  useEffect(() => {
    let cancelled = false
    footballDataService.getProviderStatus()
      .then(result => { if (!cancelled) setStatus(result) })
      .finally(() => { if (!cancelled) setStatusLoaded(true) })
    return () => { cancelled = true }
  }, [reloadToken])

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
  // the branches below are careful never to report that emptiness as "nothing stored for this
  // date": only an answered request knows what is stored.
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
  // Computed from `shown` — the fixtures actually rendered, after filters and any cap — because
  // the sentence is about what is on this page, not about what the day holds.
  const scoring = useMemo(
    () => scoringNote(shown, day.status === 'ready', t),
    [shown, day.status, t],
  )

  const days = useMemo<DateStripDay[]>(() => {
    // The strip normally runs from yesterday; when the reader has jumped to a date outside that
    // window it runs from the day before the one they chose, so the selection is always on it.
    const first = localDateString(-1)
    const last = localDateString(7)
    /*
     * Midday in the CHOSEN zone, not `new Date(`${date}T12:00:00`)`, which parses in the DEVICE's
     * — so with a chosen zone far from the device's, noon on the 25th became a moment on the 24th
     * and the strip was a day out. Anchoring on `todayIso` rather than on `new Date()` also gives
     * this memo an honest dependency on the zone: "today" moves when the zone changes, `todayIso`
     * changes with it, and the strip is rebuilt.
     */
    const anchorForDate = zonedNoon(date)
    const anchor = (date >= first && date <= last) || Number.isNaN(anchorForDate.getTime())
      ? zonedNoon(todayIso)
      : anchorForDate
    return Array.from({ length: 9 }, (_, index) => {
      const entry = localDateString(index - 1, anchor)
      return {
        date: entry,
        // Only the day we actually loaded has a count. Passing 0 for the others would claim they
        // are empty when nobody has looked at them.
        count: entry === day.date && day.status === 'ready' ? day.matches.length : undefined,
      }
    })
  }, [date, todayIso, day.date, day.status, day.matches.length])

  const activeFilters = useMemo<ActiveFilter[]>(() => {
    const chips: ActiveFilter[] = []
    for (const id of state.competitions) {
      const known = competitions.find(option => option.id === id)
      chips.push({
        id: `comp:${id}`,
        group: t('filters.group.competition'),
        // A competition filtered on a day that has no such fixtures still names itself, from the
        // URL, rather than turning into an anonymous chip the reader cannot identify. The name
        // itself is the provider's and is never translated.
        label: known?.name ?? t('filters.selectedCompetition'),
        onRemove: () => apply({ ...state, competitions: toggleValue(state.competitions, id, false) }),
      })
    }
    for (const market of state.markets) {
      chips.push({
        id: `market:${market}`,
        group: t('filters.group.market'),
        label: (() => {
          const option = MARKET_OPTIONS.find(entry => entry.value === market)
          return option ? optionLabel(option) : market
        })(),
        onRemove: () => apply({ ...state, markets: toggleValue(state.markets, market, false) }),
      })
    }
    for (const source of state.sources) {
      chips.push({
        id: `source:${source}`,
        group: t('filters.group.source'),
        label: (() => {
          const option = SOURCE_OPTIONS.find(entry => entry.value === source)
          return option ? optionLabel(option) : source
        })(),
        onRemove: () => apply({ ...state, sources: toggleValue(state.sources, source, false) }),
      })
    }
    if (state.status !== 'all') {
      chips.push({
        id: `status:${state.status}`,
        group: t('filters.group.showing'),
        label: (() => {
          const option = STATUS_OPTIONS.find(entry => entry.value === state.status)
          return option ? optionLabel(option) : state.status
        })(),
        onRemove: () => apply({ ...state, status: 'all' }),
      })
    }
    return chips
  }, [apply, competitions, state, t])

  const filtered = activeFilterCount(state) > 0
  const relative = relativeDay(date, t)
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
          <p className="text-sm text-secondary-400" role="status">{t('matchday.loading')}</p>
        </div>
      )
    }

    if (day.status === 'error') {
      return (
        <EmptyState
          tone="failed"
          title={t('matchday.errorTitle')}
          description={
            <>
              {/* The service's own message, verbatim. Only the clause under it is ours. */}
              <span className="block">{day.error}</span>
              <span className="mt-1 block text-xs text-secondary-400">{t('matchday.errorNote')}</span>
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
              {t('matchday.retry')}
            </button>
          }
          data-testid="matchday-error"
        />
      )
    }

    if (dayMatches.length === 0) {
      /*
        WHAT THIS STATE ACTUALLY KNOWS. The request succeeded and came back with no rows. That is a
        fact about this installation's store, not about football: every read here is `refresh=false`
        (see the header note), so a day nobody has fetched yet and a day with genuinely no fixture
        are indistinguishable from in here. The old title, "No matches on this date.", asserted the
        second. This says the first, and leaves the reader somewhere to go rather than a dead end —
        "Pick another day above" was also wrong on the home panel, which has no date strip above it.
      */
      const jumpTo = date === todayIso ? localDateString(1) : todayIso
      const jumpLabel = t(date === todayIso ? 'matchday.showTomorrow' : 'matchday.showToday')
      return (
        <EmptyState
          tone="empty"
          title={t('matchday.emptyTitle')}
          description={t('matchday.emptyDescription', { date: formatDay(date) })}
          action={variant === 'page' ? (
            <button
              type="button"
              onClick={() => setDate(jumpTo)}
              className="tap-target-row focus-ring rounded-lg border border-dark-600 bg-dark-800 px-4 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
              data-testid="matchday-empty-jump"
            >
              {jumpLabel}
            </button>
          ) : (
            /* The panel has no date strip of its own: send the reader where the days are. */
            <Link
              to={{ pathname: WORKSPACE_PATH, search: searchParams.toString() }}
              className="tap-target-row focus-ring inline-flex items-center rounded-lg border border-dark-600 bg-dark-800 px-4 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
              data-testid="matchday-empty-jump"
            >
              {t('matchday.pickAnotherDate')}
            </Link>
          )}
          data-testid="matchday-empty"
        />
      )
    }

    if (visible.length === 0) {
      return (
        <EmptyState
          tone="empty"
          title={t('matchday.filteredEmptyTitle')}
          description={t('matchday.filteredEmptyDescription', {
            count: dayMatches.length,
            date: formatDay(date),
          })}
          action={
            <button
              type="button"
              onClick={() => apply(clearedFilters(state))}
              className="tap-target-row focus-ring rounded-lg border border-dark-600 bg-dark-800 px-4 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
            >
              {t('matchday.clearAllFilters')}
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
                ? t('matchday.seeAll', { count: visible.length })
                : t('matchday.openWorkspace')}
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
        <div className="text-right">
          <p className="text-sm text-secondary-400">
            {relative ? t('matchday.dateLine', { relative, date: formatDay(date) }) : formatDay(date)}
          </p>
          {/*
            WHICH CLOCK THESE TIMES ARE ON, said out loud.
            A kick-off time is plausible at any hour, so a reader whose zone is wrong has no way
            to notice from the list itself. The zone is named once, beside the date it also
            decides — "today" is a day in this zone — rather than repeated on every row.
          */}
          <p className="text-xs text-secondary-500" data-testid="matchday-zone">
            {t('matchday.timesIn', { zone: zoneLabel() })}
          </p>
        </div>
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
          {date !== todayIso && (
            <button
              type="button"
              onClick={() => setDate(todayIso)}
              className="tap-target-row focus-ring flex-shrink-0 rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-xs font-medium text-secondary-200 transition-colors hover:bg-dark-700 hover:text-white"
              data-testid="matchday-jump-today"
            >
              {t('matchday.backToToday')}
            </button>
          )}
        </div>
      )}

      {/*
        Competitions, always on screen. Sideways scroll inside this strip only: the page itself
        never scrolls horizontally, at any width.

        WHILE THE DAY IS LOADING THIS SAYS SO, rather than not existing.

        The options are derived from the fixtures, so before they arrive there are none and this
        whole strip used to be absent from the document. An independent reviewer opened the
        filters during a load, waited ten seconds for a competition that could not yet exist, and
        recorded it as an unexplained failure — which is fair, because nothing on screen said the
        filters were still coming. An absent control and a control with nothing in it read the
        same to a reader and to a test, and neither is the truth here.

        A day that has finished loading with one competition still shows no strip: there is
        nothing to filter between, and offering the choice would be noise.
      */}
      {day.status === 'loading' && (
        <div
          className="mt-3 flex items-center gap-1.5 pb-1 text-xs text-secondary-400"
          data-testid="competition-chip-row-loading"
          role="status"
        >
          {t('matchday.loadingCompetitions')}
        </div>
      )}

      {day.status !== 'loading' && competitions.length > 1 && (
        <div
          role="group"
          aria-label={t('matchday.filterByCompetition')}
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
              {t('matchday.moreCompetitions', { count: hiddenChips })}
              <span className="sr-only">{t('matchday.moreCompetitionsSr')}</span>
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

      {/*
        How current this list is. It sits above the fixtures rather than under them because it
        changes how every row below should be read: none of this is live, and on a day when the
        scheduler is paused or has never run, that is the first thing worth knowing.

        Held back until the status request has settled: a panel that said "cannot be stated" for
        half a second on every load would be noise, and one that guessed would be worse.
      */}
      {statusLoaded && <DataFreshness status={status} className="mt-3" />}

      <DataSourceNotice meta={day.meta} className="mt-3" />
      <ForecastSyncNotice
        sync={day.meta?.forecastSync}
        /* "Paused" on its own is not actionable; the scheduler knows when it comes back. */
        resume={forecastAvailability(status)?.resume ?? null}
        className="mt-3"
      />

      <div id={listId} className="mt-3">
        {body()}
      </div>

      {footnote && (
        <p
          className="mt-4 max-w-3xl border-t border-dark-800 pt-3 text-xs leading-5 text-secondary-400"
          data-testid="matchday-footnote"
        >
          {footnote}
          {/* Measured from the fixtures above on every render, never written down. */}
          {scoring && ` ${scoring}`}
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
