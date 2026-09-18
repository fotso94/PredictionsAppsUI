/**
 * Probability formatting for values a source may simply never have published.
 *
 * Every market except 1X2 is optional, and the API returns null for one an expert left blank or a
 * provider did not supply. `(value * 100).toFixed(1)` turns null into "0.0%" and undefined into
 * "NaN%" — both of which read as a real forecast. These helpers say so instead, and never invent,
 * derive or complete a number the source did not publish.
 *
 * NOTE: this is presentation-layer glue that would sit better in src/utils, which this package does
 * not own. It is kept under components/ui so no data-layer file is touched; see the package report.
 */

/** Wording for a market the source did not publish. Never "0%". */
export const UNAVAILABLE_TEXT = 'Unavailable'
/** Wording for an optional field an author chose to leave blank. */
export const NOT_SET_TEXT = 'not set'

/** True only for a real, finite number — null, undefined and NaN all mean "not published". */
export function isPublished(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/**
 * A 0-1 probability as a percentage string.
 * Returns `fallback` (never "0.0%") when the source published no value.
 */
export function formatUnitProbability(
  value: number | null | undefined,
  digits = 1,
  fallback: string = NOT_SET_TEXT,
): string {
  return isPublished(value) ? `${(value * 100).toFixed(digits)}%` : fallback
}

/**
 * A 0-100 percentage as a rounded string.
 * Returns `fallback` (never "0%") when the source published no value.
 */
export function formatPercent(
  value: number | null | undefined,
  fallback: string = UNAVAILABLE_TEXT,
): string {
  return isPublished(value) ? `${Math.round(value)}%` : fallback
}

/** One side of a two-way market (e.g. BTTS yes/no, over/under 2.5). */
export interface MarketSide {
  label: string
  value: number | null | undefined
}

/** A side of a two-way market whose probability the source actually published. */
export interface PublishedSide {
  label: string
  value: number
}

/** One labelled half of a market, or null when the source published no value for it. */
export function publishedSide(label: string, value: number | null | undefined): PublishedSide | null {
  return isPublished(value) ? { label, value } : null
}

/**
 * Split a two-way market into the halves the source published and the leading one.
 *
 * `leader` is null unless BOTH halves were published: one probability on its own does not establish
 * a favourite, and treating it as one would mean inferring the missing half as 100 - value.
 */
export function marketLead(...sides: MarketSide[]): { known: PublishedSide[]; leader: PublishedSide | null } {
  const known: PublishedSide[] = sides
    .filter((side): side is PublishedSide => isPublished(side.value))
    .map(side => ({ label: side.label, value: side.value }))
  if (known.length < 2) return { known, leader: null }
  const leader = known.reduce((best, side) => (side.value > best.value ? side : best))
  return { known, leader }
}
