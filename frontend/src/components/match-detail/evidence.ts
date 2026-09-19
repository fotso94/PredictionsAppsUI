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
 * The state of the data behind this page, as ONE statement — about THIS FIXTURE and nothing else.
 *
 * A site-wide provider banner, a per-match notice and the operational quota wording used to stack
 * up on this screen and make a perfectly good forecast look broken. This composes the single
 * statement the reader needs, and hands the operational lines to a disclosure instead of printing
 * them beside it.
 *
 * THE SCOPE RULE, which is what keeps the page down to one notice. Site-wide operational state —
 * the provider's spent allowance, its cooldown, when refreshing resumes — is NOT repeated here.
 * It is stated once per page by DataFreshness, beside the ages it explains. What belongs here is
 * only what is true of this fixture: the state of the forecast we hold for it, and the brief's own
 * reason for a gap in it. `availability` therefore contributes exactly one thing — a fallback
 * "refresh paused" clause for a payload whose brief carried no reason of its own — and never its
 * wording, its counters or its resume time.
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
   * It is now shown ALONGSIDE the brief's provenance line rather than instead of it: they are two
   * different facts (how old this forecast is, and whether anything is fetching a newer one) and
   * neither answers the other. What must not be doubled is the WORDING — the provider's own reason
   * is printed here once and nowhere else on the page, which is why the caller strips it out of
   * what it hands ProvenanceLine.
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
  /*
   * THE PAUSE, STATED WITHOUT THE PROVIDER'S PROSE.
   *
   * `refresh_blocked_reason` is the provider's own sentence, and on this installation it is a
   * hundred-and-eighty-character HTTP 429 ending in a vendor upgrade URL — the identical text the
   * freshness block prints a few hundred pixels above. Printing it twice on one screen is how a
   * forecast that is perfectly sound starts to look broken.
   *
   * So the clause here says the bare fact, which is all this fixture's reader needs to read the
   * numbers below correctly, and the provider's verbatim reason goes into `detail`, behind the
   * disclosure. Nothing is dropped: the sentence is still on the page, one tap away, and the
   * freshness block still carries it in full outside any disclosure.
   */
  /*
   * And the clause only claims what is actually on the page. Nine of the fixtures this
   * installation holds carry no model forecast at all, and on those "what is below is the last
   * forecast retrieved" asserts a forecast that does not exist — a sentence the reader can see is
   * false by looking down the page. `held` already tells us which case we are in, so each case
   * gets the sentence that is true of it.
   */
  const blockedReason = refreshBlockedNote(freshness)
  const paused = blockedReason || availability?.paused
    ? held
      ? 'Refresh paused: what is below is the last forecast retrieved, unchanged.'
      : 'Refresh paused: no new forecast can be retrieved for this fixture until it resumes.'
    : null

  const detail: string[] = []
  const add = (line: string | null | undefined) => {
    const text = (line ?? '').trim()
    if (text && !detail.includes(text)) detail.push(text)
  }
  add(freshness?.state_reason)
  add(forecast?.stateReason)
  // The provider's own words for the pause, verbatim and unedited — just not in the reader's way.
  add(blockedReason)
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

/**
 * The site-wide statement about accuracy, used when the brief carries no wording of its own.
 *
 * It used to read "no prediction on this site has been scored against a match result yet". That
 * was true when nothing could be scored at all, and it is the kind of sentence that goes false
 * silently: settlement exists now, so the first time it runs the page would be making a claim
 * nobody re-checked. What is permanently true is the distinction this sentence exists to draw —
 * a probability about one fixture is not a record of how often a source has been right — so that
 * is what it says, and it points at where the record actually lives.
 */
export const ACCURACY_STATEMENT =
  'A probability is what a source expects of this one fixture. It is not a measure of how often '
  + 'that source has been right: that is counted separately from settled results, and is only ever '
  + 'published with the sample it was counted from.'
