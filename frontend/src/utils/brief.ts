/**
 * Reading the match brief.
 *
 * Lookups and wording only. Nothing in this file computes a probability, completes a market, or
 * turns an absent number into a present one: where the brief says a source supplied nothing, these
 * helpers return null and the caller must render the brief's own `detail` sentence.
 *
 * Prefer the payload's own text (`label`, `summary`, `detail`, `percent_text`) over anything
 * derived here — it is the statement the backend stands behind, and it stays correct for a market
 * this build has never heard of.
 */

import type {
  BriefFreshness, BriefMarket, BriefMarketKey, BriefMissingReason, BriefOutcome, BriefSourceBlock,
  BriefSourceKey, BriefSourcePresence, MatchBrief, MatchBriefCompact,
} from '@/types';

/** How each source is named in the interface. Short, because it sits in a dense row. */
export const SOURCE_LABEL: Record<BriefSourceKey, string> = {
  model: 'Model',
  expert: 'Expert',
};

/** The same, spelled out for a screen reader or a tooltip. */
export const SOURCE_DESCRIPTION: Record<BriefSourceKey, string> = {
  model: 'Forecast published by the model provider',
  expert: 'Prediction published by one of our experts',
};

/**
 * Short label for a missing-data reason, for a chip or a column that has no room for the sentence.
 *
 * Each one stays a distinct statement. "We have never retrieved a forecast", "the forecast omits
 * this market", "what we hold is stale" and "we cannot refresh right now" must never collapse into
 * a single "unavailable" — the whole point of the reason codes is that they are different facts.
 * When there is room, show `BriefSourceBlock.detail` instead: it is the full sentence.
 */
export const MISSING_REASON_LABEL: Record<BriefMissingReason, string> = {
  no_forecast_retrieved: 'Never retrieved',
  market_not_in_forecast: 'Not in this forecast',
  forecast_stale: 'Out of date',
  refresh_blocked: 'Refresh paused',
  no_expert_prediction: 'No expert prediction',
  market_not_supplied: 'Expert left this out',
  not_offered_by_source: 'Not published by this source',
};

/**
 * Display names for market keys, for the ONE case the payload does not supply a label: the compact
 * brief's `supplied_markets` / `missing_markets`, which carry keys only.
 *
 * Wherever a `BriefMarket` is to hand, use its own `label` instead — that is the backend's wording
 * and it stays correct for a market added after this build shipped. `marketLabel` below falls back
 * to prettifying the key for exactly that case, rather than dropping the market from the list.
 */
export const MARKET_LABEL: Record<BriefMarketKey, string> = {
  match_result: 'Match result',
  btts: 'Both teams to score',
  over_under_25: 'Total goals 2.5',
  over_under_35: 'Total goals 3.5',
  exact_score: 'Exact score',
};

/** The display name for a market key, never dropping a key this build does not recognise. */
export function marketLabel(key: BriefMarketKey | string): string {
  return MARKET_LABEL[key as BriefMarketKey] ?? String(key).replace(/_/g, ' ');
}

/** The short label, falling back to the raw code for a reason this build does not know. */
export function missingReasonLabel(reason: BriefMissingReason | null | undefined): string | null {
  if (!reason) return null;
  return MISSING_REASON_LABEL[reason] ?? String(reason).replace(/_/g, ' ');
}

/**
 * A 0-100 percentage as display text, by the backend's own rule: one decimal place, with a
 * trailing `.0` dropped. Matches `percent_text` in the brief, so a number shown from a list payload
 * and the same number shown from the brief read identically.
 *
 * Returns null — never "0%" — when the source published nothing.
 */
export function percentText(percent: number | null | undefined): string | null {
  if (typeof percent !== 'number' || !Number.isFinite(percent)) return null;
  // `String(85)` is "85" and `String(33.5)` is "33.5": the trailing `.0` never survives, which is
  // exactly the backend's `_pct_text` rule.
  return String(Math.round(percent * 10) / 10);
}

/** One market of the brief, or null when this brief does not carry it. */
export function findMarket(brief: MatchBrief | null | undefined, key: BriefMarketKey): BriefMarket | null {
  if (!brief) return null;
  return brief.markets.find(market => market.key === key) ?? null;
}

/** One source's block for one market, or null when the brief does not carry the market at all. */
export function marketBlock(
  brief: MatchBrief | null | undefined,
  key: BriefMarketKey,
  source: BriefSourceKey,
): BriefSourceBlock | null {
  const market = findMarket(brief, key);
  return market ? market[source] : null;
}

/**
 * The strongest outcome a source published for a market.
 *
 * Selection, not derivation: it picks one of the numbers already on the block. Returns null when
 * the block is unavailable or carries no outcomes, so the caller renders the unavailable state.
 */
export function leadOutcome(block: BriefSourceBlock | null | undefined): BriefOutcome | null {
  if (!block || !block.available || block.outcomes.length === 0) return null;
  return block.outcomes.find(outcome => outcome.most_likely)
    ?? block.outcomes.reduce((best, outcome) => (outcome.probability > best.probability ? outcome : best));
}

/** What the brief says about one source's presence on this fixture. */
export function sourcePresence(
  brief: MatchBrief | null | undefined,
  source: BriefSourceKey,
): BriefSourcePresence | null {
  return brief?.known.sources.find(entry => entry.source === source) ?? null;
}

/** True when the compact brief says this source supplied this market. Absent brief => false. */
export function suppliedMarket(
  compact: MatchBriefCompact | null | undefined,
  source: BriefSourceKey,
  market: BriefMarketKey,
): boolean {
  return Boolean(compact?.supplied_markets?.[source]?.includes(market));
}

/** How many markets a source supplied, by the compact brief's own count. */
export function suppliedMarketCount(
  compact: MatchBriefCompact | null | undefined,
  source: BriefSourceKey,
): number {
  return compact?.supplied_markets?.[source]?.length ?? 0;
}

/** "3 hours", "2 days" — a duration, never dressed up as a precise timestamp. */
export function ageText(hours: number | null | undefined): string | null {
  if (typeof hours !== 'number' || !Number.isFinite(hours) || hours < 0) return null;
  if (hours < 1) {
    const minutes = Math.max(1, Math.round(hours * 60));
    return `${minutes} minute${minutes === 1 ? '' : 's'}`;
  }
  if (hours < 48) {
    const whole = Math.round(hours);
    return `${whole} hour${whole === 1 ? '' : 's'}`;
  }
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? '' : 's'}`;
}

/** How a freshness line should be weighted on screen. `unknown` is not a problem, just unknown. */
export type FreshnessTone = 'ok' | 'ageing' | 'unknown' | 'problem';

export interface FreshnessLine {
  /** Short text for the row: "39 hours old", "Age unknown", "Never retrieved". */
  text: string;
  tone: FreshnessTone;
  /** The longer explanation, in the backend's own words when it gave one. May be null. */
  detail: string | null;
}

/**
 * One line describing how current the model forecast is.
 *
 * The three provider timestamps are never conflated: only `model_run_at` is when the provider says
 * its model ran, and when it did not publish one the age is genuinely UNKNOWN. Showing the fetch
 * time in its place would be a claim the provider never made, so this returns "Age unknown" and
 * names the retrieval time separately instead of quietly substituting it.
 *
 * "We cannot refresh right now" is reported as its own fact, because it says nothing about whether
 * the numbers already on screen are wrong — only that nobody has asked recently.
 */
export function freshnessLine(freshness: BriefFreshness | null | undefined): FreshnessLine | null {
  if (!freshness) return null;

  if (freshness.state === 'unavailable') {
    return {
      text: 'No forecast held',
      tone: 'problem',
      detail: freshness.state_reason ?? 'Nothing has been retrieved from the forecast provider for this fixture.',
    };
  }

  // The backend measures `age_hours` from whichever timestamp it names in `age_basis`, and says so;
  // the number is used as given rather than recomputed from a timestamp of our choosing.
  const measuredAge = ageText(freshness.age_hours);

  if (!freshness.model_run_at_known && measuredAge === null) {
    return {
      text: 'Age unknown',
      tone: 'unknown',
      detail: 'The provider published no model-run time for this forecast, so how old it is cannot be stated.',
    };
  }

  const basisNote = freshness.model_run_at_known
    ? null
    : 'The provider published no model-run time, so this age is measured from when we retrieved the forecast, not from when it was produced.';

  if (freshness.state === 'kickoff_passed') {
    return {
      text: measuredAge ? `Kept for reference · ${measuredAge} old` : 'Kept for reference',
      tone: 'ageing',
      detail: freshness.state_reason ?? 'Kickoff has passed. This is preserved as the forecast that was published, not offered as a current one.',
    };
  }

  if (freshness.stale || freshness.state === 'stale') {
    const limit = freshness.max_age_hours ? ` (limit ${freshness.max_age_hours} hours)` : '';
    return {
      text: measuredAge ? `Out of date · ${measuredAge} old` : 'Out of date',
      tone: 'problem',
      detail: basisNote ?? `This forecast is older than the freshness limit${limit}.`,
    };
  }

  return {
    text: measuredAge ? `${measuredAge} old` : 'Current',
    tone: 'ok',
    detail: basisNote,
  };
}

/**
 * Why a refresh is not running, when one is not.
 *
 * Returned separately from `freshnessLine` on purpose: a paused refresh and an out-of-date forecast
 * are different statements, and a reader who sees only "paused" must not conclude the numbers are
 * wrong, nor a reader who sees only "out of date" conclude nobody tried.
 */
export function refreshBlockedNote(
  freshness: BriefFreshness | MatchBriefCompact | null | undefined,
): string | null {
  if (!freshness || !freshness.refresh_blocked) return null;
  return freshness.refresh_blocked_reason ?? 'Forecast refreshes are paused right now.';
}
