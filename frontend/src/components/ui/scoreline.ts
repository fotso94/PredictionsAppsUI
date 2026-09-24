/**
 * The periods of a tie, turned into lines a reader can be shown beside its score.
 *
 * A knockout tie has more than one scoreline and they answer different questions. Switzerland
 * 0-0 Colombia, won 4-3 on penalties, is a draw to every market the backend settles — those
 * settle on the 90-minute score and nothing else — and a Switzerland win to everyone who watched
 * it. A reader shown only one of those two has been told half of what happened, so the periods
 * are rendered ALONGSIDE the score, never merged into it: "4-3" is never shown where "0-0" is the
 * score the tie finished at.
 *
 * Every period arrives from `GET /api/v1/matches/...` as a number or as nothing, and nothing means
 * the source did not supply it — which is not zero. A period that is absent produces no line at
 * all rather than a `0–0` nobody reported, which is the same rule the probability helpers follow
 * for a market a source never published.
 *
 * Selection and wording only. Nothing here derives one period from another: an extra-time score is
 * not inferred from a shoot-out, and a 90-minute score is never reconstructed from the rest.
 *
 * Plain helpers, deliberately in a .ts file: a .tsx may export only components.
 */

import type { MatchResult } from '@/types'
import { t } from '@/i18n'

interface Pair {
  home: number
  away: number
}

/** A period the source actually supplied, or null. Guards against a partly-filled pair. */
function supplied(pair: Pair | undefined | null): Pair | null {
  if (!pair) return null
  return typeof pair.home === 'number' && typeof pair.away === 'number' ? pair : null
}

/** "4–3 on penalties", or null when the tie was not decided on penalties. */
export function penaltiesLine(result: MatchResult | undefined | null, short = false): string | null {
  const pens = supplied(result?.penaltyScore)
  if (!pens) return null
  return t(short ? 'fixture.score.penaltiesShort' : 'fixture.score.penalties',
    { home: pens.home, away: pens.away })
}

/**
 * "After extra time", or null when nothing says the tie went past 90 minutes.
 *
 * The extra-time SCORE is not repeated here: it is already the score on screen, because the score
 * of a tie is the football that was played, extra time included. What is missing without this
 * line is that those goals took 120 minutes rather than 90.
 */
export function extraTimeLine(result: MatchResult | undefined | null, short = false): string | null {
  return supplied(result?.extraTimeScore)
    ? t(short ? 'fixture.score.afterExtraTimeShort' : 'fixture.score.afterExtraTime')
    : null
}

/**
 * "1–1 after 90 minutes" — the period every market settles on, and only when it is not already
 * the score on screen.
 *
 * For an ordinary match the two are the same number and a second line saying so would be noise.
 * For a tie won in extra time they differ, and that difference is the whole reason a forecast of
 * a draw can be correct against a 2-1 scoreline.
 */
export function regulationLine(result: MatchResult | undefined | null): string | null {
  const regulation = supplied(result?.fullTimeScore)
  if (!regulation) return null
  if (regulation.home === result?.homeScore && regulation.away === result?.awayScore) return null
  return t('fixture.score.regulation', { home: regulation.home, away: regulation.away })
}

/**
 * Every period worth showing beside this tie's score, in the order a reader reads them.
 *
 * Empty for the ordinary match, which is most of them: a league fixture that ended 2-1 after 90
 * minutes has one scoreline and needs no second line explaining it.
 */
export function periodLines(result: MatchResult | undefined | null, short = false): string[] {
  return [regulationLine(result), extraTimeLine(result, short), penaltiesLine(result, short)]
    .filter((line): line is string => line !== null)
}
