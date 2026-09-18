/**
 * What the expert is composing, and whether it can be published.
 *
 * Three rules shape this module.
 *
 *  1. NOTHING IS SUGGESTED. Every probability field starts empty and stays empty until the expert
 *     types in it. There is no prefilled 1X2 split, no prefilled conviction, and no value copied
 *     across from the model forecast shown beside the editor. The model's numbers are evidence the
 *     expert reads; they are never a starting value for the expert's own view.
 *
 *  2. MARKETS ARE OPT-IN. A market the expert did not tick is not sent at all, so the API stores
 *     null and every reader renders it as unavailable. It is never sent as 0, which would publish
 *     "this will not happen" in place of "no view was offered".
 *
 *  3. THE PAIR CHECKS MATCH THE BACKEND EXACTLY. `app/schemas/predictions.py` validates 1X2,
 *     both-teams-to-score, over/under 2.5 and over/under 3.5 with `0.99 <= total <= 1.01`, summing
 *     the unit values in a fixed order. The checks here add the same doubles in the same order, so
 *     the expert sees the problem in the form instead of as a 422 after pressing publish — and the
 *     form never accepts something the API would reject, nor rejects something it would accept.
 */

import {
  ExpertPredictionCreateRequest,
  ExpertPredictionResponse,
  ExpertPredictionUpdateRequest,
} from '@/types/expert'
import {
  formatPercentValue, inPercentRange, isBlankPercent, isMalformedPercent, parsePercent,
  percentToUnit, PercentInput, unitToPercentInput,
} from './percent'

/** The backend caps reasoning at 2000 characters (`max_length=2000`). */
export const REASONING_MAX = 2000

/**
 * Everything the composer holds, as typed.
 *
 * The `*Enabled` flags are the opt-in: false means the market is not part of this prediction and
 * its fields are not sent. Turning a market off does not erase what was typed in it, so a mis-click
 * does not destroy work — but nothing behind an unticked box ever reaches the API.
 */
export interface ComposerValues {
  homeWin: PercentInput
  draw: PercentInput
  awayWin: PercentInput
  /** The expert's own conviction in the 1X2 call. Optional, and never prefilled. */
  conviction: PercentInput
  bttsEnabled: boolean
  bttsYes: PercentInput
  bttsNo: PercentInput
  bttsConviction: PercentInput
  over25Enabled: boolean
  over25: PercentInput
  under25: PercentInput
  over35Enabled: boolean
  over35: PercentInput
  under35: PercentInput
  /** One conviction covers both goal lines, because the API stores exactly one. */
  totalsConviction: PercentInput
  reasoning: string
}

/** An untouched composer: every probability blank, every optional market off. */
export const EMPTY_COMPOSER: ComposerValues = {
  homeWin: '',
  draw: '',
  awayWin: '',
  conviction: '',
  bttsEnabled: false,
  bttsYes: '',
  bttsNo: '',
  bttsConviction: '',
  over25Enabled: false,
  over25: '',
  under25: '',
  over35Enabled: false,
  over35: '',
  under35: '',
  totalsConviction: '',
  reasoning: '',
}

/** The optional markets, in the order the editor shows them. */
export type OptionalMarketKey = 'btts' | 'over25' | 'over35'

export const OPTIONAL_MARKET_LABEL: Record<OptionalMarketKey, string> = {
  btts: 'Both teams to score',
  over25: 'Over / under 2.5 goals',
  over35: 'Over / under 3.5 goals',
}

/** Which flag switches each optional market on. */
export const OPTIONAL_MARKET_FLAG: Record<OptionalMarketKey, 'bttsEnabled' | 'over25Enabled' | 'over35Enabled'> = {
  btts: 'bttsEnabled',
  over25: 'over25Enabled',
  over35: 'over35Enabled',
}

/** Every key an error can be reported against: a real field, or a pair total. */
export type ComposerIssueKey =
  | 'matchId'
  | 'homeWin' | 'draw' | 'awayWin' | 'outcomeTotal' | 'conviction'
  | 'bttsYes' | 'bttsNo' | 'bttsTotal' | 'bttsConviction'
  | 'over25' | 'under25' | 'total25'
  | 'over35' | 'under35' | 'total35'
  | 'totalsConviction'
  | 'reasoning'

export interface PairState {
  /** The two percentages as typed, summed. Null while either side is blank or unreadable. */
  percent: number | null
  /** True only when both sides are present and the pair satisfies the backend's tolerance. */
  balanced: boolean
}

export interface ComposerValidation {
  errors: Partial<Record<ComposerIssueKey, string>>
  /** True when the composer can be published as it stands. */
  ready: boolean
  outcome: PairState
  btts: PairState
  totals25: PairState
  totals35: PairState
}

const NOT_A_NUMBER = 'Enter a number, for example 55.'
const OUT_OF_RANGE = 'Enter a percentage between 0 and 100.'

const UNKNOWN_PAIR: PairState = { percent: null, balanced: false }

/**
 * A single percentage field.
 *
 * Returns the message to show, or null. Blank is only an error when the field is required: an
 * optional conviction nobody filled in is a legitimate "no claim made", not a mistake.
 */
function checkPercentField(text: PercentInput, required: boolean, blankMessage: string): string | null {
  if (isBlankPercent(text)) return required ? blankMessage : null
  if (isMalformedPercent(text)) return NOT_A_NUMBER
  const value = parsePercent(text)
  if (value === null || !inPercentRange(value)) return OUT_OF_RANGE
  return null
}

/**
 * The complementary-pair check, in the backend's own arithmetic.
 *
 * `first` and `second` must be passed in the order the backend's validator adds them (yes then no,
 * over then under, home then draw then away) so the floating-point total is identical on both
 * sides and the two can never disagree about a borderline case.
 */
function checkPair(parts: Array<number | null>): PairState {
  if (parts.some(part => part === null)) return UNKNOWN_PAIR
  const values = parts as number[]
  const units = values.reduce((sum, value) => sum + percentToUnit(value), 0)
  return {
    percent: values.reduce((sum, value) => sum + value, 0),
    balanced: units >= 0.99 && units <= 1.01,
  }
}

function pairMessage(state: PairState, subject: string): string | null {
  if (state.percent === null) return null
  if (state.balanced) return null
  return `${subject} currently total ${formatPercentValue(state.percent)}%. They must total 100%.`
}

/**
 * Everything wrong with the composer right now, whether or not the expert has pressed anything.
 *
 * `matchId` being null is itself an issue: a prediction with no fixture cannot be published, and
 * saying so here means the publish button can be disabled for a stated reason rather than silently.
 */
export function validateComposer(values: ComposerValues, matchId: string | null): ComposerValidation {
  const errors: Partial<Record<ComposerIssueKey, string>> = {}

  if (!matchId) errors.matchId = 'Choose the fixture this prediction is for.'

  // ------------------------------------------------------------------ 1X2 (always published)
  const homeError = checkPercentField(values.homeWin, true, 'Enter a percentage for the home win.')
  const drawError = checkPercentField(values.draw, true, 'Enter a percentage for the draw.')
  const awayError = checkPercentField(values.awayWin, true, 'Enter a percentage for the away win.')
  if (homeError) errors.homeWin = homeError
  if (drawError) errors.draw = drawError
  if (awayError) errors.awayWin = awayError

  const outcome = homeError || drawError || awayError
    ? UNKNOWN_PAIR
    : checkPair([parsePercent(values.homeWin), parsePercent(values.draw), parsePercent(values.awayWin)])
  const outcomeMessage = pairMessage(outcome, 'Home, draw and away')
  if (outcomeMessage) errors.outcomeTotal = outcomeMessage

  const convictionError = checkPercentField(values.conviction, false, '')
  if (convictionError) errors.conviction = convictionError

  // ------------------------------------------------------------------ both teams to score (opt-in)
  let btts = UNKNOWN_PAIR
  if (values.bttsEnabled) {
    const yesError = checkPercentField(values.bttsYes, true, 'Enter a percentage, or untick this market.')
    const noError = checkPercentField(values.bttsNo, true, 'Enter a percentage, or untick this market.')
    if (yesError) errors.bttsYes = yesError
    if (noError) errors.bttsNo = noError
    btts = yesError || noError ? UNKNOWN_PAIR : checkPair([parsePercent(values.bttsYes), parsePercent(values.bttsNo)])
    const message = pairMessage(btts, 'Yes and no')
    if (message) errors.bttsTotal = message
    const confidence = checkPercentField(values.bttsConviction, false, '')
    if (confidence) errors.bttsConviction = confidence
  }

  // ------------------------------------------------------------------ goal lines (opt-in, each)
  let totals25 = UNKNOWN_PAIR
  if (values.over25Enabled) {
    const overError = checkPercentField(values.over25, true, 'Enter a percentage, or untick this line.')
    const underError = checkPercentField(values.under25, true, 'Enter a percentage, or untick this line.')
    if (overError) errors.over25 = overError
    if (underError) errors.under25 = underError
    totals25 = overError || underError ? UNKNOWN_PAIR : checkPair([parsePercent(values.over25), parsePercent(values.under25)])
    const message = pairMessage(totals25, 'Over 2.5 and under 2.5')
    if (message) errors.total25 = message
  }

  let totals35 = UNKNOWN_PAIR
  if (values.over35Enabled) {
    const overError = checkPercentField(values.over35, true, 'Enter a percentage, or untick this line.')
    const underError = checkPercentField(values.under35, true, 'Enter a percentage, or untick this line.')
    if (overError) errors.over35 = overError
    if (underError) errors.under35 = underError
    totals35 = overError || underError ? UNKNOWN_PAIR : checkPair([parsePercent(values.over35), parsePercent(values.under35)])
    const message = pairMessage(totals35, 'Over 3.5 and under 3.5')
    if (message) errors.total35 = message
  }

  if (values.over25Enabled || values.over35Enabled) {
    const confidence = checkPercentField(values.totalsConviction, false, '')
    if (confidence) errors.totalsConviction = confidence
  }

  // ------------------------------------------------------------------ words
  if (values.reasoning.length > REASONING_MAX) {
    errors.reasoning = `Shorten this to ${REASONING_MAX} characters — it is ${values.reasoning.length} now.`
  }

  return { errors, ready: Object.keys(errors).length === 0, outcome, btts, totals25, totals35 }
}

/** The 0-1 payload fields, with every market the expert did not tick simply absent. */
export interface PublishableValues {
  home_win_prob: number
  draw_prob: number
  away_win_prob: number
  confidence_score?: number
  btts_yes_prob?: number
  btts_no_prob?: number
  btts_confidence?: number
  total_goals_over_25_prob?: number
  total_goals_under_25_prob?: number
  total_goals_over_35_prob?: number
  total_goals_under_35_prob?: number
  total_goals_confidence?: number
  reasoning?: string
}

/** A field only if the expert actually typed a number in it. Never a zero standing in for blank. */
function unitOrAbsent(text: PercentInput): number | undefined {
  const percent = parsePercent(text)
  return percent === null ? undefined : percentToUnit(percent)
}

/**
 * The request body, or null when the composer is not publishable.
 *
 * Null rather than a best effort on purpose: a build step that quietly substituted 0 for a field it
 * could not read would publish a probability nobody chose.
 */
export function publishableValues(values: ComposerValues): PublishableValues | null {
  const home = unitOrAbsent(values.homeWin)
  const draw = unitOrAbsent(values.draw)
  const away = unitOrAbsent(values.awayWin)
  if (home === undefined || draw === undefined || away === undefined) return null

  const payload: PublishableValues = {
    home_win_prob: home,
    draw_prob: draw,
    away_win_prob: away,
  }

  const conviction = unitOrAbsent(values.conviction)
  if (conviction !== undefined) payload.confidence_score = conviction

  if (values.bttsEnabled) {
    const yes = unitOrAbsent(values.bttsYes)
    const no = unitOrAbsent(values.bttsNo)
    if (yes === undefined || no === undefined) return null
    payload.btts_yes_prob = yes
    payload.btts_no_prob = no
    const bttsConviction = unitOrAbsent(values.bttsConviction)
    if (bttsConviction !== undefined) payload.btts_confidence = bttsConviction
  }

  if (values.over25Enabled) {
    const over = unitOrAbsent(values.over25)
    const under = unitOrAbsent(values.under25)
    if (over === undefined || under === undefined) return null
    payload.total_goals_over_25_prob = over
    payload.total_goals_under_25_prob = under
  }

  if (values.over35Enabled) {
    const over = unitOrAbsent(values.over35)
    const under = unitOrAbsent(values.under35)
    if (over === undefined || under === undefined) return null
    payload.total_goals_over_35_prob = over
    payload.total_goals_under_35_prob = under
  }

  if (values.over25Enabled || values.over35Enabled) {
    const totalsConviction = unitOrAbsent(values.totalsConviction)
    if (totalsConviction !== undefined) payload.total_goals_confidence = totalsConviction
  }

  const reasoning = values.reasoning.trim()
  if (reasoning) payload.reasoning = reasoning

  return payload
}

/** The create body for one fixture, or null when the composer is not publishable. */
export function buildCreateRequest(values: ComposerValues, matchId: string): ExpertPredictionCreateRequest | null {
  const payload = publishableValues(values)
  if (!payload || !matchId) return null
  return { match_id: matchId, ...payload }
}

/** The update body for an existing prediction, or null when the composer is not publishable. */
export function buildUpdateRequest(values: ComposerValues): ExpertPredictionUpdateRequest | null {
  const payload = publishableValues(values)
  if (!payload) return null
  return payload
}

/**
 * Reopen a published prediction in the composer.
 *
 * A market is ticked only when the API actually returned a number for it, so a prediction that
 * published no goal lines reopens with those boxes unticked and empty rather than at zero.
 */
export function composerFromPrediction(prediction: ExpertPredictionResponse): ComposerValues {
  const published = (value: number | null | undefined): boolean =>
    typeof value === 'number' && Number.isFinite(value)

  return {
    homeWin: unitToPercentInput(prediction.home_win_prob),
    draw: unitToPercentInput(prediction.draw_prob),
    awayWin: unitToPercentInput(prediction.away_win_prob),
    // A stored 0 confidence is how "none was supplied" reaches us from the numeric column, so it
    // reopens as blank rather than as a 0% conviction the expert never claimed.
    conviction: published(prediction.confidence_score) && prediction.confidence_score > 0
      ? unitToPercentInput(prediction.confidence_score)
      : '',
    bttsEnabled: published(prediction.btts_yes_prob) || published(prediction.btts_no_prob),
    bttsYes: unitToPercentInput(prediction.btts_yes_prob),
    bttsNo: unitToPercentInput(prediction.btts_no_prob),
    bttsConviction: unitToPercentInput(prediction.btts_confidence),
    over25Enabled: published(prediction.total_goals_over_25_prob) || published(prediction.total_goals_under_25_prob),
    over25: unitToPercentInput(prediction.total_goals_over_25_prob),
    under25: unitToPercentInput(prediction.total_goals_under_25_prob),
    over35Enabled: published(prediction.total_goals_over_35_prob) || published(prediction.total_goals_under_35_prob),
    over35: unitToPercentInput(prediction.total_goals_over_35_prob),
    under35: unitToPercentInput(prediction.total_goals_under_35_prob),
    totalsConviction: unitToPercentInput(prediction.total_goals_confidence),
    reasoning: prediction.reasoning ?? '',
  }
}

/** Which markets this prediction already carries, so the editor can say they cannot be removed. */
export function publishedMarkets(prediction: ExpertPredictionResponse): Set<OptionalMarketKey> {
  const values = composerFromPrediction(prediction)
  const present = new Set<OptionalMarketKey>()
  if (values.bttsEnabled) present.add('btts')
  if (values.over25Enabled) present.add('over25')
  if (values.over35Enabled) present.add('over35')
  return present
}

/** True when the expert has typed nothing at all — used to decide whether a draft is worth keeping. */
export function composerIsEmpty(values: ComposerValues): boolean {
  return !values.homeWin.trim() && !values.draw.trim() && !values.awayWin.trim()
    && !values.conviction.trim() && !values.reasoning.trim()
    && !values.bttsEnabled && !values.over25Enabled && !values.over35Enabled
}
