/**
 * The market contract and the selection slips, as the backend serves them.
 *
 * These are the API shapes verbatim (snake_case), not mapped into camelCase like `Match`: every
 * value here is already a reader-safe fact the backend reviewed — a probability with its source, a
 * price with its source and date, a settlement rule in words — and re-keying them would add a second
 * place for the meaning to drift. `ApiMatch` in backend-match-data.service.ts is kept the same way.
 *
 * Contract: backend/app/services/markets.py (markets.v1), slips.py, suggestions.py.
 */

export type MarketId =
  | 'match_result' | 'double_chance' | 'draw_no_bet' | 'total_goals' | 'home_team_goals' | 'away_team_goals'
  | 'both_teams_score' | 'first_half_result' | 'team_to_score_first' | 'exact_score'

export type MarketGroupId = 'outcome' | 'goals' | 'first_half' | 'team' | 'exact_score'

export type MarketPeriod = 'regulation' | 'first_half'

export interface MarketWarning {
  severity: 'warning' | 'note'
  code: string
  /** The backend's own sentence, rendered verbatim. */
  message: string
}

export interface SelectionOdds {
  value: number
  format: 'decimal'
  source: 'provider_snapshot' | 'user'
  provider?: string | null
  captured_at: string | null
}

export interface SettlementCapability {
  capable: boolean
  basis: 'regulation_time' | 'half_time' | 'event_order' | 'fixture' | 'none' | string
  rule: string
  reason?: string | null
}

export interface SelectionCalculation {
  formula: string
  inputs: Record<string, number>
  source_market: MarketId
  note: string
}

export interface ApiMarketSelection {
  selection_id: string
  market_id: MarketId
  outcome: string
  line: number | null
  period: MarketPeriod
  /** 0-1, or null when the provider published nothing for it. Never 0 for "absent". */
  probability: number | null
  probability_source: 'provider' | 'calculated'
  calculation: SelectionCalculation | null
  available: boolean
  unavailable_reason: string | null
  warnings: MarketWarning[]
  settlement: SettlementCapability
  odds: SelectionOdds | null
}

export interface ApiMarket {
  market_id: MarketId
  group: MarketGroupId
  period: MarketPeriod
  line: number | null
  available: boolean
  unavailable_reason: string | null
  warnings: MarketWarning[]
  settlement: SettlementCapability
  selections: ApiMarketSelection[]
  /** Exact score only: the provider's remainder for scorelines it did not list. Never a selection. */
  remainder?: number | null
}

export interface ApiMarketGroup {
  group: MarketGroupId
  markets: ApiMarket[]
}

export interface ApiForecastReference {
  record_id: string | null
  snapshot_id: string | null
  captured_before_kickoff: boolean | null
  retrieved_at: string | null
  model_run_at: string | null
  provider_updated_at: string | null
  state: 'available' | 'stale' | 'kickoff_passed' | 'unavailable' | 'snapshot' | string | null
  state_reason: string | null
}

export interface ApiRecommendedBet {
  rank: string
  raw: unknown
  selection_id: string | null
  resolved: boolean
  reason: string | null
}

export interface ApiProviderOdds {
  market_id: MarketId
  source: string
  provider: string
  bookmaker: string | null
  captured_at: string | null
  note: string
}

export interface ApiMarketEnvelope {
  match_id: string
  provider: string | null
  normalisation_version: string
  /** When this normalisation ran — not when the forecast was fetched. */
  built_at: string
  forecast: ApiForecastReference
  groups: ApiMarketGroup[]
  recommended_bets: ApiRecommendedBet[]
  provider_odds: ApiProviderOdds | null
  anomalies: MarketWarning[]
  reason: string | null
}

/* ------------------------------------------------------------------------------ capabilities */

export interface ApiCapabilityFamily {
  family: string
  markets: MarketId[]
  status: 'served' | 'calculated' | 'served_not_tracked' | 'unavailable'
  provider: string | null
  payload_field: string | null
  settlement: string
  cost?: string
  reason?: string
}

export interface ApiCapabilities {
  normalisation_version: string
  families: ApiCapabilityFamily[]
}

/* ------------------------------------------------------------------------------ suggestions */

export interface ApiMatchSummary {
  id: string
  home: { id: string; name: string; short_name: string | null; logo?: string } | null
  away: { id: string; name: string; short_name: string | null; logo?: string } | null
  competition: { id: string; name: string; key?: string | null; is_national_team?: boolean } | null
  kickoff_utc: string | null
  status: string
  minute?: string | null
  score?: Record<string, number | null> | null
}

export interface ApiSuggestedLeg {
  match: ApiMatchSummary
  selection: ApiMarketSelection
  why: {
    probability: number
    probability_source: 'provider' | 'calculated'
    threshold: number
    ceiling: number
    rank: number
    forecast: {
      provider: string | null
      snapshot_id: string | null
      model_run_at: string | null
      retrieved_at: string | null
      state: string | null
      age_hours: number | null
      captured_before_kickoff: boolean | null
    }
    warnings: MarketWarning[]
    settlement: SettlementCapability
    provider_odds: SelectionOdds | null
  }
}

export interface ApiCombination {
  index: number
  legs: ApiSuggestedLeg[]
  /** `value` is null when the figure is withheld (a draw-no-bet leg); `basis` says why either way. */
  combined_probability: { value: number | null; basis: string }
  combined_odds: { value: number; format: 'decimal'; source: string; note: string } | null
}

export interface ApiSuggestions {
  generated_at: string
  rules: {
    version: string
    legs: number
    min_probability: number
    max_probability: number
    markets: MarketId[]
    max_combinations: number
    include_stale: boolean
    settleable_only: boolean
    kickoff_from: string | null
    kickoff_to: string | null
    odds_min: number | null
    odds_max: number | null
    competition_ids: string[]
    selection_rule: string
    combined_probability: string
    source: string
  }
  pool: { fixtures_in_window: number; qualifying: number; excluded: Record<string, number> }
  combinations: ApiCombination[]
  shortfall: string | null
}

export interface SuggestionQuery {
  legs?: number
  min_probability?: number
  max_probability?: number
  markets?: MarketId[]
  competitions?: string[]
  from?: string
  to?: string
  odds_min?: number
  odds_max?: number
  max_combinations?: number
  include_stale?: boolean
}

/* ------------------------------------------------------------------------------ slips */

export type SlipStatus = 'draft' | 'saved' | 'recorded'
export type SettlementState = 'pending' | 'won' | 'lost' | 'void' | 'unresolved'

export interface ApiSlipLeg {
  id: string
  position: number
  match: ApiMatchSummary
  selection: { selection_id: string; market_id: MarketId; outcome: string; line: number | null; period: MarketPeriod }
  /** The probability on the page when the leg was added. Never rewritten. */
  probability: number | null
  probability_source: 'provider' | 'calculated'
  calculation: SelectionCalculation | null
  provider: string
  snapshot_id: string | null
  model_run_at: string | null
  forecast_fetched_at: string | null
  normalisation_version: string
  odds: SelectionOdds | null
  kickoff_utc: string | null
  started: boolean
  /** The same selection read from the CURRENT forecast, for comparison only. */
  current: { probability: number | null; available: boolean; forecast_changed: boolean; state: string | null }
  state: SettlementState
  settled_at: string | null
  settlement: Record<string, unknown> | null
  settlement_capability: SettlementCapability | null
}

export interface ApiPotential {
  currency: string
  stake: string
  gross_return: string
  net_profit: string
  rounding: string
  note: string
}

export interface ApiSlip {
  id: string
  name: string | null
  status: SlipStatus
  note: string | null
  currency: string | null
  /** Decimal text in `currency`, as the reader entered it. */
  stake: string | null
  /** The ORIGINAL price: as recorded, or the product of every leg's price before recording. */
  price: number | null
  price_source: 'user' | 'provider_snapshot' | 'mixed' | null
  price_missing_legs: number
  price_note: string
  /** What the combination pays on now: the original, or the remaining legs' product once a leg is void; null when that cannot be computed. */
  effective_price: number | null
  effective_price_source: string | null
  effective_price_note: string | null
  /** Computed from `effective_price`, never from the original once a leg is void. */
  potential: ApiPotential | null
  potential_withheld_reason: string | null
  recorded_at: string | null
  recorded_reference: string | null
  recorded_note: string | null
  state: SettlementState
  settled_at: string | null
  counts: Record<SettlementState | 'legs', number>
  created_at: string
  updated_at: string
  legs: ApiSlipLeg[]
}

export interface SlipLegInput {
  match_id: string
  selection_id: string
  odds?: number | null
}
