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

/*
 * ── DISPLAY, IN THE READER'S LOCALE ─────────────────────────────────────────────────────────
 *
 * Everything below writes a number for a person to read, and takes the BCP 47 locale it is
 * written in as an argument rather than reading it from src/i18n: this file stays free of any
 * runtime import, so its arithmetic above and these formatters can be exercised with no page and
 * no catalogue (e2e/mocked/expert-composer-localisation.spec.ts does exactly that). Callers pass
 * `currentLocale()`; the default is the English the editor always printed.
 *
 * ENGLISH IS BYTE-FOR-BYTE WHAT IT WAS. These replaced `toFixed` and `String`, which wrote "99%",
 * "101.01%", "Add 1." and "1500" for everybody. `Intl` writes exactly those in en-GB — measured
 * over every value the composer can produce, in that spec — and in French writes « 99 % »,
 * « 101,01 % », « 1,01 », with the locale's own no-break space before the sign. Grouping is off
 * throughout: the old output had none, so "2000" characters stays "2000" rather than "2,000".
 */

const numberFormats = new Map<string, Intl.NumberFormat>()

function numberFormat(locale: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = `${locale}|${JSON.stringify(options)}`
  let format = numberFormats.get(key)
  if (!format) {
    format = new Intl.NumberFormat(locale, { useGrouping: false, ...options })
    numberFormats.set(key, format)
  }
  return format
}

/** -0 written as 0. `Intl` prints a negative zero with its sign, where `String(-0)` never did. */
const unsigned = (value: number): number => (Object.is(value, -0) ? 0 : value)

/**
 * A number of percentage points as text, to the precision the API can actually keep: "1.01" in
 * English, « 1,01 » in French. No sign — this is the size of a gap ("Add 1.").
 *
 * Two decimals: one percentage point is 0.01 in the 0-1 units the API takes, and the columns
 * keep four decimal places of those units, so 0.01 of a percentage point is the smallest
 * difference that survives storage. Anything coarser would print "0" for a total that is
 * genuinely short, and tell an expert to change nothing. Trailing zeros are dropped.
 */
export function formatPercentPoints(points: number, locale = 'en-GB'): string {
  return numberFormat(locale, { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(unsigned(points))
}

/**
 * The same precision as a percentage, with the locale's sign: "99%" / « 99 % », "101.01%" /
 * « 101,01 % ». This is a pair's running total, which has to show the hundredths the API will
 * hold: a total of 99.99 must not round to "100%" beside a sentence saying it is short.
 */
export function formatPercentTotal(points: number, locale = 'en-GB'): string {
  return numberFormat(locale, { style: 'percent', minimumFractionDigits: 0, maximumFractionDigits: 2 })
    .format(unsigned(points) / 100)
}

/**
 * A percentage as the preview publishes it: one decimal at most, no trailing ".0", with the
 * locale's sign — "55.5%" / « 55,5 % », "20%" / « 20 % ».
 */
export function formatPercentShown(percent: number, locale = 'en-GB'): string {
  const rounded = unsigned(Math.round(percent * 10) / 10)
  const digits = Number.isInteger(rounded) ? 0 : 1
  return numberFormat(locale, { style: 'percent', minimumFractionDigits: digits, maximumFractionDigits: digits })
    .format(rounded / 100)
}

/** A whole number, never grouped: a character count reads "2000" in both languages. */
export function formatWholeNumber(value: number, locale = 'en-GB'): string {
  return numberFormat(locale, { maximumFractionDigits: 0 }).format(unsigned(value))
}

/** The locale's decimal separator: "." in English, "," in French. */
export function decimalSeparator(locale = 'en-GB'): string {
  return numberFormat(locale, { minimumFractionDigits: 1 }).formatToParts(1.5)
    .find(part => part.type === 'decimal')?.value ?? '.'
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

/**
 * A stored 0-1 probability as text for an input, written the way the reader types a decimal:
 * "55.5" in English, « 55,5 » in French. Blank when the source published nothing.
 *
 * The French form is the one `parsePercent` reads back to the same number, so reopening and
 * saving an edit untouched sends the stored value unchanged. An expert who would rather type a
 * point can: either separator is accepted.
 */
export function unitToPercentInput(unit: number | null | undefined, locale = 'en-GB'): PercentInput {
  if (typeof unit !== 'number' || !Number.isFinite(unit)) return ''
  const text = String(unitToPercent(unit))
  const separator = decimalSeparator(locale)
  return separator === '.' ? text : text.replace('.', separator)
}
