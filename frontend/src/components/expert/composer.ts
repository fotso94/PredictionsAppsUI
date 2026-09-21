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
 *  2. MARKETS ARE OPT-IN, AND A CREATE SAYS SO BY SILENCE WHILE AN EDIT SAYS SO OUT LOUD. A
 *     market the expert did not tick is never sent as 0, which would publish "this will not
 *     happen" in place of "no view was offered". On a create there is nothing stored yet, so
 *     leaving the keys out is the whole statement and the API stores null. On an edit there IS
 *     something stored, and the API reads an absent key as "leave it alone" — so the edit body
 *     built here states every optional field, with `null` where the expert withdrew one. See
 *     `buildUpdateBody`.
 *
 *  3. THE TOTALS ARE MEASURED THE WAY THE API MEASURES THEM, WHICH IS NOT THE WAY THEY WERE
 *     TYPED. Two rules, and they differ because the database's do:
 *
 *       - the three match-result probabilities must total EXACTLY 100%. The column constraint
 *         `ck_predictions_prob_sum` is an equality with no tolerance in it, so 33 / 33 / 33 and
 *         34 / 33 / 34 are rows the table cannot hold and the API refuses on the request;
 *       - each two-way market (both teams to score, over/under 2.5, over/under 3.5) must land
 *         within a percentage point of 100, which is the window the API allows a pair —
 *         `ck_predictions_btts_prob_sum` for the BTTS columns, and the request validator alone
 *         for the goal lines, which carry no constraint of their own.
 *
 *     Both are measured on the values the API will STORE — four decimal places of a 0-1
 *     probability — and not on the doubles as typed, because that is where
 *     `app/schemas/predictions.py` measures them. See `storedTenThousandths` in ./percent.
 *
 *     The point of reproducing the rules here is that the expert meets an unbalanced total in
 *     the form, while they are typing, instead of as a 422 after pressing publish. It is a claim
 *     about the totals alone: the backend applies rules this module does not reproduce, and a
 *     body this module builds can still be refused.
 */

import {
  ExpertPredictionCreateRequest,
  ExpertPredictionResponse,
  ExpertPredictionUpdateRequest,
} from '@/types/expert'
import {
  formatPercentPoints, inPercentRange, isBlankPercent, isMalformedPercent, parsePercent,
  percentToUnit, PercentInput, storedTenThousandths, unitToPercentInput,
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
  /**
   * The percentages summed as the API will store them. Null while a side is blank or unreadable.
   *
   * Not always what the eye adds up: 33.335 is stored as 33.34, so what is shown here is what
   * the API will actually be holding.
   */
  percent: number | null
  /** True only when every side is present and the total is one the API accepts. */
  balanced: boolean
  /**
   * Percentage points still to be found: positive to add, negative to take away, 0 on exactly
   * 100. Null while the total is unknown. This is what turns "that is wrong" into "add 1".
   */
  gap: number | null
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

const UNKNOWN_PAIR: PairState = { percent: null, balanced: false, gap: null }

/** 1.0000 as the probability columns count it, in ten-thousandths. */
const WHOLE = 10_000

/**
 * How far from 1.0000 each kind of market may land, in the same ten-thousandths.
 *
 * `EXACT` is `ck_predictions_prob_sum`, an equality: the three match-result probabilities are a
 * distribution, every stored row sums to exactly 1, and readers render each one as a percentage
 * without rescaling — so 34 / 33 / 34 is not a row the table will take.
 *
 * `TWO_WAY` is the window `ck_predictions_btts_prob_sum` allows, one percentage point either
 * side. The over/under pairs carry no constraint of their own and the request holds them to the
 * same window. Matching the API rather than rounding it off in either direction is the point:
 * a form stricter than the API blocks a body the API would take, and a looser one sends a body
 * the API refuses.
 */
const EXACT = 0
const TWO_WAY = 100

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
 * The total of a market's sides, in the backend's own arithmetic.
 *
 * Every percentage is converted to the unit value that will be sent and then rounded to what the
 * column will hold, and the ten-thousandths are added as integers. Adding the doubles instead
 * agrees with the API wherever the values fit the column and parts company where they do not:
 * 98.995 and 2.005 are sent as 0.98995 and 0.02005, which total exactly 1.01 as doubles — inside
 * the window — and 1.0101 as the two values that would be stored, which the API refuses.
 *
 * `slack` is how far from 100% this market may land, in the same ten-thousandths.
 */
function checkPair(parts: Array<number | null>, slack: number): PairState {
  if (parts.some(part => part === null)) return UNKNOWN_PAIR
  const stored = (parts as number[]).reduce(
    (sum, value) => sum + storedTenThousandths(percentToUnit(value)), 0)
  return {
    percent: stored / 100,
    balanced: Math.abs(stored - WHOLE) <= slack,
    gap: (WHOLE - stored) / 100,
  }
}

/**
 * What the expert has to do about an unbalanced total, rather than only that it is wrong.
 *
 * A form that refuses 33 / 33 / 33 and stops there leaves them to work out that one point is
 * missing and which box to put it in. The size is stated; which box is theirs to choose.
 */
export function pairAdjustment(gap: number | null): string | null {
  if (gap === null || gap === 0) return null
  return gap > 0
    ? `Add ${formatPercentPoints(gap)}.`
    : `Remove ${formatPercentPoints(-gap)}.`
}

function pairMessage(state: PairState, subject: string): string | null {
  if (state.percent === null || state.balanced) return null
  const adjustment = pairAdjustment(state.gap)
  return `${subject} currently total ${formatPercentPoints(state.percent)}%. They must total `
    + `100%.${adjustment ? ` ${adjustment}` : ''}`
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
    : checkPair([parsePercent(values.homeWin), parsePercent(values.draw), parsePercent(values.awayWin)], EXACT)
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
    btts = yesError || noError ? UNKNOWN_PAIR : checkPair([parsePercent(values.bttsYes), parsePercent(values.bttsNo)], TWO_WAY)
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
    totals25 = overError || underError ? UNKNOWN_PAIR : checkPair([parsePercent(values.over25), parsePercent(values.under25)], TWO_WAY)
    const message = pairMessage(totals25, 'Over 2.5 and under 2.5')
    if (message) errors.total25 = message
  }

  let totals35 = UNKNOWN_PAIR
  if (values.over35Enabled) {
    const overError = checkPercentField(values.over35, true, 'Enter a percentage, or untick this line.')
    const underError = checkPercentField(values.under35, true, 'Enter a percentage, or untick this line.')
    if (overError) errors.over35 = overError
    if (underError) errors.under35 = underError
    totals35 = overError || underError ? UNKNOWN_PAIR : checkPair([parsePercent(values.over35), parsePercent(values.under35)], TWO_WAY)
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

/**
 * Every field an edit can carry, with `null` for the ones the expert withdrew.
 *
 * This is the shape `buildUpdateRequest` actually puts on the wire, and it is deliberately not
 * `Partial`: an edit body is a COMPLETE statement of the prediction, because the composer it was
 * built from was seeded by `composerFromPrediction` and holds the whole of one.
 *
 * Why it has to be complete. `PUT /api/v1/expert/predictions/{id}` distinguishes a key that is
 * absent from a key carrying null (app/services/expert_prediction.py, `model_fields_set`): absent
 * leaves the stored value alone, null withdraws it. The create rules cannot withdraw anything at
 * all, because `unitOrAbsent` returns undefined for a cleared box and `JSON.stringify` drops the
 * key entirely — so an edit built with them silently leaves every emptied box as it was. An edit
 * body must therefore name every field it means, null included.
 *
 * Pairs move together, which is the same rule the backend enforces (COMPLEMENTARY_PAIRS in
 * app/schemas/predictions.py): an unticked market sends BOTH of its sides as null, so the market
 * is withdrawn whole, and a ticked one sends two numbers or the composer is not publishable at
 * all. There is no body this builder can produce that names one side of a pair and not the other.
 * A market's conviction goes with it (`btts_confidence` with the BTTS pair,
 * `total_goals_confidence` with the goal lines), because the editor only shows those fields while
 * their market is ticked, and a conviction in a market this prediction does not publish is a
 * figure about nothing — which the backend now refuses outright (MARKET_CONVICTIONS in
 * app/schemas/predictions.py). Clearing a conviction on a market that stays published is a
 * different thing and a legitimate one: `PredictionMarketsEditor` locks a published market's
 * toggle, not its conviction box, so an expert can withdraw the figure while the market stands,
 * and this body sends that as `null` like any other withdrawal.
 *
 * `key_factors` is the one thing deliberately left out: the composer has no field for it, so an
 * edit here has nothing to say about it and the stored value must stand.
 */
export interface ExpertPredictionUpdateBody {
  home_win_prob: number
  draw_prob: number
  away_win_prob: number
  confidence_score: number | null
  btts_yes_prob: number | null
  btts_no_prob: number | null
  btts_confidence: number | null
  total_goals_over_25_prob: number | null
  total_goals_under_25_prob: number | null
  total_goals_over_35_prob: number | null
  total_goals_under_35_prob: number | null
  total_goals_confidence: number | null
  reasoning: string | null
}

/** The update body for an existing prediction, or null when the composer is not publishable. */
export function buildUpdateBody(values: ComposerValues): ExpertPredictionUpdateBody | null {
  const payload = publishableValues(values)
  if (!payload) return null
  // `?? null` and not `|| null`: a conviction of 0 is a claim the expert made and has to survive.
  return {
    home_win_prob: payload.home_win_prob,
    draw_prob: payload.draw_prob,
    away_win_prob: payload.away_win_prob,
    confidence_score: payload.confidence_score ?? null,
    btts_yes_prob: payload.btts_yes_prob ?? null,
    btts_no_prob: payload.btts_no_prob ?? null,
    btts_confidence: payload.btts_confidence ?? null,
    total_goals_over_25_prob: payload.total_goals_over_25_prob ?? null,
    total_goals_under_25_prob: payload.total_goals_under_25_prob ?? null,
    total_goals_over_35_prob: payload.total_goals_over_35_prob ?? null,
    total_goals_under_35_prob: payload.total_goals_under_35_prob ?? null,
    total_goals_confidence: payload.total_goals_confidence ?? null,
    reasoning: payload.reasoning ?? null,
  }
}

/**
 * The same body, typed as the service's parameter expects.
 *
 * `ExpertPredictionUpdateRequest` in src/types/expert.ts still declares every optional field as
 * `number | undefined`, which no longer describes what this endpoint accepts or what is sent.
 * Widening it belongs with that file; until then the honest shape is `ExpertPredictionUpdateBody`
 * above and the mismatch is absorbed by exactly one cast, here, rather than by building a body
 * that the type happens to fit.
 */
export function buildUpdateRequest(values: ComposerValues): ExpertPredictionUpdateRequest | null {
  const body = buildUpdateBody(values)
  return body === null ? null : (body as unknown as ExpertPredictionUpdateRequest)
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
    /*
     * Null is how "none was supplied" reaches us now, so a stored zero is a real zero again.
     *
     * This used to read `published(...) && confidence_score > 0`, because the column could not
     * hold null and the service wrote 0.0 for a blank — so zero was the only signal available.
     * With the column nullable that clause inverted the defect: an expert who deliberately rated
     * their conviction at 0% reopened the editor to an empty field, and the value they had chosen
     * was gone from in front of them.
     */
    conviction: published(prediction.confidence_score)
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
