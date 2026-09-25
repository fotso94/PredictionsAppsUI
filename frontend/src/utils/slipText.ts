/**
 * A slip as plain text, for the clipboard.
 *
 * What a reader pastes into their own bookmaker's app or a message: one line per leg with the
 * fixture, the kickoff in the reader's zone, the selection and the provider's published
 * probability; the price only where one was actually given; and the sentence that says what the
 * numbers are and are not. No booking code — there is no bookmaker integration to produce one, and
 * a made-up code would be the most harmful line on the page.
 */

import { backendInstant, formatDateTime, formatPercentValue, type TranslateFn } from '@/i18n'
import { selectionSentence } from './marketLabels'
import type { DockLeg } from '@/services/slips.service'

export interface SlipTextInput {
  name: string | null
  legs: DockLeg[]
  price: number | null
  priceSource: string | null
  stake: string | null
  currency: string | null
  potential: { gross_return: string; net_profit: string } | null
  combinedProbability: number | null
}

export function slipText(t: TranslateFn, input: SlipTextInput): string {
  const lines: string[] = []
  lines.push(`${input.name ?? t('selections.copy.untitled')} — ${t('selections.copy.count', { count: input.legs.length })}`)
  input.legs.forEach((leg, index) => {
    const when = leg.kickoffUtc ? formatDateTime(backendInstant(leg.kickoffUtc).at) ?? '' : ''
    const fixture = `${leg.home} v ${leg.away}${leg.competition ? ` (${leg.competition})` : ''}`
    const probability = leg.probability === null
      ? t('selections.copy.noProbability')
      : t('selections.copy.probability', { value: formatPercentValue(leg.probability * 100, 0) })
    const price = leg.odds ? ` @ ${leg.odds.value.toFixed(2)} (${leg.odds.source === 'user' ? t('selections.copy.priceUser') : t('selections.copy.priceProvider')})` : ''
    lines.push(`${index + 1}. ${when ? `${when} — ` : ''}${fixture}`)
    lines.push(`   ${selectionSentence(t, leg.selection, leg.home, leg.away)} — ${probability}${price}`)
  })
  if (input.price !== null) {
    lines.push(t('selections.copy.combinedPrice', { price: input.price.toFixed(2) }))
  } else {
    lines.push(t('selections.copy.noCombinedPrice'))
  }
  if (input.stake && input.currency) {
    lines.push(t('selections.copy.stake', { stake: input.stake, currency: input.currency }))
    if (input.potential) {
      lines.push(t('selections.copy.potential', { gross: input.potential.gross_return, net: input.potential.net_profit, currency: input.currency }))
    }
  }
  if (input.combinedProbability !== null) {
    lines.push(t('selections.copy.combinedProbability', { value: formatPercentValue(input.combinedProbability * 100, 1) }))
  }
  lines.push(t('selections.copy.disclaimer'))
  return lines.join('\n')
}

/**
 * The product of the legs' probabilities, or null when any leg has none - or when any leg is a
 * draw-no-bet selection: its probability is conditional on there being no draw, and a conditional
 * figure multiplied with the other legs' unconditional ones is not the chance of anything. Labelled
 * as an approximation wherever shown; `combinedProbabilityWithheld` says when and why it is not.
 */
export function combinedProbability(legs: Array<{ probability: number | null; selection: { market_id: string } }>): number | null {
  if (legs.length === 0 || combinedProbabilityWithheld(legs)) return null
  let product = 1
  for (const leg of legs) {
    if (leg.probability === null) return null
    product *= leg.probability
  }
  return product
}

/** True when a combined probability must not be shown for these legs (a draw-no-bet selection is among them). */
export function combinedProbabilityWithheld(legs: Array<{ selection: { market_id: string } }>): boolean {
  return legs.some(leg => leg.selection.market_id === 'draw_no_bet')
}

/** The product of the legs' prices, or null when any leg has none. Nothing is invented for a missing one. */
export function combinedPrice(legs: Array<{ odds: { value: number } | null }>): number | null {
  if (legs.length === 0) return null
  let product = 1
  for (const leg of legs) {
    if (!leg.odds) return null
    product *= leg.odds.value
  }
  return Math.round(product * 10000) / 10000
}
