/**
 * Which markets a prediction actually offers, and at what confidence.
 *
 * Used by the list filters. A market the source did not publish is ABSENT — it is never counted as
 * a 0% probability, and it never satisfies a "show me matches with this market" filter.
 *
 * NOTE: presentation-layer glue that would sit better in src/utils, which this package does not
 * own; see the needs_other_owner note in the package report.
 */

import { BettingMarket, ConfidenceLevel, MatchPredictions } from '@/types'
import { isPublished } from './probability'

/** True when the source published a usable 1X2 block (and did not flag the market as absent). */
export function hasMatchResult(prediction: MatchPredictions | null | undefined): boolean {
  return Boolean(prediction?.outcome) && prediction?.markets?.matchResult !== false
}

/** True when at least one half of the both-teams-to-score market was published. */
export function hasBtts(prediction: MatchPredictions | null | undefined): boolean {
  const btts = prediction?.bothTeamsToScore
  return Boolean(btts) && (isPublished(btts?.yes) || isPublished(btts?.no))
}

/** True when at least one over/under line was published. */
export function hasTotalGoals(prediction: MatchPredictions | null | undefined): boolean {
  const totals = prediction?.totalGoals
  if (!totals) return false
  return isPublished(totals.over25) || isPublished(totals.under25)
    || isPublished(totals.over35) || isPublished(totals.under35)
}

/** True when a usable exact-score market was published. */
export function hasCorrectScore(prediction: MatchPredictions | null | undefined): boolean {
  return Boolean(prediction?.correctScore)
}

/** Does this prediction offer the given betting market? Absent market => false, never 0%. */
export function hasMarket(prediction: MatchPredictions | null | undefined, market: BettingMarket): boolean {
  switch (market) {
    case '1x2': return hasMatchResult(prediction)
    case 'btts': return hasBtts(prediction)
    case 'over-under': return hasTotalGoals(prediction)
    case 'correct-score': return hasCorrectScore(prediction)
    // Markets this app never receives from any configured source.
    case 'double-chance':
    case 'handicap':
    default:
      return false
  }
}

/** Confidence levels attached to the markets this prediction actually published. */
export function confidenceLevels(prediction: MatchPredictions | null | undefined): ConfidenceLevel[] {
  if (!prediction) return []
  const levels: ConfidenceLevel[] = []
  if (hasMatchResult(prediction) && prediction.outcome) levels.push(prediction.outcome.confidence)
  if (hasBtts(prediction) && prediction.bothTeamsToScore) levels.push(prediction.bothTeamsToScore.confidence)
  if (hasTotalGoals(prediction) && prediction.totalGoals) levels.push(prediction.totalGoals.confidence)
  if (hasCorrectScore(prediction) && prediction.correctScore) levels.push(prediction.correctScore.confidence)
  return levels
}

/** True when any published market carries one of `wanted`. */
export function hasAnyConfidence(
  prediction: MatchPredictions | null | undefined,
  wanted: ConfidenceLevel[],
): boolean {
  return confidenceLevels(prediction).some(level => wanted.includes(level))
}

/** True when any published market is rated high or very high. */
export function isHighConfidence(prediction: MatchPredictions | null | undefined): boolean {
  return hasAnyConfidence(prediction, ['high', 'very-high'])
}
