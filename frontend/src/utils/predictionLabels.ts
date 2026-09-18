import { MatchPredictions } from '@/types'

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
