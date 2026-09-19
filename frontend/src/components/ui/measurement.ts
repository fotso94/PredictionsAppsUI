/**
 * Reading the measured record.
 *
 * Selection and wording only. Nothing here computes a hit rate, fills in a missing one, rounds a
 * refused figure up into existence or turns a sample of four into a headline: every number these
 * helpers hand to a component came from `GET /api/v1/performance/sources`, and every figure that
 * endpoint withheld arrives as `null` beside the backend's own sentence explaining why.
 *
 * THE RULE THAT SHAPES ALL OF IT. A measured figure may only ever appear with its sample size, the
 * definition of what was counted, and the window it was counted over. A percentage on its own is
 * not a fact a reader can check, and below the backend's minimum sample it is not even a good
 * estimate — which is why `hit_rate` comes back null with a reason rather than as a small,
 * confident-looking number.
 *
 * AND EVERY STATE IS WRITTEN OUT, because which one a visitor meets depends only on how much has
 * been scored by the time they arrive, and that changes as results come in. "Nothing scored",
 * "scored but below the minimum sample" and "measured" each get their own sentences here, so no
 * caller has to invent wording — and so no sentence asserts one of those states as a standing fact
 * about this installation. An earlier version of this comment did exactly that, and it was still
 * claiming nothing had been scored after four forecasts had been.
 *
 * Plain helpers, deliberately in a .ts file: a .tsx may export only components.
 */

import type { MeasuredMarket, MeasuredPerformance, MeasuredSource } from '@/types';
import type { PerformanceResult } from '@/services/performance.service';
import type { MessageKey } from '@/i18n';
import { formatIsoDate, formatPercentTrimmed, t } from '@/i18n';

/**
 * Market names as the settlement service keys them.
 *
 * Deliberately its own map rather than the brief's (`@/utils/brief`): settlement calls the same
 * markets `both_teams_score`, `over_under_2_5`, `over_under_3_5` and `correct_score`, where the
 * brief calls them `btts`, `over_under_25`, `over_under_35` and `exact_score`. Reusing the wrong
 * map would silently drop every market but the first.
 */
const MEASURED_MARKET_KEY: Record<string, MessageKey> = {
  match_result: 'measured.market.matchResult',
  both_teams_score: 'measured.market.bothTeamsScore',
  over_under_2_5: 'measured.market.overUnder25',
  over_under_3_5: 'measured.market.overUnder35',
  correct_score: 'measured.market.correctScore',
};

/** A market key as a display name, never dropping a key this build does not recognise. */
export function measuredMarketLabel(key: string): string {
  const message = MEASURED_MARKET_KEY[key];
  return message ? t(message) : key.replace(/_/g, ' ');
}

/** How a source is introduced: what kind of thing published the predictions being scored. */
export function sourceKindLabel(sourceType: string): string {
  if (sourceType === 'model_provider') return t('measured.sourceKind.modelProvider');
  if (sourceType === 'expert') return t('measured.sourceKind.expert');
  return sourceType.replace(/_/g, ' ');
}

/**
 * A 0-1 ratio as a percentage string, to one decimal place with a trailing `.0` dropped.
 *
 * Returns null — never "0%" — for anything that is not a finite number, so a withheld figure can
 * never be rendered as a zero by accident.
 */
export function ratioPercent(ratio: number | null | undefined): string | null {
  if (typeof ratio !== 'number' || !Number.isFinite(ratio)) return null;
  return formatPercentTrimmed(Math.round(ratio * 1000) / 10);
}

/** "18 June 2026 to 18 September 2026" — the window, spelled out rather than as two ISO strings. */
export function windowText(performance: MeasuredPerformance): string {
  /*
   * The window's two ends are CALENDAR DATES the backend published, not instants. They are
   * spelled out in the reader's language but deliberately NOT re-bucketed into their chosen
   * time zone: "18 June to 18 September" is the window settlement actually counted over, and
   * shifting either end by a zone offset would move a measured boundary to make a display read
   * nicely. `formatIsoDate` anchors at midday, which is what keeps the date stable.
   */
  return t('measured.window', {
    start: formatIsoDate(performance.window.start, false),
    end: formatIsoDate(performance.window.end, false),
  });
}

/**
 * What a market counted that is NOT in its sample: pushes, voids and unscorable predictions.
 *
 * They are real and they are published, but none of them is in the denominator of a hit rate. They
 * used to trail the hit count on the same line — "1 of 4 scored · 1 push · 2 not scorable" — where
 * a reader had to work out which of the four numbers the rate would be computed from. Given its
 * own labelled row, the sample stays a single number the correct-outcome count can be checked
 * against. Returns null when nothing was excluded, so no row is rendered saying "nothing".
 */
export function excludedCountsText(market: MeasuredMarket): string | null {
  const parts: string[] = [];
  if (market.pushes > 0) parts.push(t('measured.excluded.pushes', { count: market.pushes }));
  if (market.voids > 0) parts.push(t('measured.excluded.voids', { count: market.voids }));
  if (market.not_scored > 0) parts.push(t('measured.excluded.notScored', { count: market.not_scored }));
  return parts.length > 0 ? parts.join(' · ') : null;
}

/** The counts behind a source, which are published whether or not a headline figure is. */
export function sourceCounts(source: MeasuredSource): string {
  const parts = [t('measured.counts.scored', { count: source.scored })];
  if (source.pending > 0) parts.push(t('measured.counts.pending', { count: source.pending }));
  if (source.void > 0) parts.push(t('measured.counts.void', { count: source.void }));
  if (source.not_scored > 0) parts.push(t('measured.counts.notScored', { count: source.not_scored }));
  return t('measured.counts', { eligible: source.eligible, parts: parts.join(' · ') });
}

/**
 * What the panel should render, decided once so the component cannot drift from it.
 *
 * Four states, and they are four different claims:
 *  - `failed`      we could not ask. NOT "nothing has been measured".
 *  - `none`        the endpoint answered and no source was even eligible in the window.
 *  - `pending`     sources exist, and not one of them has anything scored yet.
 *  - `measured`    at least one source has a record, and it is shown with its sample.
 */
export type MeasuredState = 'failed' | 'none' | 'pending' | 'measured';

export interface MeasuredView {
  state: MeasuredState;
  /** The sentence that leads the panel. The backend's own words wherever it supplied them. */
  headline: string;
  /** A supporting sentence, or null. */
  detail: string | null;
  /** The payload, when there is one to render rows from. */
  performance: MeasuredPerformance | null;
  /** Sources with `measured: true`, in payload order. Empty except in the `measured` state. */
  measured: MeasuredSource[];
  /** Sources with nothing scored. Always shown: their counts are real even when no rate is. */
  unmeasured: MeasuredSource[];
}

/** Turn a service result into exactly what the panel will say. */
export function measuredView(result: PerformanceResult | null): MeasuredView {
  if (!result) {
    return {
      state: 'failed',
      headline: t('measured.state.notLoaded'),
      detail: null,
      performance: null,
      measured: [],
      unmeasured: [],
    };
  }

  if (result.state === 'failed') {
    return {
      state: 'failed',
      // Carefully not "nothing has been measured": a failed request is a fact about the request.
      headline: t('measured.state.failed'),
      // `{error}` is the service's own sentence; only the clause after it is ours.
      detail: t('measured.state.failedDetail', { error: result.error }),
      performance: null,
      measured: [],
      unmeasured: [],
    };
  }

  const performance = result.data;
  const measured = performance.sources.filter(source => source.measured);
  const unmeasured = performance.sources.filter(source => !source.measured);

  if (performance.sources.length === 0) {
    return {
      state: 'none',
      headline: t('measured.state.none'),
      // The backend's sentence verbatim, after a colon so its lower-case opening reads as the
      // clause it is. Only a trailing full stop is normalised — the words are never rewritten,
      // and never translated: they are the backend's, not ours.
      detail: performance.not_measured_reason
        ? t('measured.state.noneWhy', { reason: performance.not_measured_reason.replace(/\.\s*$/, '') })
        : t('measured.state.noneDetail'),
      performance,
      measured: [],
      unmeasured: [],
    };
  }

  if (measured.length === 0) {
    return {
      state: 'pending',
      headline: t('measured.state.pending'),
      detail: t('measured.state.pendingDetail'),
      performance,
      measured: [],
      unmeasured,
    };
  }

  return {
    state: 'measured',
    headline: t('measured.state.measured', {
      measured: measured.length,
      total: performance.sources.length,
    }),
    detail: t('measured.state.measuredDetail'),
    performance,
    measured,
    unmeasured,
  };
}
