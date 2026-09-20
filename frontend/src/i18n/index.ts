/**
 * Language, time zone, and the runtime that serves both.
 *
 * ── C1. THE MECHANISM, AND WHY IT IS THIS ONE ───────────────────────────────────────────────
 *
 * No library. `react-i18next` + `i18next` is about 45 kB minified before any catalogue, plus a
 * plugin for the format and another for detection; `react-intl` compiles ICU with a parser of
 * roughly the same size again. This application's entire measured problem is bytes on a phone in
 * Douala — the package immediately before this one split the bundle for exactly that reason — so
 * shipping a general-purpose i18n framework to save writing two hundred lines of message parser
 * would have undone part of the work it is built on top of. What is here instead is `Intl`, which
 * every browser already has and which costs nothing to download: `Intl.PluralRules` for plurals,
 * `Intl.DateTimeFormat` for dates, times and zones, `Intl.NumberFormat` for numbers, and about 250
 * lines in src/i18n/format.ts for the message syntax. No dependency was added to package.json.
 *
 * ONE LANGUAGE IS DOWNLOADED, NOT TWO. The two catalogues are separate modules and French is a
 * `import()`, so it becomes a chunk of its own that an English reader never fetches. English is a
 * static import and therefore lives in the entry chunk — not an oversight, a decision: English is
 * the fallback, and a fallback that needs a network request to exist is not a fallback. It is what
 * a reader sees if the French chunk never arrives on a dropped connection, which on this audience's
 * connection is a real event rather than a hypothetical one.
 *
 * The French reader's cost is therefore one extra request, once, cached afterwards, measured in
 * the package report. It is paid as early as it possibly can be: the fetch is started while this
 * module is being evaluated — before `createRoot().render()` — so it overlaps the rest of the
 * boot rather than following it.
 *
 * ── THREE PREFERENCES, THREE KEYS, AND NONE OF THEM PROOF OF ANOTHER ────────────────────────
 *
 * Cameroon has two official languages with equal status, and its readers are spread across zones
 * that are nothing to do with either. So:
 *
 *   - LANGUAGE is a choice, stored under its own key. It is not read from the time zone.
 *   - TIME ZONE is a choice, stored under its own key (see src/i18n/zones.ts). It is not read
 *     from the language.
 *   - COUNTRY is not stored, not asked for, and not inferred. Nothing in this application needs
 *     it, and guessing it from either of the other two would be a claim about a reader that we
 *     have no evidence for. If a country preference is ever needed it gets a key of its own.
 *
 * The first-visit DEFAULT for language reads `navigator.languages`, which is a browser setting the
 * reader controls, and the default for the zone reads the device clock. Both are starting points
 * that the reader's own choice overrides permanently, and neither is ever treated as a fact about
 * where somebody is.
 *
 * ── WHY THERE IS A MODULE-LEVEL `t` AS WELL AS A HOOK ───────────────────────────────────────
 *
 * Roughly half the sentences in this application are produced by plain `.ts` modules that are not
 * components — freshness.ts, brief.ts, measurement.ts, errors.ts — and are called from inside a
 * render. They read the active catalogue directly through `t()`. Components use `useLocale()`,
 * which is what actually makes React re-render when the language changes; by the time that render
 * runs, `t()` is already serving the new catalogue. The hook is the subscription, the module-level
 * function is the lookup, and they can never disagree because there is one catalogue variable.
 */

import type { CompiledMessage, MessageParams } from './format'
import { compileMessage, formatNumber as formatNumberIn, renderMessage } from './format'
import type { Catalog, MessageKey } from './messages/types'
import en from './messages/en'
import {
  type ZoneId, addDays, dayBoundaryOffsets, deviceZone, isUsableZone, isoDateInZone, noonOn,
  offsetLabel, zoneAbbreviation, zoneCity,
} from './zones'

export type { ZoneId } from './zones'
export type { MessageKey } from './messages/types'

// --------------------------------------------------------------------------- languages

/** The languages this build ships. Both official languages of Cameroon, and nothing pretended. */
export const LANGUAGES = ['en', 'fr'] as const
export type Language = (typeof LANGUAGES)[number]

/** How each language names itself. Never translated: a language picker is read by someone who
 *  cannot necessarily read the language currently on screen. */
export const LANGUAGE_ENDONYM: Record<Language, string> = { en: 'English', fr: 'Français' }

/** The BCP 47 tag handed to `Intl`. Kept apart from the catalogue key so a regional variant can
 *  be added later without renaming every message file. */
const INTL_LOCALE: Record<Language, string> = { en: 'en-GB', fr: 'fr-FR' }

function isLanguage(value: unknown): value is Language {
  return typeof value === 'string' && (LANGUAGES as readonly string[]).includes(value)
}

// --------------------------------------------------------------------------- stored preferences

/** Versioned, so a later change to what a value MEANS cannot be misread as the old meaning. */
const LANGUAGE_KEY = 'sp.language.v1'
const ZONE_KEY = 'sp.timeZone.v1'

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    // Private mode, disabled storage, a locked-down browser. The choice still applies to this
    // page; it simply will not survive a reload, and the settings panel says so.
    return null
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Same: better than throwing inside a click handler.
  }
}

/** True when a choice made here will still be here after a reload. Reported, never assumed. */
export function preferencesAreDurable(): boolean {
  try {
    const probe = 'sp.storage.probe'
    window.localStorage.setItem(probe, '1')
    window.localStorage.removeItem(probe)
    return true
  } catch {
    return false
  }
}

/**
 * The language to start in when the reader has never chosen.
 *
 * `navigator.languages` is a list the reader configured in their own browser, so it is a
 * preference rather than an inference — which is exactly why it is used and why nothing else is.
 * A `fr-CA` or `fr-BE` tag matches French on its primary subtag; a tag for a language this build
 * does not ship falls through to the next one, and English is the last resort.
 */
function detectLanguage(): Language {
  const stored = readStored(LANGUAGE_KEY)
  if (isLanguage(stored)) return stored
  const offered = typeof navigator === 'undefined'
    ? []
    : [...(navigator.languages ?? []), navigator.language].filter(Boolean)
  for (const tag of offered) {
    const primary = String(tag).toLowerCase().split('-')[0]
    if (isLanguage(primary)) return primary
  }
  return 'en'
}

function detectZone(): ZoneId {
  const stored = readStored(ZONE_KEY)
  // A zone stored by a browser that knew it and read by one that does not is a real possibility,
  // and falling back is better than formatting every time on this page as Invalid Date.
  if (stored && isUsableZone(stored)) return stored
  return deviceZone()
}

// --------------------------------------------------------------------------- the active state

let language: Language = typeof window === 'undefined' ? 'en' : detectLanguage()
let catalog: Catalog = en
let zone: ZoneId = typeof window === 'undefined' ? 'UTC' : detectZone()
/** True when the reader asked for a language whose catalogue could not be fetched. */
let catalogFailed = false

const compiled = new Map<string, CompiledMessage>()

const listeners = new Set<() => void>()

function announce(): void {
  for (const listener of listeners) listener()
}

/** Subscribe to language or zone changes. Returns the unsubscribe. */
export function onLocaleChange(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

/** The active language. */
export function currentLanguage(): Language {
  return language
}

/** The active time zone. Every date and time on screen is formatted in it. */
export function currentZone(): ZoneId {
  return zone
}

/** The BCP 47 tag `Intl` is being given. */
export function currentLocale(): string {
  return INTL_LOCALE[language]
}

/** True when the reader's chosen catalogue failed to download and English is standing in. */
export function languageFellBack(): boolean {
  return catalogFailed
}

// --------------------------------------------------------------------------- loading a catalogue

/**
 * The French catalogue, as its own chunk.
 *
 * `import()` rather than a static import is the whole of the code-splitting decision: this is the
 * line that keeps a French-sized file out of an English reader's download, and vice versa for
 * everything English that is NOT the fallback.
 */
async function loadCatalog(next: Language): Promise<Catalog> {
  if (next === 'en') return en
  const module = await import('./messages/fr')
  return module.default
}

function applyLanguage(next: Language, loaded: Catalog, failed: boolean): void {
  language = next
  catalog = loaded
  catalogFailed = failed
  compiled.clear()
  if (typeof document !== 'undefined') {
    // Read by assistive technology to pick a voice, and by the browser for hyphenation and
    // quotation marks. Wrong `lang` is a real accessibility defect, not a nicety.
    document.documentElement.lang = next
  }
  announce()
}

/**
 * Started while this module is evaluated — i.e. before `createRoot().render()` in main.tsx —
 * and awaited there. The reader never sees a flash of the wrong language, and the request is in
 * flight for as much of the boot as possible rather than beginning after it.
 */
const initialLoad: Promise<void> = (async () => {
  if (typeof window === 'undefined') return
  const wanted = language
  if (wanted === 'en') {
    applyLanguage('en', en, false)
    return
  }
  try {
    applyLanguage(wanted, await loadCatalog(wanted), false)
  } catch {
    // The chunk did not arrive. English is already loaded, so the page is readable; the flag is
    // what lets the interface say so instead of silently serving a language nobody asked for.
    applyLanguage('en', en, true)
  }
})()

/** Resolves once the reader's chosen catalogue is in place. Awaited once, at boot. */
export function localeReady(): Promise<void> {
  return initialLoad
}

/**
 * Change the language. Resolves when the new catalogue is in place, or when it has failed and
 * English has been kept.
 *
 * Nothing is applied until the catalogue is actually loaded, so the interface never renders half
 * in one language and half in another.
 */
export async function setLanguage(next: Language): Promise<void> {
  if (!isLanguage(next)) return
  writeStored(LANGUAGE_KEY, next)
  if (next === language && !catalogFailed) return
  try {
    applyLanguage(next, await loadCatalog(next), false)
  } catch {
    applyLanguage('en', en, next !== 'en')
  }
}

// --------------------------------------------------------------------------- changing the zone

/** Called when the zone changes, so cached data mapped in the old zone is not reused. */
const zoneChangeHooks = new Set<() => void>()

/**
 * Register work that must happen when the reader changes zone.
 *
 * The match services map a fixture's local kick-off time and local calendar date at FETCH time
 * and cache the result, so a cached day mapped in Europe/Paris would keep its Paris times after a
 * move to Africa/Douala. The display reads the UTC instant and re-formats it on every render, so
 * what is on screen is right immediately; this is what stops a stale `Match.date` reaching the
 * grouping code behind it. Registered by the service rather than imported here, so this module
 * stays free of any dependency on the data layer.
 */
export function onZoneChange(hook: () => void): () => void {
  zoneChangeHooks.add(hook)
  return () => { zoneChangeHooks.delete(hook) }
}

export function setZone(next: ZoneId): void {
  if (!next || next === zone || !isUsableZone(next)) return
  zone = next
  writeStored(ZONE_KEY, next)
  for (const hook of zoneChangeHooks) hook()
  announce()
}

// --------------------------------------------------------------------------- translating

export type TranslateFn = (key: MessageKey, params?: MessageParams) => string

/**
 * One message, in the active language.
 *
 * A key missing from the active catalogue falls back to English rather than to the key itself: a
 * reader is better served by a true sentence in the wrong language than by `matchday.emptyTitle`.
 * It cannot happen for a key in this build — `Catalog` is typed from English, so an incomplete
 * catalogue does not compile — but it can happen to a catalogue chunk served from an older
 * deploy's cache, which is precisely when a silent blank would be hardest to diagnose.
 */
export const t: TranslateFn = (key, params) => {
  const source = catalog[key] ?? en[key]
  if (source === undefined) return String(key)
  let message = compiled.get(source)
  if (!message) {
    message = compileMessage(source)
    compiled.set(source, message)
  }
  return renderMessage(message, currentLocale(), params)
}

// --------------------------------------------------------------------------- formatting values

const dateTimeFormats = new Map<string, Intl.DateTimeFormat>()

function dateTimeFormat(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${currentLocale()}|${zone}|${JSON.stringify(options)}`
  let format = dateTimeFormats.get(key)
  if (!format) {
    format = new Intl.DateTimeFormat(currentLocale(), { timeZone: zone, ...options })
    dateTimeFormats.set(key, format)
  }
  return format
}

function asDate(value: Date | string | number | null | undefined): Date | null {
  if (value === null || value === undefined) return null
  const at = value instanceof Date ? value : new Date(value)
  return Number.isNaN(at.getTime()) ? null : at
}

// --------------------------------------------------------- a timestamp the backend wrote

/** A timestamp that already carries its offset: a trailing `Z`, `+01:00` or `-0400`. */
const CARRIES_AN_OFFSET = /(?:Z|[+-]\d{2}:?\d{2})$/i

/** A calendar date with no time at all. ECMAScript already reads this form as UTC midnight. */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

/** What `backendInstant` could establish about a timestamp from the server. */
export interface BackendInstant {
  /** The moment, or null when the value was absent or unreadable. */
  at: Date | null
  /**
   * True when the server said which zone the timestamp was in. False when it did not and this
   * read it as UTC — which is a claim, and the page that shows it should say so.
   */
  anchored: boolean
}

/**
 * Read a timestamp from this backend, and report whether it actually named an instant.
 *
 * WHY THIS EXISTS AND WHY EVERY PAGE SHOWING A SERVER TIMESTAMP SHOULD USE IT. Several of this
 * backend's columns are `DateTime` with no time zone, written with `datetime.utcnow()` — see
 * `TimestampMixin` in backend/app/models/base.py:34, which is where `created_at` and `updated_at`
 * come from. Pydantic serialises a naive datetime with NO offset at all: "2026-01-05T09:00:00".
 * And ECMAScript reads a date-TIME string without an offset in the DEVICE's zone, not UTC. So
 * `new Date(profile.created_at)` was silently shifted by whatever the reader's laptop was set to,
 * and then `toLocaleDateString()` shifted it again into the device's zone and the device's
 * language. On a phone in Douala that is how a 23:30 UTC sign-up became the following day.
 *
 * Reading it as UTC is not a guess: it is what the server wrote. But it IS an assumption about
 * the server rather than something the payload states, so it is reported rather than hidden —
 * `anchored: false` is the caller's cue to say on the page that the date is being read as UTC
 * and shown in the reader's chosen zone. ProfilePage.tsx does exactly that.
 *
 * A DATE-ONLY value ("2026-01-05") is a calendar date and not an instant at all. ECMAScript
 * already reads that form as UTC midnight, and it comes back `anchored: false` for the same
 * reason: showing it in a zone behind UTC would move it to the day before, and the caller needs
 * to be able to say so.
 */
export function backendInstant(value: string | number | Date | null | undefined): BackendInstant {
  if (value === null || value === undefined || value === '') return { at: null, anchored: true }
  if (value instanceof Date || typeof value === 'number') {
    return { at: asDate(value), anchored: true }
  }
  const trimmed = value.trim()
  // A calendar date parses on its own; appending "Z" to it would only make it unreadable.
  if (DATE_ONLY.test(trimmed)) return { at: asDate(trimmed), anchored: false }
  const anchored = CARRIES_AN_OFFSET.test(trimmed)
  // Appending "Z" is what makes the browser read the server's UTC as UTC. Nothing else here
  // touches the string: a value that is already anchored is parsed exactly as it arrived.
  const at = asDate(anchored ? trimmed : `${trimmed}Z`)
  // A string that does not parse even with the offset added is unreadable, not unanchored.
  return at ? { at, anchored } : { at: null, anchored: true }
}

/** "19 September 2026" / "19 septembre 2026". Null in, null out — never "Invalid Date". */
export function formatDate(value: Date | string | number | null | undefined): string | null {
  const at = asDate(value)
  return at ? dateTimeFormat({ day: 'numeric', month: 'long', year: 'numeric' }).format(at) : null
}

/** "Saturday 19 September 2026" / "samedi 19 septembre 2026". */
export function formatFullDate(value: Date | string | number | null | undefined): string | null {
  const at = asDate(value)
  return at
    ? dateTimeFormat({ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(at)
    : null
}

/** A calendar date string (`YYYY-MM-DD`) spelled out, anchored at midday in the chosen zone. */
export function formatIsoDate(iso: string, full = true): string {
  const at = noonOn(zone, iso)
  if (Number.isNaN(at.getTime())) return iso
  return (full ? formatFullDate(at) : formatDate(at)) ?? iso
}

/** "20:45" — the kick-off, in the reader's chosen zone, in their own convention. */
export function formatTime(value: Date | string | number | null | undefined): string | null {
  const at = asDate(value)
  return at ? dateTimeFormat({ hour: '2-digit', minute: '2-digit' }).format(at) : null
}

/** Date and time together, for a timestamp. */
export function formatDateTime(value: Date | string | number | null | undefined): string | null {
  const at = asDate(value)
  return at
    ? dateTimeFormat({
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(at)
    : null
}

/** The locale's own short weekday: "Sat" / "sam.". */
export function formatWeekdayShort(value: Date): string {
  return dateTimeFormat({ weekday: 'short' }).format(value)
}

/** The day of the month as the locale writes the numeral. */
export function formatDayOfMonth(value: Date): string {
  return dateTimeFormat({ day: 'numeric' }).format(value)
}

/** A number in the reader's own convention: 1,234 in English, 1 234 in French. */
export function formatNumber(value: number): string {
  return formatNumberIn(currentLocale(), value)
}

const moneyFormats = new Map<string, Intl.NumberFormat>()

/**
 * A price, in the reader's own convention and in the currency the payload names.
 *
 * `` `$${price.toFixed(2)}` `` was English with an American currency symbol welded on, for every
 * reader: it wrote "$9.99" in French too, where the convention is "9,99 $" — the symbol after
 * the figure, a comma for the decimal, and a no-break space between them that `Intl` supplies
 * and a template literal cannot.
 *
 * `currencyDisplay: 'narrowSymbol'` rather than the default: the default renders USD in en-GB as
 * "US$9.99", so the plain symbol is both what this interface already showed and the less
 * cluttered of the two. The currency itself is never assumed — it is the `currency` field the
 * subscription payload carries.
 *
 * An unknown currency code, or a runtime without `narrowSymbol`, makes `Intl` throw rather than
 * degrade. The fallback below prints the grouped figure and the code beside it, which is
 * readable and true, instead of taking the page down over a price.
 */
export function formatMoney(amount: number, currency: string): string {
  const code = (currency || '').trim().toUpperCase()
  const key = `${currentLocale()}|${code}`
  let format = moneyFormats.get(key)
  if (!format) {
    try {
      format = new Intl.NumberFormat(currentLocale(), {
        style: 'currency',
        currency: code,
        currencyDisplay: 'narrowSymbol',
      })
    } catch {
      try {
        format = new Intl.NumberFormat(currentLocale(), { style: 'currency', currency: code })
      } catch {
        return `${formatNumber(amount)}${code ? ` ${code}` : ''}`
      }
    }
    moneyFormats.set(key, format)
  }
  return format.format(amount)
}

const percentFormats = new Map<string, Intl.NumberFormat>()

/**
 * A percentage the reader can read, from a 0-100 value.
 *
 * `Intl` owns both halves of this, and both differ by language: the decimal separator (47.2% in
 * English, 47,2 % in French) and whether a space precedes the sign (it does in French, and it is
 * a no-break space, so the number and its sign never split across a line). Writing
 * `${value.toFixed(1)}%` produced the English form for everybody.
 *
 * `digits` is the number of decimal places, fixed rather than maximum, so a column of figures
 * stays aligned. English output is unchanged from the `toFixed` it replaces.
 */
export function formatPercentValue(value: number, digits = 1): string {
  const key = `${currentLocale()}|${digits}`
  let format = percentFormats.get(key)
  if (!format) {
    format = new Intl.NumberFormat(currentLocale(), {
      style: 'percent',
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
    percentFormats.set(key, format)
  }
  return format.format(value / 100)
}

/**
 * The same, but trailing zeros dropped — the backend's own `_pct_text` rule, which publishes
 * "85" rather than "85.0" and "33.5" as it is. Kept identical to the backend's so a figure shown
 * from a list payload and the same figure shown from a brief read the same.
 */
export function formatPercentTrimmed(value: number): string {
  const rounded = Math.round(value * 10) / 10
  return formatPercentValue(rounded, Number.isInteger(rounded) ? 0 : 1)
}

/** How the chosen zone is named on screen: "Douala, Yaoundé · WAT (UTC+01:00)". */
export function zoneLabel(at: Date = new Date()): string {
  const abbreviation = zoneAbbreviation(currentLocale(), zone, at)
  const offset = offsetLabel(zone, at)
  return abbreviation ? `${zoneCity(zone)} · ${abbreviation} (${offset})` : `${zoneCity(zone)} · ${offset}`
}

// --------------------------------------------------------------------------- calendar days

/**
 * The calendar date `offsetDays` from `from`, in the reader's chosen zone.
 *
 * This is the function `localDateString` in the match services delegates to, so the day the page
 * asks the backend for, the day the date strip highlights and the day a fixture is filed under
 * are one answer computed in one place.
 */
export function zonedDateString(offsetDays = 0, from: Date = new Date()): string {
  return addDays(isoDateInZone(zone, from), offsetDays)
}

/** The offsets bounding a local day in the chosen zone, for the backend's day window. */
export function zonedDayOffsets(iso?: string): { start: number; end: number } {
  return dayBoundaryOffsets(zone, iso ?? isoDateInZone(zone, new Date()))
}

/** Midday on a calendar date in the chosen zone, as a safe anchor for date arithmetic. */
export function zonedNoon(iso: string): Date {
  return noonOn(zone, iso)
}
