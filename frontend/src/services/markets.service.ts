/**
 * Markets, suggestions and the capability matrix: three stored-data reads.
 *
 * None of these can cost a provider request — the backend builds them from forecasts already on
 * disk — so nothing here is rationed or cached beyond de-duplicating one page render.
 */

import apiClient from './api-client'
import type { ApiCapabilities, ApiMarketEnvelope, ApiSuggestions, SuggestionQuery } from '@/types/markets'

const API = '/api/v1'
const ENVELOPE_TTL_MS = 30 * 1000

const envelopes = new Map<string, { at: number; value: ApiMarketEnvelope }>()

/**
 * Coerce whatever came back into an envelope the panel can render.
 *
 * A backend from before the endpoint existed answers 404 (an error, handled by the caller); a
 * proxy or a stub can answer 200 with something else entirely. Neither may take the match page
 * down: anything without a `groups` array is read as "no stored forecast", and the optional lists
 * are made present so nothing downstream has to check them.
 */
export function normalizeEnvelope(matchId: string, data: unknown): ApiMarketEnvelope {
  const raw = (data && typeof data === 'object' ? data : {}) as Partial<ApiMarketEnvelope>
  if (!Array.isArray(raw.groups)) {
    return {
      match_id: matchId, provider: null, normalisation_version: String(raw.normalisation_version ?? 'unknown'),
      built_at: String(raw.built_at ?? ''), forecast: {
        record_id: null, snapshot_id: null, captured_before_kickoff: null, retrieved_at: null, model_run_at: null,
        provider_updated_at: null, state: 'unavailable', state_reason: 'the markets payload could not be read',
      },
      groups: [], recommended_bets: [], provider_odds: null, anomalies: [], reason: 'the markets payload could not be read',
    }
  }
  return {
    ...(raw as ApiMarketEnvelope),
    groups: raw.groups.map(group => ({ ...group, markets: Array.isArray(group.markets) ? group.markets.map(market => ({
      ...market, warnings: Array.isArray(market.warnings) ? market.warnings : [],
      selections: Array.isArray(market.selections) ? market.selections.map(s => ({ ...s, warnings: Array.isArray(s.warnings) ? s.warnings : [] })) : [],
    })) : [] })),
    recommended_bets: Array.isArray(raw.recommended_bets) ? raw.recommended_bets : [],
    anomalies: Array.isArray(raw.anomalies) ? raw.anomalies : [],
    forecast: raw.forecast ?? { record_id: null, snapshot_id: null, captured_before_kickoff: null, retrieved_at: null, model_run_at: null, provider_updated_at: null, state: null, state_reason: null },
  }
}

export async function getMatchMarkets(matchId: string, options: { fresh?: boolean } = {}): Promise<ApiMarketEnvelope> {
  const cached = envelopes.get(matchId)
  if (!options.fresh && cached && Date.now() - cached.at < ENVELOPE_TTL_MS) return cached.value
  const { data } = await apiClient.get<unknown>(`${API}/matches/${encodeURIComponent(matchId)}/markets`)
  const envelope = normalizeEnvelope(matchId, data)
  envelopes.set(matchId, { at: Date.now(), value: envelope })
  return envelope
}

export function suggestionParams(query: SuggestionQuery): Record<string, string> {
  const params: Record<string, string> = {}
  if (query.legs) params.legs = String(query.legs)
  if (query.min_probability !== undefined) params.min_probability = String(query.min_probability)
  if (query.max_probability !== undefined) params.max_probability = String(query.max_probability)
  if (query.markets && query.markets.length) params.markets = query.markets.join(',')
  if (query.competitions && query.competitions.length) params.competitions = query.competitions.join(',')
  if (query.from) params.from = query.from
  if (query.to) params.to = query.to
  if (query.odds_min !== undefined) params.odds_min = String(query.odds_min)
  if (query.odds_max !== undefined) params.odds_max = String(query.odds_max)
  if (query.max_combinations) params.max_combinations = String(query.max_combinations)
  if (query.include_stale) params.include_stale = 'true'
  return params
}

export async function getSuggestions(query: SuggestionQuery): Promise<ApiSuggestions> {
  const { data } = await apiClient.get<ApiSuggestions>(`${API}/suggestions`, { params: suggestionParams(query) })
  return data
}

export async function getCapabilities(): Promise<ApiCapabilities> {
  const { data } = await apiClient.get<Partial<ApiCapabilities>>(`${API}/suggestions/capabilities`)
  return { normalisation_version: String(data?.normalisation_version ?? 'unknown'), families: Array.isArray(data?.families) ? data.families : [] }
}

/** Test seam: forget de-duplicated envelopes. */
export function resetMarketsCache(): void {
  envelopes.clear()
}
