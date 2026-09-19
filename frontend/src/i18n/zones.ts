/**
 * Time, in the zone the reader chose — and nothing about that zone inferred from anything else.
 *
 * WHY THE DEVICE'S ZONE IS NOT GOOD ENOUGH. It is a good default and a bad answer. A phone bought
 * abroad, a laptop that never had its clock touched, a browser in a container, a reader in Douala
 * following a friend's fixtures on a machine still set to Europe/Paris: in every one of those the
 * device is confidently wrong, and the failure is invisible, because a kickoff time is plausible
 * at any hour. So the zone is a preference the reader sets, the device's zone is what it starts
 * at, and the interface says which zone the times on screen are in.
 *
 * WHAT THE ZONE IS NOT ALLOWED TO IMPLY. It is not a country and it is not a language. Africa/
 * Douala does not mean French, Europe/London does not mean English, and a French reader in Lagos
 * is not unusual. The three preferences are stored separately and read separately (see
 * src/i18n/index.ts); nothing in this file reads the language and nothing in the language module
 * reads this.
 *
 * THE DAY BOUNDARY FOLLOWS THE ZONE, WHICH IS THE WHOLE POINT. "Today" is a calendar day, and a
 * calendar day is 23, 24 or 25 hours long depending on where you are and what the clocks did that
 * night. Every function here derives that from the IANA database through `Intl`, never from a
 * fixed offset:
 *
 *   - `isoDateInZone` buckets an instant into the zone's calendar day.
 *   - `dayBoundaryOffsets` returns the UTC offset at local midnight AND at the next local
 *     midnight, which are one hour apart on a transition day. The backend's `/matches` endpoint
 *     takes both (`tz_offset`, `tz_offset_end`) and uses them as the half-open window
 *     [local midnight, next local midnight). Passing one offset twice loses an hour of football
 *     at one end of the day, twice a year, in every DST zone — the defect e2e/mocked/timezone.
 *     spec.ts pins, and which this module has to keep pinned now that it computes the numbers.
 *
 * ROUNDING. Offsets are reported in whole minutes. Every zone in current use is a whole number of
 * minutes from UTC; a handful of pre-1900 local mean times are not, and this rounds them, which
 * is correct for fixtures and wrong for nothing anybody will schedule.
 */

/** IANA zone id, e.g. `Africa/Douala`. */
export type ZoneId = string

/** Whatever the device says, which is where a reader who has never chosen starts. */
export function deviceZone(): ZoneId {
  try {
    const zone = new Intl.DateTimeFormat().resolvedOptions().timeZone
    return zone && isUsableZone(zone) ? zone : 'UTC'
  } catch {
    return 'UTC'
  }
}

/** True when this engine can actually format in `zone`. A stored zone may outlive a browser. */
export function isUsableZone(zone: string): boolean {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: zone }).format(new Date())
    return true
  } catch {
    return false
  }
}

// --------------------------------------------------------------------------- the arithmetic

const partsFormats = new Map<ZoneId, Intl.DateTimeFormat>()

function partsFormat(zone: ZoneId): Intl.DateTimeFormat {
  let format = partsFormats.get(zone)
  if (!format) {
    format = new Intl.DateTimeFormat('en-US', {
      timeZone: zone,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    partsFormats.set(zone, format)
  }
  return format
}

export interface ZonedParts {
  year: number
  /** 1-12, not the 0-11 a Date uses. */
  month: number
  day: number
  hour: number
  minute: number
  second: number
}

/** The wall-clock reading in `zone` at `instant`. */
export function zonedParts(zone: ZoneId, instant: Date): ZonedParts {
  const parts = partsFormat(zone).formatToParts(instant)
  const read = (type: Intl.DateTimeFormatPartTypes): number => {
    const found = parts.find(part => part.type === type)
    return found ? Number(found.value) : 0
  }
  // `hourCycle: 'h23'` should never produce 24, but some engines have; `% 24` costs nothing and
  // turns a wrong hour into the right one rather than into a date a day out.
  return {
    year: read('year'),
    month: read('month'),
    day: read('day'),
    hour: read('hour') % 24,
    minute: read('minute'),
    second: read('second'),
  }
}

/** The zone's offset from UTC at `instant`, in minutes east (Africa/Douala is +60). */
export function offsetMinutesAt(zone: ZoneId, instant: Date): number {
  const parts = zonedParts(zone, instant)
  const asUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second)
  // The instant truncated to whole seconds, because `Date.UTC` above carries no milliseconds.
  const truncated = Math.floor(instant.getTime() / 1000) * 1000
  return Math.round((asUtc - truncated) / 60000)
}

/**
 * The instant at which the clocks in `zone` read this wall time.
 *
 * Two passes, because the offset needed to convert the wall time is the offset AT the resulting
 * instant, which is not known until the conversion is done. One pass is wrong for a few hours
 * either side of every transition. On a spring-forward gap — a local time that does not exist —
 * the second pass does not converge and the first answer stands, which lands on a real instant an
 * hour either side of the gap rather than throwing. Nothing here is ever asked for a time in a
 * gap: `startOfDay` is asked for midnight, and no IANA zone in current use skips midnight.
 */
export function instantAtWallTime(
  zone: ZoneId,
  year: number,
  month: number,
  day: number,
  hour = 0,
  minute = 0,
): Date {
  const naive = Date.UTC(year, month - 1, day, hour, minute)
  const first = offsetMinutesAt(zone, new Date(naive))
  const candidate = naive - first * 60000
  const second = offsetMinutesAt(zone, new Date(candidate))
  return new Date(second === first ? candidate : naive - second * 60000)
}

// --------------------------------------------------------------------------- calendar days

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/

/** Split `YYYY-MM-DD`, or null when it is not one. */
export function readIsoDate(iso: string): { year: number; month: number; day: number } | null {
  const match = ISO_DATE.exec(iso)
  if (!match) return null
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) }
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

/** The calendar date `instant` falls on, in `zone`. */
export function isoDateInZone(zone: ZoneId, instant: Date = new Date()): string {
  const parts = zonedParts(zone, instant)
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}`
}

/**
 * Calendar arithmetic on a date string, with no zone involved.
 *
 * Adding a day to a calendar date is a fact about the calendar, not about any clock: the day after
 * 2026-10-25 is 2026-10-26 in every zone on earth, including the one where that day is 25 hours
 * long. Doing it on the string rather than on a `Date` is what keeps a daylight-saving transition
 * from turning "tomorrow" into "today at 23:00".
 */
export function addDays(iso: string, days: number): string {
  const parts = readIsoDate(iso)
  if (!parts) return iso
  const moved = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + days))
  return `${moved.getUTCFullYear()}-${pad(moved.getUTCMonth() + 1)}-${pad(moved.getUTCDate())}`
}

/** The instant at which the calendar day `iso` begins in `zone`. */
export function startOfDay(zone: ZoneId, iso: string): Date {
  const parts = readIsoDate(iso)
  if (!parts) return new Date(NaN)
  return instantAtWallTime(zone, parts.year, parts.month, parts.day, 0, 0)
}

/**
 * Midday on `iso` in `zone`, as an anchor for formatting a bare date.
 *
 * Every "format this calendar date" path needs an instant, and midday is the one that cannot land
 * on the wrong side of a transition however the clocks move — which `new Date(`${iso}T12:00:00`)`
 * could, because that parses in the DEVICE's zone and the reader may have chosen another.
 */
export function noonOn(zone: ZoneId, iso: string): Date {
  const parts = readIsoDate(iso)
  if (!parts) return new Date(NaN)
  return instantAtWallTime(zone, parts.year, parts.month, parts.day, 12, 0)
}

/**
 * The UTC offsets bounding one calendar day in `zone`, in minutes east — the backend's
 * `tz_offset` and `tz_offset_end`.
 *
 * Taken at local midnight and at the NEXT local midnight, which differ by an hour on a transition
 * day. New York on 1 November 2026 runs 04:00Z to 05:00Z the next day: start -240, end -300.
 */
export function dayBoundaryOffsets(zone: ZoneId, iso: string): { start: number; end: number } {
  const start = startOfDay(zone, iso)
  if (Number.isNaN(start.getTime())) {
    const now = new Date()
    return { start: offsetMinutesAt(zone, now), end: offsetMinutesAt(zone, now) }
  }
  const end = startOfDay(zone, addDays(iso, 1))
  return {
    start: offsetMinutesAt(zone, start),
    end: offsetMinutesAt(zone, Number.isNaN(end.getTime()) ? start : end),
  }
}

// --------------------------------------------------------------------------- naming a zone

/** "UTC+01:00" — the offset as a reader recognises it, for the zone at a given moment. */
export function offsetLabel(zone: ZoneId, instant: Date = new Date()): string {
  const minutes = offsetMinutesAt(zone, instant)
  const sign = minutes < 0 ? '-' : '+'
  const absolute = Math.abs(minutes)
  return `UTC${sign}${pad(Math.floor(absolute / 60))}:${pad(absolute % 60)}`
}

/**
 * The zone's own short name at this moment — "WAT", "GMT+1", "EDT".
 *
 * From `Intl`, so it is the zone's real abbreviation for the real date and it changes across a
 * daylight-saving transition, which is exactly the fact a reader needs on the day the clocks
 * move. Returns null when the engine offers nothing better than the offset, rather than dressing
 * the offset up as an abbreviation.
 */
export function zoneAbbreviation(
  locale: string,
  zone: ZoneId,
  instant: Date = new Date(),
): string | null {
  try {
    const parts = new Intl.DateTimeFormat(locale, { timeZone: zone, timeZoneName: 'short' })
      .formatToParts(instant)
    const name = parts.find(part => part.type === 'timeZoneName')?.value ?? null
    return name && !/^(GMT|UTC)[+-]?\d*(:\d+)?$/.test(name) ? name : null
  } catch {
    return null
  }
}

/**
 * The zones offered in the picker.
 *
 * NOT A WORLD LIST, and deliberately so: a 400-entry `Intl.supportedValuesOf('timeZone')` dropdown
 * is a worse control than a short one on the phone this product is for, and it is a much worse one
 * for a reader who does not already know which IANA name their city has. So this is the set this
 * audience plausibly reads from, plus the ones the fixtures themselves are played in — and the
 * device's own zone is always offered first whether or not it is on this list, so nobody is ever
 * unable to pick where they actually are.
 *
 * Africa/Douala is first because it is the market this work is for. Zones that observe daylight
 * saving are marked, because a reader in one of them is the one who needs to know that the offset
 * beside it is only today's.
 */
export interface ZoneOption {
  id: ZoneId
  /** The city, as the picker lists it. Not translated: a place name is a name. */
  city: string
  /** True where the clocks change during the year. */
  observesDaylightSaving: boolean
}

export const OFFERED_ZONES: readonly ZoneOption[] = Object.freeze([
  { id: 'Africa/Douala', city: 'Douala, Yaoundé', observesDaylightSaving: false },
  { id: 'Africa/Lagos', city: 'Lagos, Abuja', observesDaylightSaving: false },
  { id: 'Africa/Abidjan', city: 'Abidjan, Accra', observesDaylightSaving: false },
  { id: 'Africa/Casablanca', city: 'Casablanca', observesDaylightSaving: true },
  { id: 'Africa/Kinshasa', city: 'Kinshasa', observesDaylightSaving: false },
  { id: 'Africa/Nairobi', city: 'Nairobi', observesDaylightSaving: false },
  { id: 'Africa/Johannesburg', city: 'Johannesburg', observesDaylightSaving: false },
  { id: 'Europe/London', city: 'London', observesDaylightSaving: true },
  { id: 'Europe/Paris', city: 'Paris, Brussels', observesDaylightSaving: true },
  { id: 'Europe/Madrid', city: 'Madrid', observesDaylightSaving: true },
  { id: 'Europe/Berlin', city: 'Berlin', observesDaylightSaving: true },
  { id: 'Europe/Rome', city: 'Rome', observesDaylightSaving: true },
  { id: 'Europe/Lisbon', city: 'Lisbon', observesDaylightSaving: true },
  { id: 'America/New_York', city: 'New York, Toronto', observesDaylightSaving: true },
  { id: 'America/Sao_Paulo', city: 'São Paulo', observesDaylightSaving: false },
  { id: 'Asia/Dubai', city: 'Dubai', observesDaylightSaving: false },
  { id: 'UTC', city: 'UTC', observesDaylightSaving: false },
])

/** The offered entry for a zone, when it has one. */
export function zoneOption(zone: ZoneId): ZoneOption | null {
  return OFFERED_ZONES.find(option => option.id === zone) ?? null
}

/** `Africa/Douala` as "Douala" — the last segment, readable, for a zone not on the list. */
export function zoneCity(zone: ZoneId): string {
  return zoneOption(zone)?.city ?? zone.split('/').pop()?.replace(/_/g, ' ') ?? zone
}
