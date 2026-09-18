/**
 * The matchday workspace's state, and the URL that carries it.
 *
 * Everything the workspace shows — which day, which competitions, which markets, which sources,
 * whether finished fixtures are included — lives in the query string. That is deliberate:
 *
 *  - Going into a fixture and pressing Back restores the exact list the reader left, because the
 *    browser restored the URL. Nothing has to be remembered anywhere else.
 *  - A filtered day is a link. "Here is tonight's Bundesliga list" can be sent to somebody.
 *  - Changing the date rewrites only `date`, so a competition filter set five minutes ago is still
 *    set on the new day. Silently clearing it would answer a question the reader did not ask.
 *
 * WHAT IS NOT OFFERED, AND WHY. There is no confidence filter. The `ConfidenceLevel` attached to a
 * 1X2 block is a display bucket the mapper derives from how large the biggest probability is
 * (`levelFromProbability` in backend-match-data.service.ts) — it is not a confidence any source
 * published, and it is certainly not a measured accuracy, because nothing in this application has
 * ever been scored against a result. Filtering by it would present that derivation as a fact about
 * the forecast's quality. Market and source filters are kept because both are plain facts the
 * payload states: whether a source published a market at all, and whether a source exists for the
 * fixture at all.
 */

import type { BettingMarket, Match } from '@/types'
import { hasMarket } from '@/components/ui/predictionMarkets'
import { isMatchFinished, isMatchLive, isMatchScheduled } from '@/utils/matchFilters'

/** Which fixtures of the day are listed. */
export type FixtureStatusFilter = 'all' | 'upcoming' | 'finished'

/** A source the reader insists on having for a fixture. */
export type SourceFilter = 'model' | 'expert'

export interface WorkspaceState {
  /** YYYY-MM-DD in the viewer's local calendar. */
  date: string
  /** Competition ids. Empty means every competition. */
  competitions: string[]
  /** Markets that must ALL be published for the fixture to be listed. Empty means no constraint. */
  markets: BettingMarket[]
  /** Sources that must ALL be present. Empty means no constraint. */
  sources: SourceFilter[]
  status: FixtureStatusFilter
}

/** Query-string keys. Short, because they end up in links people paste. */
export const PARAM = {
  date: 'date',
  competitions: 'comp',
  markets: 'market',
  sources: 'source',
  status: 'show',
} as const

/**
 * Markets offered as a filter.
 *
 * `double-chance` and `handicap` are absent on purpose: `hasMarket` returns false for them for
 * every prediction this app can receive, so offering them would be a control that can only ever
 * empty the list.
 */
export const MARKET_OPTIONS: ReadonlyArray<{ value: BettingMarket; label: string }> = Object.freeze([
  { value: '1x2', label: 'Match result (1X2)' },
  { value: 'btts', label: 'Both teams to score' },
  { value: 'over-under', label: 'Over / under goals' },
  { value: 'correct-score', label: 'Correct score' },
])

export const SOURCE_OPTIONS: ReadonlyArray<{ value: SourceFilter; label: string }> = Object.freeze([
  { value: 'model', label: 'Has a model forecast' },
  { value: 'expert', label: 'Has an expert prediction' },
])

export const STATUS_OPTIONS: ReadonlyArray<{ value: FixtureStatusFilter; label: string }> = Object.freeze([
  { value: 'all', label: 'Everything on this date' },
  { value: 'upcoming', label: 'Upcoming and in play' },
  { value: 'finished', label: 'Played' },
])

const MARKET_VALUES = MARKET_OPTIONS.map(option => option.value)
const SOURCE_VALUES = SOURCE_OPTIONS.map(option => option.value)
const STATUS_VALUES = STATUS_OPTIONS.map(option => option.value)

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

/** A date the strip and the backend can both use. Anything else is ignored rather than guessed at. */
export function isWorkspaceDate(value: string | null | undefined): value is string {
  return typeof value === 'string'
    && DATE_PATTERN.test(value)
    && !Number.isNaN(new Date(`${value}T12:00:00`).getTime())
}

/** Comma-separated list from the URL, keeping only values this build understands, without repeats. */
function readList<T extends string>(params: URLSearchParams, key: string, allowed: readonly T[]): T[] {
  const raw = params.getAll(key).flatMap(value => value.split(','))
  const seen: T[] = []
  for (const entry of raw) {
    const trimmed = entry.trim()
    if (!trimmed) continue
    if ((allowed as readonly string[]).length > 0 && !(allowed as readonly string[]).includes(trimmed)) continue
    if (!seen.includes(trimmed as T)) seen.push(trimmed as T)
  }
  return seen
}

/** Competition ids are opaque: they come from the payload, so there is no allow-list to check. */
function readIds(params: URLSearchParams, key: string): string[] {
  const raw = params.getAll(key).flatMap(value => value.split(','))
  const seen: string[] = []
  for (const entry of raw) {
    const trimmed = entry.trim()
    if (trimmed && !seen.includes(trimmed)) seen.push(trimmed)
  }
  return seen
}

/**
 * The state the URL describes. `fallbackDate` is the route's own day (today on /predictions/today),
 * used only when the URL names no date — an unreadable `date` is treated the same way rather than
 * showing an empty list for a day that does not exist.
 */
export function readWorkspaceState(params: URLSearchParams, fallbackDate: string): WorkspaceState {
  const date = params.get(PARAM.date)
  const status = params.get(PARAM.status)
  return {
    date: isWorkspaceDate(date) ? date : fallbackDate,
    competitions: readIds(params, PARAM.competitions),
    markets: readList<BettingMarket>(params, PARAM.markets, MARKET_VALUES),
    sources: readList<SourceFilter>(params, PARAM.sources, SOURCE_VALUES),
    status: (STATUS_VALUES as readonly string[]).includes(status ?? '') ? (status as FixtureStatusFilter) : 'all',
  }
}

/**
 * `state` written back over `params`, preserving any key the workspace does not own.
 *
 * `omitDate` drops the date parameter, which is what a route whose path already names the day
 * (/predictions/today) wants when the selected date is that day: the tidy URL, not `?date=`.
 */
export function writeWorkspaceState(
  params: URLSearchParams,
  state: WorkspaceState,
  options: { omitDate?: boolean } = {},
): URLSearchParams {
  const next = new URLSearchParams(params)
  const set = (key: string, value: string) => { if (value) next.set(key, value); else next.delete(key) }

  if (options.omitDate) next.delete(PARAM.date)
  else set(PARAM.date, state.date)
  set(PARAM.competitions, state.competitions.join(','))
  set(PARAM.markets, state.markets.join(','))
  set(PARAM.sources, state.sources.join(','))
  set(PARAM.status, state.status === 'all' ? '' : state.status)
  return next
}

/** State with every filter lifted. The date is kept: clearing filters is not changing the day. */
export function clearedFilters(state: WorkspaceState): WorkspaceState {
  return { date: state.date, competitions: [], markets: [], sources: [], status: 'all' }
}

/** How many filters are narrowing the list right now. */
export function activeFilterCount(state: WorkspaceState): number {
  return state.competitions.length + state.markets.length + state.sources.length + (state.status === 'all' ? 0 : 1)
}

/** Add or remove one value from a list-valued filter. */
export function toggleValue<T extends string>(values: T[], value: T, next: boolean): T[] {
  if (next) return values.includes(value) ? values : [...values, value]
  return values.filter(entry => entry !== value)
}

/**
 * Does this fixture survive the current filters?
 *
 * A market counts as published when ANY source published it, because the reader asked for matches
 * where that market exists, not for matches where one particular source supplied it. Markets and
 * sources are conjunctions: ticking two means "both", which is the only reading under which the
 * count on the button matches what narrowing actually does.
 */
export function matchesWorkspaceFilters(match: Match, state: WorkspaceState): boolean {
  if (state.competitions.length > 0 && !state.competitions.includes(match.league.id)) return false

  if (state.status === 'upcoming' && !(isMatchLive(match) || isMatchScheduled(match))) return false
  if (state.status === 'finished' && !isMatchFinished(match)) return false

  // A market the source left out is ABSENT from the payload, never a 0% probability, so it can
  // never satisfy this test by accident.
  if (state.markets.length > 0 && !state.markets.every(market =>
    hasMarket(match.predictions, market)
    || hasMarket(match.providerForecast, market)
    || hasMarket(match.expertPrediction, market))) return false

  if (state.sources.includes('model') && !match.providerForecast) return false
  if (state.sources.includes('expert') && !match.expertPrediction) return false

  return true
}
