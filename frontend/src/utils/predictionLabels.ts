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
