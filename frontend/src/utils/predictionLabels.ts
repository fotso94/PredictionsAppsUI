import { MatchPredictions } from '@/types'
import { ForecastSyncStatus } from '@/services/match-data-source'

/** Human label for a prediction provider name reported by the backend. */
export const providerLabel = (name?: string | null): string => {
  switch ((name || '').toLowerCase()) {
    case 'gameforecast': return 'GameForecast model'
    case 'api_football':
    case 'api-football': return 'API-Football model'
    case 'sample': return 'Sample data (not real)'
    case 'expert': return 'Expert'
    default: return name ? `${name} model` : 'Model'
  }
}

/** Short label describing where the shown prediction comes from. */
export const predictionSourceLabel = (prediction: MatchPredictions | null | undefined): string => {
  if (!prediction) return 'No prediction'
  if (prediction.source === 'expert') return 'Expert prediction'
  if (prediction.source === 'default') return 'Placeholder (demo)'
  return providerLabel(prediction.providerName || prediction.source_type)
}

/**
 * GameForecast publishes recommended bets as market keys ("matchResult.homeWinProbability",
 * "totalGoals.over2_5", "bothTeamsScore.no"). Turn them into readable labels; unknown keys pass through.
 */
export const betLabel = (raw: unknown): string => {
  const key = String(raw ?? '').trim()
  const exact: Record<string, string> = {
    'matchResult.homeWinProbability': 'Home win',
    'matchResult.drawProbability': 'Draw',
    'matchResult.awayWinProbability': 'Away win',
    'bothTeamsScore.yes': 'Both teams to score: Yes',
    'bothTeamsScore.no': 'Both teams to score: No',
  }
  if (exact[key]) return exact[key]
  const totals = key.match(/^totalGoals\.(over|under)(\d)_(\d)$/)
  if (totals) return `${totals[1] === 'over' ? 'Over' : 'Under'} ${totals[2]}.${totals[3]} goals`
  return key.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[._]/g, ' ').toLowerCase()
}

/** Ordered, de-duplicated labels from a provider's recommended_bets object or list. */
export const betLabels = (bets: Record<string, unknown> | unknown[] | null | undefined): string[] => {
  if (!bets) return []
  const values = Array.isArray(bets) ? bets : Object.keys(bets).sort().map(k => (bets as Record<string, unknown>)[k])
  return Array.from(new Set(values.map(betLabel).filter(Boolean)))
}

/**
 * Why the forecast refresh is not running, in the backend's own terms.
 *
 * A paused refresh is not the same as "no forecast exists": the reader needs to know the numbers
 * are simply not being updated right now. Returns null when the refresh ran normally.
 */
export const forecastSyncMessage = (sync: ForecastSyncStatus | null | undefined): string | null => {
  if (!sync || !sync.paused) return null
  const provider = sync.provider ? providerLabel(sync.provider) : 'The forecast provider'
  if (sync.reason) return `${provider} refresh is paused: ${sync.reason}`
  return `${provider} refresh is paused; ${sync.deferred.length} competition(s) wait for the next allowance reset`
}

/**
 * How to describe when a forecast was produced, without passing off a fetch time as a model run.
 * Returns null when nothing datable is known.
 */
export const generationTimeLabel = (prediction: MatchPredictions | null | undefined): string | null => {
  if (!prediction) return null
  if (prediction.generationTimeKnown && prediction.modelRunAt) {
    return `Model run ${new Date(prediction.modelRunAt).toLocaleString()}`
  }
  if (prediction.fetchedAt) {
    // Explicitly NOT "generated": the provider never published a model-run time for this forecast.
    return `Generation time not published; retrieved ${new Date(prediction.fetchedAt).toLocaleString()}`
  }
  return prediction.publishedAt ? `Published ${new Date(prediction.publishedAt).toLocaleString()}` : null
}
