/**
 * Reading the match brief for the match page.
 *
 * Selection and wording only. Nothing here produces a probability, completes a market, or turns an
 * absent number into a present one: every sentence shown to the reader is either the backend's own
 * (`detail`, `summary`, `state_reason`) or a fixed statement about the state of the data.
 *
 * NOTE: this file exports no component on purpose. React Fast Refresh (and the lint rule that
 * guards it) wants a .tsx file to export components only, so the plain helpers live here.
 */

import type {
  BriefFreshness, BriefMarketKey, BriefMissingEntry, BriefMissingReason, BriefSourceBlock,
  BriefSourceKey, ForecastState, MatchPredictions,
} from '@/types'
import type { FreshnessTone } from '@/utils/brief'
import { marketLabel, missingReasonLabel, refreshBlockedNote } from '@/utils/brief'
import type { ForecastAvailability } from '@/components/ui/forecastStatus'

/**
 * Every gap the brief reported about one source for one reason.
 *
 * Grouped by `source + reason` and NEVER by source alone: the whole purpose of the reason codes is
 * that "we have never retrieved a forecast", "the forecast we hold omits this market", "what we
 * hold is out of date" and "nobody has asked the provider recently" are four different statements.
 * Collapsing them into one "unavailable" row would throw away the only thing that tells a reader
 * whether the market is unknowable or merely unrefreshed.
 */
export interface MissingGroup {
  /** `source:reason`, stable across renders. */
  key: string
  source: BriefSourceKey
  reason: BriefMissingReason
  /** Short label for the chip. */
  label: string
  /** The backend's own sentence, shown verbatim. */
  detail: string
  /** True when the brief said this about the source as a whole, not about one market. */
  wholeSource: boolean
  /** Market keys this reason was reported for, in brief order. */
  markets: BriefMarketKey[]
}

/** The markets of a group as display names, using the brief's own market vocabulary. */
export function groupMarketNames(group: MissingGroup): string[] {
  return group.markets.map(marketLabel)
}

/**
 * Group the brief's `missing` array by source and reason, source-scoped statements first.
 *
 * A source-scoped entry ("no forecast was ever retrieved for this fixture") is a fact about the
 * whole fixture and leads; the market-scoped entries that follow say which markets it cost us.
 */
export function groupMissing(missing: BriefMissingEntry[] | null | undefined): MissingGroup[] {
  if (!missing || missing.length === 0) return []
  const groups = new Map<string, MissingGroup>()
  const order: string[] = []

  for (const entry of missing) {
    const key = `${entry.source}:${entry.reason}`
    let group = groups.get(key)
    if (!group) {
      group = {
        key,
        source: entry.source,
        reason: entry.reason,
        label: missingReasonLabel(entry.reason) ?? 'Not published',
        detail: entry.detail,
        wholeSource: false,
        markets: [],
      }
      groups.set(key, group)
      order.push(key)
    }
    if (entry.scope === 'source') {
      group.wholeSource = true
    } else if (entry.market && !group.markets.includes(entry.market)) {
      group.markets.push(entry.market)
    }
  }

  const grouped = order.map(key => groups.get(key) as MissingGroup)
  // A stable sort: source-scoped statements first, otherwise the brief's own order is kept.
  return [...grouped].sort((a, b) => Number(b.wholeSource) - Number(a.wholeSource))
}

/**
 * The state of the data behind this page, as ONE statement.
 *
 * A site-wide provider banner, a per-match notice and the operational quota wording used to stack
 * up on this screen and make a perfectly good forecast look broken. This composes the single
 * statement the reader needs, and hands the operational lines to a disclosure instead of printing
 * them beside it.
 *
 * A paused refresh never becomes the statement: "nobody has asked the provider recently" says
 * nothing about whether the numbers on screen are right, so it stays its own clause.
 */
export interface DataState {
  /** The one sentence: what the reader should take from the state of the forecast. */
  statement: string
  tone: FreshnessTone
  /**
   * That a refresh is not running — its own clause, never folded into `statement`, because
   * "nobody has asked the provider recently" says nothing about whether what is on screen is right.
   *
   * The caller shows EITHER this or the brief's own provenance line, never both: two sentences for
   * one fact is how a working forecast ends up looking broken.
   */
  pausedClause: string | null
  /** Operational lines for the disclosure, in the backend's own words. De-duplicated. */
  detail: string[]
}

const STATE_STATEMENT: Record<ForecastState, { statement: string; tone: FreshnessTone }> = {
  available: {
    statement: 'The model forecast below is the one currently held for this fixture.',
    tone: 'ok',
  },
  stale: {
    statement: 'The model forecast below is older than the freshness limit. It is shown as it was published, not as a current view.',
    tone: 'problem',
  },
  kickoff_passed: {
    statement: 'Kick-off has passed. The model forecast below is kept as it was published, for reference.',
    tone: 'ageing',
  },
  unavailable: {
    statement: 'No model forecast has been retrieved for this fixture.',
    tone: 'problem',
  },
}

/** A forecast is on the page, but nothing says how current it is. Not a fault; simply unknown. */
const HELD_WITHOUT_STATE: { statement: string; tone: FreshnessTone } = {
  statement: 'A model forecast is held for this fixture. How current it is has not been reported.',
  tone: 'unknown',
}

export function describeDataState(
  freshness: BriefFreshness | null | undefined,
  forecast: MatchPredictions | null | undefined,
  availability: ForecastAvailability | null,
): DataState {
  const held = Boolean(forecast)
  const reported: ForecastState | undefined = freshness?.state ?? forecast?.state
  const state: ForecastState = reported ?? (held ? 'available' : 'unavailable')
  // "No forecast has been retrieved" is only ever said when none is on the page. A forecast that is
  // shown while its reported state says otherwise gets the honest statement instead of a contradiction.
  const base = held && state === 'unavailable'
    ? HELD_WITHOUT_STATE
    : STATE_STATEMENT[state] ?? STATE_STATEMENT.unavailable

  // The brief's own reason wins; the provider-status message is the fallback for a payload that
  // carries no brief. Either way this stays a separate clause from the state statement above.
  const blockedReason = refreshBlockedNote(freshness)
  const paused = blockedReason
    ? `Refresh paused — ${blockedReason}`
    : availability?.paused
      ? availability.message
      : null

  const detail: string[] = []
  const add = (line: string | null | undefined) => {
    const text = (line ?? '').trim()
    if (text && !detail.includes(text)) detail.push(text)
  }
  add(freshness?.state_reason)
  add(forecast?.stateReason)
  // The operational quota wording: true, useful to an operator, and noise beside a sound forecast.
  add(availability?.message)
  if (freshness?.max_age_hours) {
    add(`A forecast is treated as out of date once it is more than ${freshness.max_age_hours} hours old.`)
  }

  return { statement: base.statement, tone: base.tone, pausedClause: paused, detail }
}

/**
 * How a confidence badge beside a probability should be read.
 *
 * `published` means the source itself stated a confidence. `derived` means it did not, and the band
 * is only the strength of the probability — never evidence that this source has been right before.
 * Falls back to the mapped prediction when no brief is carried, and an expert who published no
 * confidence score is NOT credited with one.
 */
export function confidenceBasis(
  block: BriefSourceBlock | null | undefined,
  prediction: MatchPredictions,
): 'published' | 'derived' {
  if (block) return block.confidence_published ? 'published' : 'derived'
  const score = prediction.confidence_score
  const published = prediction.source === 'expert' && typeof score === 'number' && Number.isFinite(score)
  return published ? 'published' : 'derived'
}

/**
 * One sentence on whether this source published a confidence at all.
 *
 * The brief's own wording wins. The fallbacks state the same fact for a payload that carries no
 * brief, and neither ever implies a measured accuracy: nothing here has been scored against a
 * result.
 */
export function confidenceStatement(
  detailFromBrief: string | null | undefined,
  source: BriefSourceKey,
  prediction: MatchPredictions | null,
): string {
  const fromBrief = (detailFromBrief ?? '').trim()
  if (fromBrief) return fromBrief
  if (source === 'expert') {
    const score = prediction?.confidence_score
    return typeof score === 'number' && Number.isFinite(score)
      ? 'The expert published a confidence value with this prediction.'
      : 'This expert published no confidence value with this prediction.'
  }
  return 'This provider publishes no confidence value with its forecasts.'
}

/** The site-wide statement about accuracy. Nothing has been scored against a result yet. */
export const ACCURACY_STATEMENT =
  'No prediction on this site has been scored against a match result yet, so no accuracy has ever '
  + 'been measured for either source. A probability is what a source expects; it is not a record of '
  + 'how often that source has been right.'
