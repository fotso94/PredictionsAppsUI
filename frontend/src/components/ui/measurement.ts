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
 * AND THE STATE WE ARE ACTUALLY IN. Nothing on this installation has been scored yet, so the
 * "not measured" path is the one a real visitor meets. It is treated as a first-class state with
 * its own sentences, not as an error or an empty chart.
 *
 * Plain helpers, deliberately in a .ts file: a .tsx may export only components.
 */

import type { MeasuredPerformance, MeasuredSource } from '@/types';
import type { PerformanceResult } from '@/services/performance.service';

/**
 * Market names as the settlement service keys them.
 *
 * Deliberately its own map rather than the brief's (`@/utils/brief`): settlement calls the same
 * markets `both_teams_score`, `over_under_2_5`, `over_under_3_5` and `correct_score`, where the
 * brief calls them `btts`, `over_under_25`, `over_under_35` and `exact_score`. Reusing the wrong
 * map would silently drop every market but the first.
 */
export const MEASURED_MARKET_LABEL: Record<string, string> = {
  match_result: 'Match result',
  both_teams_score: 'Both teams to score',
  over_under_2_5: 'Total goals 2.5',
  over_under_3_5: 'Total goals 3.5',
  correct_score: 'Exact score',
};

/** A market key as a display name, never dropping a key this build does not recognise. */
export function measuredMarketLabel(key: string): string {
  return MEASURED_MARKET_LABEL[key] ?? key.replace(/_/g, ' ');
}

/** How a source is introduced: what kind of thing published the predictions being scored. */
export function sourceKindLabel(sourceType: string): string {
  if (sourceType === 'model_provider') return 'Model provider';
  if (sourceType === 'expert') return 'Expert';
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
  return `${String(Math.round(ratio * 1000) / 10)}%`;
}

/** "18 June 2026 to 18 September 2026" — the window, spelled out rather than as two ISO strings. */
export function windowText(performance: MeasuredPerformance): string {
  const format = (iso: string): string => {
    const at = new Date(`${iso}T12:00:00Z`);
    return Number.isNaN(at.getTime())
      ? iso
      : at.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  };
  return `${format(performance.window.start)} to ${format(performance.window.end)}`;
}

/** The counts behind a source, which are published whether or not a headline figure is. */
export function sourceCounts(source: MeasuredSource): string {
  const parts = [`${source.scored} scored`];
  if (source.pending > 0) parts.push(`${source.pending} awaiting settlement`);
  if (source.void > 0) parts.push(`${source.void} void`);
  if (source.not_scored > 0) parts.push(`${source.not_scored} not scorable`);
  return `${source.eligible} eligible · ${parts.join(' · ')}`;
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
      headline: 'The measured record has not been loaded.',
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
      headline: 'The measured record could not be loaded.',
      detail: `${result.error} This says nothing about what has or has not been scored — only that we could not ask.`,
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
      headline: 'Nothing has been scored yet, so no source has a measured record.',
      // The backend's sentence verbatim, after a colon so its lower-case opening reads as the
      // clause it is. Only a trailing full stop is normalised — the words are never rewritten.
      detail: performance.not_measured_reason
        ? `Why: ${performance.not_measured_reason.replace(/\.\s*$/, '')}.`
        : 'No prediction in this window has been settled against a final result.',
      performance,
      measured: [],
      unmeasured: [],
    };
  }

  if (measured.length === 0) {
    return {
      state: 'pending',
      headline: 'No source has a measured record yet.',
      detail: 'Predictions from the sources below are in scope, but none of them has been scored '
        + 'against a final result yet. The counts are real; there is simply no rate to report.',
      performance,
      measured: [],
      unmeasured,
    };
  }

  return {
    state: 'measured',
    headline: `${measured.length} of ${performance.sources.length} `
      + `${performance.sources.length === 1 ? 'source has' : 'sources have'} a measured record.`,
    detail: 'Every figure below is counted from settled results and carries the sample it was '
      + 'counted from. It is a record of what happened, not a forecast of what will.',
    performance,
    measured,
    unmeasured,
  };
}
