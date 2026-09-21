/**
 * Percent <-> unit conversion for the expert workspace.
 *
 * The API stores and returns 0-1 probabilities. A human thinking "55%" should be able to type 55,
 * so every field the expert touches is a PERCENTAGE and the conversion happens here, once, on the
 * way to the request: 55 -> 0.55.
 *
 * Every value is held as RAW TEXT rather than as a number. That is deliberate: a number field needs
 * a value, and the only honest value for "the expert has not decided yet" is the empty string. The
 * old composer solved that by shipping 0.33 / 0.33 / 0.34 already in the boxes, which anchored the
 * expert's judgement and made an accidental submission of three numbers nobody chose a single
 * click away. Nothing in this file proposes, completes or rounds a probability towards anything.
 */

/** Raw text exactly as typed. `''` means nothing has been entered — never a zero, never a default. */
export type PercentInput = string

/** True when the field is empty. Empty is a distinct state from "0", which is a real forecast. */
export function isBlankPercent(text: PercentInput): boolean {
  return text.trim() === ''
}

/**
 * The number the expert typed, or null when the field is blank or unreadable.
 *
 * A comma is accepted as a decimal separator because much of Europe types one; nothing else is
 * coerced, so "abc" and "" stay distinguishable from 0 via `isBlankPercent`.
 */
export function parsePercent(text: PercentInput): number | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const value = Number(trimmed.replace(',', '.'))
  return Number.isFinite(value) ? value : null
}

/** Text was entered but is not a number. Different from blank, and reported differently. */
export function isMalformedPercent(text: PercentInput): boolean {
  return !isBlankPercent(text) && parsePercent(text) === null
}

/** True when the value is a percentage the API will accept (it validates 0 <= p <= 1). */
export function inPercentRange(percent: number): boolean {
  return percent >= 0 && percent <= 100
}

/**
 * 55 -> 0.55.
 *
 * Plain division, so `percentToUnit(55)` is bit-for-bit the double written as `0.55` — the same
 * double the request body carries and the backend parses back.
 */
export function percentToUnit(percent: number): number {
  return percent / 100
}

/**
 * A 0-1 probability as the API will STORE it, counted in ten-thousandths.
 *
 * `predictions.predictions` holds these as NUMERIC(5, 4): Postgres rounds every value to four
 * decimal places, half away from zero, and its CHECK constraints then add the ROUNDED values.
 * The request validators do the same (`as_stored` in app/schemas/predictions.py). So a form that
 * adds the raw doubles is measuring numbers nothing downstream will ever hold, and will sooner
 * or later call a pair balanced that the API refuses: 0.98995 and 0.02005 add to exactly 1.01 as
 * doubles and to 1.0101 as the two values that would be stored.
 *
 * Whole ten-thousandths rather than a fraction, because integers add exactly: three of them can
 * be summed and compared with 10000 without a rounding error of their own.
 *
 * THE ROUNDING IS DONE ON THE DECIMAL TEXT, not by multiplying and not with `toFixed`. Both of
 * those carry binary floating-point error into the decision: `0.02005 * 10000` is
 * 200.49999999999997, which rounds DOWN to 0.0200 where the column rounds UP to 0.0201, and
 * `(0.98995).toFixed(4)` is "0.9899" where the column gives 0.9900 — `toFixed` rounds the
 * double's exact binary value, which sits just under the decimal midpoint. `String(unit)` is
 * the shortest decimal that reads back as this double: the same text `JSON.stringify` puts on
 * the wire, and the same digits Python's `str()` recovers from it, so both sides round the same
 * number.
 */
export function storedTenThousandths(unit: number): number {
  if (!Number.isFinite(unit)) return 0
  const parsed = /^(-?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/.exec(String(unit))
  if (!parsed) return 0
  const [, sign, whole = '', fraction = '', exponent = '0'] = parsed
  const digits = `${whole}${fraction}` || '0'
  // The value is `digits` scaled by 10**shift once it is expressed in ten-thousandths.
  const shift = Number(exponent) - fraction.length + 4
  const magnitude = shift >= 0
    ? Number(`${digits}${'0'.repeat(shift)}`)
    : roundOffLastDigits(digits, -shift)
  return sign === '-' ? -magnitude : magnitude
}

/** `digits` with its last `count` digits dropped, rounded half away from zero on the first. */
function roundOffLastDigits(digits: string, count: number): number {
  const padded = digits.padStart(count + 1, '0')
  const kept = Number(padded.slice(0, padded.length - count))
  return padded[padded.length - count] >= '5' ? kept + 1 : kept
}

/**
 * A number of percentage points as text, to the precision the API can actually keep.
 *
 * Two decimals: one percentage point is 0.01 in the 0-1 units the API takes, and the columns
 * keep four decimal places of those units, so 0.01 of a percentage point is the smallest
 * difference that survives storage. Anything coarser would print "0" for a total that is
 * genuinely short, and tell an expert to change nothing.
 */
export function formatPercentPoints(points: number): string {
  const text = points.toFixed(2)
  return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text
}

/**
 * 0.55 -> 55.
 *
 * Rounded to four decimals because `0.55 * 100` is 55.00000000000001 in binary floating point, and
 * an edit form that reopened a stored 55% as "55.00000000000001" would invite the expert to
 * "correct" a number they never typed.
 */
export function unitToPercent(unit: number): number {
  return Math.round(unit * 1e6) / 1e4
}

/** A stored 0-1 probability as text for an input. Blank when the source published nothing. */
export function unitToPercentInput(unit: number | null | undefined): PercentInput {
  if (typeof unit !== 'number' || !Number.isFinite(unit)) return ''
  return String(unitToPercent(unit))
}

/** A percentage for display: one decimal at most, and no trailing `.0`. */
export function formatPercentValue(percent: number): string {
  const rounded = Math.round(percent * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}
