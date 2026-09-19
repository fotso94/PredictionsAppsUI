import { MatchPredictions } from '@/types'
import { ForecastSyncStatus } from '@/services/match-data-source'
import { currentLocale, formatDateTime, t } from '@/i18n'

/**
 * Human label for a prediction provider name reported by the backend.
 *
 * The PRODUCT names — GameForecast, API-Football — are the same in every language; only the word
 * we add to them ("model") is translated. A provider this build has never heard of keeps its own
 * key and is named rather than hidden.
 */
export const providerLabel = (name?: string | null): string => {
  switch ((name || '').toLowerCase()) {
    case 'gameforecast': return t('provider.gameforecast')
    case 'api_football':
    case 'api-football': return t('provider.apiFootball')
    case 'sample': return t('provider.sample')
    case 'expert': return t('provider.expert')
    default: return name ? t('provider.namedModel', { name }) : t('provider.model')
  }
}

/** Short label describing where the shown prediction comes from. */
export const predictionSourceLabel = (prediction: MatchPredictions | null | undefined): string => {
  if (!prediction) return t('prediction.none')
  if (prediction.source === 'expert') return t('prediction.expert')
  if (prediction.source === 'default') return t('prediction.placeholder')
  return providerLabel(prediction.providerName || prediction.source_type)
}

/**
 * GameForecast publishes recommended bets as market keys ("matchResult.homeWinProbability",
 * "totalGoals.over2_5", "bothTeamsScore.no"). Turn them into readable labels; unknown keys pass through.
 */
export const betLabel = (raw: unknown): string => {
  const key = String(raw ?? '').trim()
  switch (key) {
    case 'matchResult.homeWinProbability': return t('bet.homeWin')
    case 'matchResult.drawProbability': return t('bet.draw')
    case 'matchResult.awayWinProbability': return t('bet.awayWin')
    case 'bothTeamsScore.yes': return t('bet.bttsYes')
    case 'bothTeamsScore.no': return t('bet.bttsNo')
    default: break
  }
  const totals = key.match(/^totalGoals\.(over|under)(\d)_(\d)$/)
  if (totals) {
    // The LINE is a number and goes through the reader's own decimal separator: 2.5 in English,
    // 2,5 in French. The provider publishes it as two digits in a key, not as a decimal string,
    // so there is nothing verbatim here to preserve.
    const line = formatNumberForLine(Number(`${totals[2]}.${totals[3]}`))
    return t(totals[1] === 'over' ? 'bet.overGoals' : 'bet.underGoals', { line })
  }
  return key.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[._]/g, ' ').toLowerCase()
}

/**
 * A goal line in the reader's convention: 2.5 in English, 2,5 in French.
 *
 * `currentLocale()`, not `undefined` — `undefined` means the DEVICE's locale, which is the thing
 * this whole package exists to stop standing in for the reader's choice.
 */
const formatNumberForLine = (value: number): string =>
  new Intl.NumberFormat(currentLocale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })
    .format(value)

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
  const provider = sync.provider ? providerLabel(sync.provider) : t('provider.none')
  // `{reason}` is the backend's own sentence and is never translated.
  if (sync.reason) return t('forecastSync.pausedWithReason', { provider, reason: sync.reason })
  return t('forecastSync.pausedDeferred', { provider, count: sync.deferred.length })
}

/**
 * How to describe when a forecast was produced, without passing off a fetch time as a model run.
 * Returns null when nothing datable is known.
 */
export const generationTimeLabel = (prediction: MatchPredictions | null | undefined): string | null => {
  if (!prediction) return null
  // Every branch checks the FORMATTED value, not the raw one: an unparseable timestamp must
  // produce no sentence rather than a sentence with a hole where the date should be.
  const modelRun = prediction.generationTimeKnown ? formatDateTime(prediction.modelRunAt) : null
  if (modelRun) return t('generation.modelRun', { when: modelRun })

  const fetched = formatDateTime(prediction.fetchedAt)
  // Explicitly NOT "generated": the provider never published a model-run time for this forecast.
  if (fetched) return t('generation.retrievedOnly', { when: fetched })

  const published = formatDateTime(prediction.publishedAt)
  return published ? t('generation.published', { when: published }) : null
}
