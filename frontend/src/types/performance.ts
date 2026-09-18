/**
 * The measured record: what each source actually got right, counted from settled results.
 *
 * Served by `GET /api/v1/performance/sources` (backend/app/api/v1/endpoints/performance.py, which
 * computes everything in `app/services/settlement.py`). Nothing in this payload is estimated: every
 * figure is arithmetic over stored score rows, and a figure the backend refused to compute arrives
 * as `null` beside the reason it was refused.
 *
 * THREE PROPERTIES OF THIS PAYLOAD THE INTERFACE MUST PRESERVE.
 *
 *  1. A figure never travels without its sample. `hit_rate` is meaningless without
 *     `hit_rate_sample`, and the backend withholds the rate entirely below `minimum_sample`
 *     rather than publishing one from a handful of matches. A withheld figure is `null` WITH a
 *     `*_unavailable_reason` — it is a sentence to print, never a zero, a dash or an empty bar.
 *  2. A figure never travels without its definition. `hit_rate_definition`, `brier_definition`
 *     and `rule` are the backend's own words for what was counted, and they are what makes the
 *     number checkable.
 *  3. A figure never travels without its window. `window` says which kickoffs were included and
 *     on what basis, so "62%" cannot be read as an all-time claim.
 *
 * Nothing here is a prediction, and nothing here may be presented as one: a measured record is a
 * statement about the past.
 */

/** The range of kickoffs a measurement covers, in the backend's own terms. */
export interface MeasuredWindow {
  /** First kickoff date included, ISO `YYYY-MM-DD`. */
  start: string;
  /** Last kickoff date included, ISO `YYYY-MM-DD`. */
  end: string;
  /** How the two dates are to be read, e.g. "kickoff date in UTC, both ends included". */
  basis: string;
}

/**
 * The settlement ruleset every figure on this installation was computed with.
 *
 * Published alongside the numbers on purpose: a hit rate is only checkable against the rule that
 * produced it. `markets` is an open map so a market added to the backend after this build shipped
 * still reaches the reader with its rule attached.
 */
export interface SettlementRules {
  version: string;
  basis: string;
  void: string;
  unsupplied_market: string;
  prematch_only: string;
  markets: Record<string, string>;
  probability_of_actual: string;
  brier: string;
  brier_baselines: Record<string, number>;
  hit_rate: string;
  minimum_sample: number;
  minimum_sample_rationale: string;
}

/**
 * One market's measured record for one source.
 *
 * `scored` is the denominator behind `hit_rate`: voids, pushes and markets the source never
 * published are excluded from it, which is why `scored + pushes + voids + not_scored` is the
 * eligible total rather than `scored` alone.
 */
export interface MeasuredMarket {
  /** Market key, e.g. `match_result`. Open: a market this build has never heard of still arrives. */
  market: string;
  /** How this market settles, in the backend's words. */
  rule: string;
  scored: number;
  hits: number;
  pushes: number;
  voids: number;
  not_scored: number;

  /** Share of `scored` whose most likely published outcome occurred. Null when withheld. */
  hit_rate: number | null;
  hit_rate_available: boolean;
  /** How many scored predictions the rate was (or would be) computed from. Always present. */
  hit_rate_sample: number;
  /** Why no rate is published, when none is. Print it; never substitute a zero. */
  hit_rate_unavailable_reason: string | null;
  hit_rate_definition: string;

  /** Mean squared error of the published probabilities. Lower is better. Null when withheld. */
  brier_score: number | null;
  brier_available: boolean;
  brier_unavailable_reason: string | null;
  brier_definition: string;
  /** What an uninformative forecast would score on this market, for comparison. May be null. */
  brier_baseline: number | null;
  brier_sample: number;

  /** Mean probability the source published for the outcome that occurred. Null when none applies. */
  mean_probability_of_actual: number | null;
  mean_probability_of_actual_definition: string;
  mean_probability_of_actual_sample: number;
}

/** One reason predictions were not scored, and how many it applied to. */
export interface MeasuredNotScoredReason {
  reason: string;
  count: number;
}

/**
 * One source over the window: a model provider, or an expert.
 *
 * `measured` is the gate. When it is false the source has NO headline figure and
 * `not_measured_reason` is the sentence to show instead — that path is the normal one on an
 * installation where settlement has not yet had results to score.
 */
export interface MeasuredSource {
  /** `model_provider` or `expert`; open, so a source kind added later still renders. */
  source_type: string;
  source_id: string;
  source_label: string;
  /** Predictions from this source that were in scope at all. */
  eligible: number;
  /** Predictions actually scored against a result. The sample behind everything else. */
  scored: number;
  /** Settled fixtures still waiting to be scored. */
  pending: number;
  /** Fixtures that were never played to a result: never a win, never a loss. */
  void: number;
  /** Eligible predictions the rules refused to score, with the reasons below. */
  not_scored: number;
  not_scored_reasons: MeasuredNotScoredReason[];
  markets: MeasuredMarket[];
  measured: boolean;
  /** Why this source has no measured record, when it has none. */
  not_measured_reason: string | null;
}

/** The whole `GET /api/v1/performance/sources` payload. */
export interface MeasuredPerformance {
  window: MeasuredWindow;
  /** Scored predictions required before any headline figure is published. */
  minimum_sample: number;
  minimum_sample_rationale: string;
  rules: SettlementRules;
  sources: MeasuredSource[];
  /** How many entries of `sources` have `measured: true`. */
  sources_measured: number;
  /** Why nothing at all is measured, when the source list is empty. */
  not_measured_reason: string | null;
  measured_at: string;
}
