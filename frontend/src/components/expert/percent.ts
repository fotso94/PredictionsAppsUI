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
 * Plain division, so `percentToUnit(55)` is bit-for-bit the double written as `0.55`. The pair
 * checks below add the SAME doubles in the SAME order the backend validator adds them, so a total
 * this module accepts is one the backend accepts, and one it rejects the backend rejects too.
 */
export function percentToUnit(percent: number): number {
  return percent / 100
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
