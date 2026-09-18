/**
 * The match brief, as the backend assembles it (app/services/match_brief.py).
 *
 * The brief exists so the UI never has to interpret anything: every sentence, label, percentage
 * and "why is this missing" detail is assembled server-side from values a source actually
 * published. Nothing here is generated, interpolated or renormalised, and no language model is
 * involved anywhere in its production.
 *
 * Two rules these types are shaped to enforce:
 *
 *  1. A market a source did not supply arrives as a block with `available: false`, a `reason` code
 *     and a human `detail`. It must render as unavailable with that reason — NEVER as 0%, and
 *     never filled in from the other source, from odds or from the complementary outcome.
 *  2. "We have never retrieved a forecast", "the forecast we hold omits this market", "what we
 *     hold is stale" and "we cannot refresh right now" are four different statements. They keep
 *     four different `reason` codes and must not be collapsed into one message on screen.
 *
 * Renderers should prefer the payload's own `label`, `summary`, `detail` and `percent_text` over
 * anything they compute themselves, so an unrecognised market key still reads correctly.
 */

import type { ForecastAnomaly } from './index';

/** The two kinds of source a brief can carry. A provider forecast is "the model"; a person is "the expert". */
export type BriefSourceKey = 'model' | 'expert';

/**
 * Markets the brief can carry, in the order the backend emits them.
 *
 * The parser passes through whatever key the backend sent, so a future market arrives intact even
 * though it is not in this union: never `switch` on it without a `default` branch, and take display
 * text from `BriefMarket.label` rather than from a local lookup table.
 */
export type BriefMarketKey =
  | 'match_result'
  | 'btts'
  | 'over_under_25'
  | 'over_under_35'
  | 'exact_score';

/**
 * How a market's outcomes relate to each other.
 *  - `ranked`: mutually exclusive outcomes ordered by probability (1X2).
 *  - `pair`: two named sides (BTTS yes/no, over/under). Either side may be missing on its own.
 *  - `scores`: a scoreline distribution plus an "everything else" remainder.
 */
export type BriefMarketKind = 'ranked' | 'pair' | 'scores';

/**
 * State of one source's view of one market.
 *  - `available`: usable now.
 *  - `stale`: held, but older than the freshness limit. Shown with its age, not hidden.
 *  - `reference_only`: kickoff has passed; kept so the original forecast stays readable, and is
 *    explicitly no longer offered as a forecast.
 *  - `unavailable`: nothing to show; `reason` says why.
 */
export type BriefSourceState = 'available' | 'stale' | 'reference_only' | 'unavailable';

/** Why a source has nothing for a market. Each code is a distinct statement; do not merge them. */
export type BriefMissingReason =
  /** Nothing has ever been retrieved for this fixture: the model's view is genuinely unknown. */
  | 'no_forecast_retrieved'
  /** A forecast was retrieved, but it did not carry this market. */
  | 'market_not_in_forecast'
  /** We hold a forecast, but it is older than the configured freshness limit. */
  | 'forecast_stale'
  /** Refreshing is paused (allowance spent, provider cooling down). Nobody has asked recently. */
  | 'refresh_blocked'
  /** No expert has published anything for this fixture. */
  | 'no_expert_prediction'
  /** The expert published a prediction, but left this market out of it. */
  | 'market_not_supplied'
  /** This source does not publish this market at all (experts publish no scorelines). */
  | 'not_offered_by_source';

/** Freshness verdict for the model forecast as a whole. Mirrors `ForecastState` in ./index. */
export type BriefFreshnessState = 'available' | 'stale' | 'kickoff_passed' | 'unavailable';

/** Whether a published confidence value covers the whole prediction or just one market. */
export type BriefConfidenceScope = 'prediction' | 'market';

/** One outcome, exactly as the source published it. `percent_text` is the backend's own rounding. */
export interface BriefOutcome {
  /** 'home_win' | 'draw' | 'away_win' | 'yes' | 'no' | 'over' | 'under', or a scoreline like '2-1'. */
  key: string;
  label: string;
  /** The label as it reads inside a sentence, e.g. "a home win". */
  phrase: string;
  /** 0-1, verbatim from the source. */
  probability: number;
  /** 0-100, the same number scaled. */
  percent: number;
  /** Already rounded for display by the backend; prefer it over rounding `percent` again. */
  percent_text: string;
  /** 1 = strongest published outcome in this market for this source. */
  rank: number;
  most_likely: boolean;
}

/**
 * What one source has for one market.
 *
 * `confidence_published`, `confidence` and `accuracy_measured` are three separate facts and must
 * stay separate on screen: a probability is not a confidence, and a published confidence is not a
 * measured accuracy. `accuracy_measured` is false everywhere until results scoring lands.
 */
export interface BriefSourceBlock {
  source: BriefSourceKey;
  state: BriefSourceState;
  /** True only when `outcomes` carries something. False means render the `detail` sentence. */
  available: boolean;
  reason: BriefMissingReason | null;
  /** The backend's own sentence for why this is missing or stale. Show it verbatim. */
  detail: string | null;
  outcomes: BriefOutcome[];
  /** A complete sentence describing this block, assembled from the published numbers. */
  summary: string | null;
  confidence_published: boolean;
  /** 0-1. Null whenever `confidence_published` is false — never substitute a derived band. */
  confidence: number | null;
  confidence_percent: number | null;
  confidence_scope: BriefConfidenceScope | null;
  /** Always false today: nothing in this application has scored a prediction against a result yet. */
  accuracy_measured: boolean;
  accuracy_detail: string | null;
  /** `scores` markets only: the provider's remainder for every scoreline it did not list. */
  other_scorelines_probability?: number | null;
  other_scorelines_percent?: number | null;
}

/** One market, with both sources side by side. Either side may be unavailable. */
export interface BriefMarket {
  key: BriefMarketKey;
  /** Display name from the backend. Use this rather than mapping `key` locally. */
  label: string;
  kind: BriefMarketKind;
  /** The sources whose block is actually available, in model-then-expert order. */
  supplied_by: BriefSourceKey[];
  model: BriefSourceBlock;
  expert: BriefSourceBlock;
}

/**
 * One gap, reported rather than silently dropped.
 *
 * `scope: 'source'` is a statement about the whole source on this fixture (no forecast was ever
 * retrieved, what we hold is stale, a refresh is blocked, no expert has published) and carries
 * `market: null`. `scope: 'market'` is a statement about one market of one source. The two are not
 * interchangeable: only the market-scoped entries feed `MatchBriefCompact.missing_markets`.
 */
export interface BriefMissingEntry {
  scope: 'source' | 'market';
  source: BriefSourceKey;
  market: BriefMarketKey | null;
  reason: BriefMissingReason;
  detail: string;
}

/**
 * When the forecast was produced, updated and retrieved — three distinct times, never collapsed.
 *
 * `model_run_at` is the only one the provider calls a generation time. When
 * `model_run_at_known` is false the generation time is genuinely unknown, and showing
 * `retrieved_at` in its place would be a claim the provider never made.
 */
export interface BriefFreshness {
  state: BriefFreshnessState;
  state_reason: string | null;
  stale: boolean;
  kickoff_passed: boolean;
  model_run_at: string | null;
  provider_updated_at: string | null;
  retrieved_at: string | null;
  model_run_at_known: boolean;
  provider_updated_at_known: boolean;
  retrieved_at_known: boolean;
  /** Names of the timestamps above that the provider never supplied. */
  unknown_timestamps: string[];
  /** Which timestamp `age_hours` was measured from; null when none was known. */
  age_basis: string | null;
  age_hours: number | null;
  max_age_hours: number | null;
  /** True when a refresh cannot run right now. This is not the same as "no forecast exists". */
  refresh_blocked: boolean;
  refresh_blocked_reason: string | null;
}

/** The competition as the match payload serialises it. */
export interface BriefCompetition {
  id: string | null;
  key: string | null;
  name: string;
  country: string | null;
  country_code: string | null;
  logo: string | null;
  is_cup: boolean;
  providers?: Record<string, string>;
}

/** Whether a source has anything at all for this fixture, and how it was linked to it. */
export interface BriefSourcePresence {
  source: BriefSourceKey;
  present: boolean;
  markets: BriefMarketKey[];
  /** model only */
  provider?: string | null;
  external_event_id?: string | null;
  /** How confidently the forecast was linked to this fixture ('exact' | 'high'). */
  match_confidence?: string | null;
  matched_by?: string | null;
  /** expert only */
  prediction_id?: string | null;
  published_at?: string | null;
  created_by?: string | null;
}

/** Facts about the fixture itself, each paired with a `*_known` flag rather than a silent null. */
export interface BriefKnown {
  kickoff_utc: string | null;
  kickoff_known: boolean;
  status: string | null;
  competition: BriefCompetition | null;
  competition_known: boolean;
  model_markets: BriefMarketKey[];
  expert_markets: BriefMarketKey[];
  sources: BriefSourcePresence[];
}

/** One source's published-confidence position, with the backend's own explanation. */
export interface BriefReliabilitySource {
  confidence_published: boolean;
  confidence: number | null;
  detail: string;
}

/**
 * Confidence and accuracy, kept apart on purpose.
 *
 * `accuracy_measured` / `results_scored` are false until predictions are scored against results.
 * A confidence a source published is not evidence it has ever been right.
 */
export interface BriefReliability {
  model: BriefReliabilitySource;
  expert: BriefReliabilitySource;
  accuracy_measured: boolean;
  results_scored: boolean;
  detail: string;
}

/** The full brief, returned by GET /api/v1/matches/{id}. */
export interface MatchBrief {
  match_id: string | null;
  assembled_at: string | null;
  /** The first available summary sentence, or the first missing-data detail when nothing is available. */
  headline: string | null;
  known: BriefKnown;
  markets: BriefMarket[];
  missing: BriefMissingEntry[];
  /** De-duplicated, sorted reason codes from `missing`. */
  missing_reasons: BriefMissingReason[];
  freshness: BriefFreshness;
  reliability: BriefReliability;
  /** Consistency problems the backend observed in the provider payload, reported not corrected. */
  anomalies: ForecastAnomaly[];
}

/** The slice of the brief carried on every fixture in a list payload. Costs no extra query. */
export interface MatchBriefCompact {
  match_id: string | null;
  headline: string | null;
  supplied_markets: Record<BriefSourceKey, BriefMarketKey[]>;
  missing_markets: Record<BriefSourceKey, BriefMarketKey[]>;
  missing_reasons: BriefMissingReason[];
  forecast_state: BriefFreshnessState;
  stale: boolean;
  refresh_blocked: boolean;
  refresh_blocked_reason: string | null;
  confidence_published: Record<BriefSourceKey, boolean>;
  accuracy_measured: boolean;
}
