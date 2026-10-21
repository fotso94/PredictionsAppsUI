/**
 * The composer's words, written at render time in the reader's language.
 *
 * ./composer.ts decides WHAT is wrong and returns it as a catalogue key and some numbers
 * (`ComposerMessage`); this file is the one place those become a sentence. The split is the fix for
 * QA finding 7's mechanism, not a tidy-up: the messages used to be English template literals built
 * inside `validateComposer`, which the composer page memoises on the values alone — so even a
 * translated sentence there would have stayed in whatever language was on screen when the expert
 * last typed. A key cannot go stale that way. Every function here reads `t()` and the active
 * locale when it is CALLED, so a component that calls it during render (and subscribes with
 * `useT`/`useLocale`) follows a language change on the next render.
 *
 * Each figure is formatted by its kind (see `ComposerFigure`) through ./percent's locale-aware
 * formatters, which print exactly the English the editor always printed and French in French.
 */

import { currentLocale, formatNumber, t } from '@/i18n'
import type { MessageParams } from '@/i18n/format'
import { ComposerFigure, ComposerMessage, OPTIONAL_MARKET_LINE, OptionalMarketKey } from './composer'
import { formatPercentPoints, formatPercentTotal, formatWholeNumber } from './percent'

/** One figure, written in the active locale by its kind. */
export function figureText(figure: ComposerFigure): string {
  const locale = currentLocale()
  switch (figure.kind) {
    case 'points': return formatPercentPoints(figure.value, locale)
    case 'whole': return formatWholeNumber(figure.value, locale)
  }
}

/** A validation message as the sentence the reader sees. */
export function composerText(message: ComposerMessage): string {
  const params: MessageParams = {}
  for (const [name, figure] of Object.entries(message.params ?? {})) params[name] = figureText(figure)
  return t(message.key, params)
}

/** A pair's 100% — "100%" / « 100 % » — which every total rule and hint names. */
export function hundredPercent(): string {
  return formatPercentTotal(100, currentLocale())
}

/** A goal line as the reader writes it: 2.5 / 2,5. */
export function goalLine(line: number): string {
  return formatNumber(line)
}

/** An optional market's name: "Both teams to score", "Over / under 2.5 goals". */
export function optionalMarketLabel(market: OptionalMarketKey): string {
  const line = OPTIONAL_MARKET_LINE[market]
  return line === null ? t('market.btts') : t('expert.editor.overUnderGoals', { line: goalLine(line) })
}
