/**
 * The one-line probability preview a dense fixture row shows.
 *
 * It answers two questions per source and nothing more: "what does this source make most likely for
 * the match result, and at what probability the source itself published?", and "if it says nothing,
 * exactly why not?".
 *
 * NOTHING IS DERIVED. The leading outcome is SELECTED from probabilities the source published — it
 * is never computed, rescaled, completed from the other outcomes, or borrowed from the other
 * source. A source that published no match-result market yields `lead: null` with a reason, which
 * the row renders as unavailable. It is never 0%, and it never falls back to odds or history.
 *
 * Where the full brief is present its own wording wins outright, because that is the sentence the
 * backend stands behind. Where only the compact brief is present (every list payload) the reason is
 * worked out from fields the compact brief actually states — whether a forecast exists at all,
 * whether an expert published — and never guessed from the union of reasons across all markets.
 */

import type {
  BriefConfidenceScope, BriefMissingReason, BriefSourceKey, BriefSourceState, Match,
  MatchPredictions,
} from '@/types';
import { leadOutcome, marketBlock, percentText, sourceLabel } from './brief';
import { t } from '@/i18n';

/** Which 1X2 outcome leads. The key is kept so a row can label it with the real team name. */
export type OutcomeKey = 'home_win' | 'draw' | 'away_win';

export interface PreviewOutcome {
  key: OutcomeKey;
  /** Generic label ("Home win"). A row with the teams to hand should prefer the team's own name. */
  label: string;
  /** 0-100, exactly as the source published it. */
  percent: number;
  /** Display text by the backend's rule: one decimal, trailing `.0` dropped. No '%' sign. */
  percentText: string;
}

/** The strongest published outcome. Kept as its own name because that is what a dense row shows. */
export type PreviewLead = PreviewOutcome;

/** A confidence value a source actually published. Absent whenever the source published none. */
export interface PreviewConfidence {
  /** 0-100. */
  percent: number;
  /** Whether the value covers the whole prediction or only one market. */
  scope: BriefConfidenceScope | null;
}

export interface SourcePreview {
  source: BriefSourceKey;
  /** 'Model' | 'Expert'. */
  label: string;
  /** True when this source has anything at all for this fixture. */
  present: boolean;
  /** Freshness/usability of this source's match-result view, when the brief stated it. */
  state: BriefSourceState;
  /** The leading match-result outcome, or null. Null must render as unavailable, never as 0%. */
  lead: PreviewLead | null;
  /**
   * Every match-result outcome this source published, strongest first. An outcome the source left
   * out is ABSENT from the array — it is never added back as 0%, and the three present need not sum
   * to 100: they are reproduced as published, not renormalised.
   */
  outcomes: PreviewOutcome[];
  /** Why there is no lead. Null when there is one. */
  reason: BriefMissingReason | null;
  /** A full sentence for `reason`, in the backend's words when it supplied them. */
  detail: string | null;
  /**
   * Only ever set when the source PUBLISHED a confidence value. A band worked out from how strong
   * a probability looks is not a confidence and is never put here — and neither is ever an accuracy.
   */
  confidence: PreviewConfidence | null;
}

export interface FixturePreview {
  model: SourcePreview;
  expert: SourcePreview;
  /** The brief's own headline sentence, when the payload carried a brief. */
  headline: string | null;
  /** True when at least one source has a match-result view to show. */
  anyLead: boolean;
  /** True when the model forecast we hold is older than the freshness limit. */
  stale: boolean;
  /**
   * Why a refresh is not running, if it is not. Separate from `stale` on purpose: "nobody has asked
   * recently" says nothing about whether the numbers on screen are wrong.
   */
  refreshBlockedReason: string | null;
  /**
   * False until predictions are scored against results. Nothing in this application has ever
   * measured an accuracy, so no part of the UI may present one.
   */
  accuracyMeasured: boolean;
}

/** Read per call, not built once at import: the reader can change language without reloading. */
const outcomeLabel = (key: OutcomeKey): string =>
  t(key === 'home_win' ? 'outcome.homeWin' : key === 'away_win' ? 'outcome.awayWin' : 'outcome.draw');

/**
 * The 1X2 outcomes a source published, strongest first.
 *
 * Only outcomes carrying a real number survive. Nothing is completed, rescaled or inferred: a
 * source that published two of the three arrives here with two.
 */
function outcomesFromPredictions(prediction: MatchPredictions | null | undefined): PreviewOutcome[] {
  // `markets.matchResult === false` is the source saying outright that it published no 1X2 block;
  // an `outcome` object alongside it would be zero-filled and must not be shown.
  if (!prediction?.outcome || prediction.markets?.matchResult === false) return [];
  const { homeWin, draw, awayWin } = prediction.outcome;
  return ([
    { key: 'home_win' as const, percent: homeWin },
    { key: 'draw' as const, percent: draw },
    { key: 'away_win' as const, percent: awayWin },
  ])
    .filter(entry => typeof entry.percent === 'number' && Number.isFinite(entry.percent))
    .map(entry => ({
      key: entry.key,
      label: outcomeLabel(entry.key),
      percent: entry.percent,
      percentText: percentText(entry.percent) ?? String(entry.percent),
    }))
    .sort((a, b) => b.percent - a.percent);
}

/** The same list, taken from a brief block (which has already ranked and formatted them). */
function outcomesFromBlock(block: { outcomes: Array<{ key: string; label: string; percent: number; percent_text: string }> } | null): PreviewOutcome[] {
  if (!block) return [];
  return block.outcomes
    .filter((outcome): outcome is typeof outcome & { key: OutcomeKey } => isOutcomeKey(outcome.key))
    .map(outcome => ({
      key: outcome.key,
      label: outcome.label,
      percent: outcome.percent,
      percentText: outcome.percent_text,
    }));
}

/** A published confidence, or null. `confidence_score` is 0-1 on both sources. */
function publishedConfidence(
  prediction: MatchPredictions | null | undefined,
  scope: BriefConfidenceScope,
): PreviewConfidence | null {
  const value = prediction?.confidence_score;
  // Absence has its own value: `confidence_score` is null when no confidence was supplied, so
  // null is the only thing that means "nobody made this judgement". A zero is a source that
  // rated its own conviction at nothing, and the brief path in this same file keeps it
  // (`confidence_published` with a `confidence_percent` of 0), so this path must keep it too —
  // otherwise one fixture reads two ways depending on which payload built the row.
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  return { percent: Math.round(value * 1000) / 10, scope };
}

function emptyPreview(source: BriefSourceKey, reason: BriefMissingReason, detail: string): SourcePreview {
  return {
    source,
    label: sourceLabel(source),
    present: false,
    state: 'unavailable',
    lead: null,
    outcomes: [],
    reason,
    detail,
    confidence: null,
  };
}

/**
 * Everything a compact fixture row needs, from whatever the payload actually carried.
 *
 * Works on a list payload (compact brief + the mapped predictions) and on a detail payload (full
 * brief), preferring the full brief wherever it is present.
 */
export function fixturePreview(match: Match): FixturePreview {
  const compact = match.briefCompact ?? null;
  const brief = match.brief ?? null;

  const forecast = match.providerForecast ?? null;
  const expertPrediction = match.expertPrediction ?? null;

  // ---------------------------------------------------------------- model
  const modelBlock = marketBlock(brief, 'match_result', 'model');
  const modelBriefLead = leadOutcome(modelBlock);
  let model: SourcePreview;
  if (modelBlock) {
    // The full brief said it: take its state, its numbers and its wording untouched.
    const outcomes = outcomesFromBlock(modelBlock);
    model = {
      source: 'model',
      label: sourceLabel('model'),
      present: Boolean(brief && brief.known.sources.some(entry => entry.source === 'model' && entry.present)),
      state: modelBlock.state,
      lead: modelBriefLead && isOutcomeKey(modelBriefLead.key)
        ? { key: modelBriefLead.key, label: modelBriefLead.label, percent: modelBriefLead.percent, percentText: modelBriefLead.percent_text }
        : null,
      outcomes,
      reason: modelBriefLead ? null : modelBlock.reason,
      detail: modelBriefLead ? null : modelBlock.detail,
      confidence: modelBlock.confidence_published && modelBlock.confidence_percent !== null
        ? { percent: modelBlock.confidence_percent, scope: modelBlock.confidence_scope }
        : null,
    };
  } else if (!forecast) {
    // No forecast object at all in the payload: the one thing we can say is that nothing has been
    // retrieved. Not "the market is missing" — there is no forecast for a market to be missing from.
    model = emptyPreview('model', 'no_forecast_retrieved',
      t('preview.noForecastRetrieved'));
  } else {
    const outcomes = outcomesFromPredictions(forecast);
    const lead = outcomes[0] ?? null;
    model = {
      source: 'model',
      label: sourceLabel('model'),
      present: true,
      state: forecastState(forecast),
      lead,
      outcomes,
      // A forecast exists, so a missing market can only be a market this forecast did not carry.
      reason: lead ? null : 'market_not_in_forecast',
      detail: lead ? null : t('preview.marketNotInForecast'),
      confidence: publishedConfidence(forecast, 'prediction'),
    };
  }

  // ---------------------------------------------------------------- expert
  const expertBlock = marketBlock(brief, 'match_result', 'expert');
  const expertBriefLead = leadOutcome(expertBlock);
  let expert: SourcePreview;
  if (expertBlock) {
    expert = {
      source: 'expert',
      label: sourceLabel('expert'),
      present: Boolean(brief && brief.known.sources.some(entry => entry.source === 'expert' && entry.present)),
      state: expertBlock.state,
      lead: expertBriefLead && isOutcomeKey(expertBriefLead.key)
        ? { key: expertBriefLead.key, label: expertBriefLead.label, percent: expertBriefLead.percent, percentText: expertBriefLead.percent_text }
        : null,
      outcomes: outcomesFromBlock(expertBlock),
      reason: expertBriefLead ? null : expertBlock.reason,
      detail: expertBriefLead ? null : expertBlock.detail,
      confidence: expertBlock.confidence_published && expertBlock.confidence_percent !== null
        ? { percent: expertBlock.confidence_percent, scope: expertBlock.confidence_scope }
        : null,
    };
  } else if (!expertPrediction) {
    expert = emptyPreview('expert', 'no_expert_prediction',
      t('preview.noExpertPrediction'));
  } else {
    const outcomes = outcomesFromPredictions(expertPrediction);
    const lead = outcomes[0] ?? null;
    expert = {
      source: 'expert',
      label: sourceLabel('expert'),
      present: true,
      state: 'available',
      lead,
      outcomes,
      reason: lead ? null : 'market_not_supplied',
      detail: lead ? null : t('preview.marketNotSupplied'),
      confidence: publishedConfidence(expertPrediction, 'prediction'),
    };
  }

  return {
    model,
    expert,
    headline: brief?.headline ?? compact?.headline ?? null,
    anyLead: model.lead !== null || expert.lead !== null,
    stale: brief?.freshness.stale ?? compact?.stale ?? (forecast?.state === 'stale'),
    refreshBlockedReason: brief?.freshness.refresh_blocked
      ? (brief.freshness.refresh_blocked_reason ?? t('preview.refreshBlocked'))
      : compact?.refresh_blocked
        ? (compact.refresh_blocked_reason ?? t('preview.refreshBlocked'))
        : null,
    // Hard-wired false, and read from the payload where the payload says it, because nothing here
    // has ever been scored against a result. A published confidence is not a measured accuracy.
    accuracyMeasured: brief?.reliability.accuracy_measured ?? compact?.accuracy_measured ?? false,
  };
}

function isOutcomeKey(key: string): key is OutcomeKey {
  return key === 'home_win' || key === 'draw' || key === 'away_win';
}

function forecastState(forecast: MatchPredictions): BriefSourceState {
  switch (forecast.state) {
    case 'stale': return 'stale';
    case 'kickoff_passed': return 'reference_only';
    case 'unavailable': return 'unavailable';
    default: return 'available';
  }
}
