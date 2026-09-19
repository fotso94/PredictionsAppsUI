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
import { formatPercentTrimmed, t } from '@/i18n';
import type { MessageKey } from '@/i18n';

/**
 * How each source is named in the interface. Short, because it sits in a dense row.
 *
 * FUNCTIONS, NOT MAPS. A `Record` literal is evaluated once when the module is imported, which
 * for the catalogue means "in whatever language was active at boot" — and this application lets
 * the reader change that without reloading. Every one of these lookups therefore reads `t` at
 * call time. The maps are gone; the keys they were indexed by are unchanged.
 */
export function sourceLabel(source: BriefSourceKey): string {
  return t(source === 'expert' ? 'source.expert' : 'source.model');
}

/** The same, spelled out for a screen reader or a tooltip. */
export function sourceDescription(source: BriefSourceKey): string {
  return t(source === 'expert' ? 'source.description.expert' : 'source.description.model');
}

/**
 * Short label for a missing-data reason, for a chip or a column that has no room for the sentence.
 *
 * Each one stays a distinct statement. "We have never retrieved a forecast", "the forecast omits
 * this market", "what we hold is stale" and "we cannot refresh right now" must never collapse into
 * a single "unavailable" — the whole point of the reason codes is that they are different facts.
 * When there is room, show `BriefSourceBlock.detail` instead: it is the full sentence.
 */
const MISSING_REASON_KEY: Record<BriefMissingReason, MessageKey> = {
  no_forecast_retrieved: 'missing.noForecastRetrieved',
  market_not_in_forecast: 'missing.marketNotInForecast',
  forecast_stale: 'missing.forecastStale',
  refresh_blocked: 'missing.refreshBlocked',
  no_expert_prediction: 'missing.noExpertPrediction',
  market_not_supplied: 'missing.marketNotSupplied',
  not_offered_by_source: 'missing.notOfferedBySource',
};

/**
 * Display names for market keys, for the ONE case the payload does not supply a label: the compact
 * brief's `supplied_markets` / `missing_markets`, which carry keys only.
 *
 * Wherever a `BriefMarket` is to hand, use its own `label` instead — that is the backend's wording
 * and it stays correct for a market added after this build shipped. `marketLabel` below falls back
 * to prettifying the key for exactly that case, rather than dropping the market from the list.
 */
const MARKET_KEY: Record<BriefMarketKey, MessageKey> = {
  match_result: 'market.matchResult',
  btts: 'market.btts',
  over_under_25: 'market.overUnder25',
  over_under_35: 'market.overUnder35',
  exact_score: 'market.exactScore',
};

/** The display name for a market key, never dropping a key this build does not recognise. */
export function marketLabel(key: BriefMarketKey | string): string {
  const message = MARKET_KEY[key as BriefMarketKey];
  return message ? t(message) : String(key).replace(/_/g, ' ');
}

/**
 * What a market counts, and the one thing none of the sources says about it.
 *
 * Returns the definition and, separately, the note that the PERIOD is not published. The two are
 * kept apart because they are different kinds of statement: the first is what the market means,
 * the second is a limit on what anybody has told us about it. Null for a market this build does
 * not recognise — a made-up definition would be worse than none.
 */
export function marketDefinition(key: BriefMarketKey | string): string | null {
  switch (key) {
    case 'match_result': return t('market.definition.1x2');
    case 'btts': return t('market.definition.btts');
    case 'over_under_25':
    case 'over_under_35': return t('market.definition.overUnder');
    case 'exact_score': return t('market.definition.correctScore');
    default: return null;
  }
}

/** The sentence that says no source publishes the period a market covers. */
export function marketPeriodNote(): string {
  return t('market.period.note');
}

/** The short label, falling back to the raw code for a reason this build does not know. */
export function missingReasonLabel(reason: BriefMissingReason | null | undefined): string | null {
  if (!reason) return null;
  const message = MISSING_REASON_KEY[reason];
  return message ? t(message) : String(reason).replace(/_/g, ' ');
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
  // exactly the backend's `_pct_text` rule. Deliberately NOT localised: this value is compared
  // against the backend's own `percent_text`, and a comma would make two equal numbers unequal.
  // `percentDisplay` below is the one that reaches a reader.
  return String(Math.round(percent * 10) / 10);
}

/**
 * The same number as the reader reads it: 47.2% in English, 47,2 % in French.
 *
 * Separate from `percentText` on purpose. That one mirrors a backend string and is used for
 * comparison; this one is for display, and display means the reader's decimal separator and the
 * no-break space French puts before the sign. Returns null — never "0%" — for a value the source
 * did not publish.
 */
export function percentDisplay(percent: number | null | undefined): string | null {
  if (typeof percent !== 'number' || !Number.isFinite(percent)) return null;
  return formatPercentTrimmed(percent);
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
  if (hours < 1) return t('duration.minutes', { count: Math.max(1, Math.round(hours * 60)) });
  if (hours < 48) return t('duration.hours', { count: Math.round(hours) });
  return t('duration.days', { count: Math.round(hours / 24) });
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
      text: t('brief.noForecastHeld'),
      tone: 'problem',
      // The backend's own sentence wherever it gave one, untranslated: it is the source's words.
      detail: freshness.state_reason ?? t('brief.noForecastHeldDetail'),
    };
  }

  // The backend measures `age_hours` from whichever timestamp it names in `age_basis`, and says so;
  // the number is used as given rather than recomputed from a timestamp of our choosing.
  const measuredAge = ageText(freshness.age_hours);

  if (!freshness.model_run_at_known && measuredAge === null) {
    return {
      text: t('brief.ageUnknown'),
      tone: 'unknown',
      detail: t('brief.ageUnknownDetail'),
    };
  }

  const basisNote = freshness.model_run_at_known ? null : t('brief.basisNote');

  if (freshness.state === 'kickoff_passed') {
    return {
      text: measuredAge
        ? t('brief.keptForReferenceAged', { age: measuredAge })
        : t('brief.keptForReference'),
      tone: 'ageing',
      detail: freshness.state_reason ?? t('brief.kickoffPassedDetail'),
    };
  }

  if (freshness.stale || freshness.state === 'stale') {
    return {
      text: measuredAge ? t('brief.outOfDateAged', { age: measuredAge }) : t('brief.outOfDate'),
      tone: 'problem',
      detail: basisNote ?? (freshness.max_age_hours
        ? t('brief.staleDetailWithLimit', { hours: freshness.max_age_hours })
        : t('brief.staleDetail')),
    };
  }

  return {
    text: measuredAge ? t('brief.aged', { age: measuredAge }) : t('brief.current'),
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
  return freshness.refresh_blocked_reason ?? t('preview.refreshBlocked');
}
