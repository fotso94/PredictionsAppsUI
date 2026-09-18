/**
 * The one unpublished draft the composer keeps, in this browser only.
 *
 * WHAT A DRAFT IS NOT: it is not a submission, not a queue entry, and not a thing any timer acts
 * on. Nothing in this module talks to the API. The draft exists so that closing the tab halfway
 * through writing a prediction does not lose the work, and so the dashboard can offer "continue
 * where you left off" instead of a blank start. A prediction becomes public when, and only when,
 * the expert presses publish in the composer — autosaving here can never cause that.
 *
 * It is stored per signed-in user id, so a shared machine never shows one expert the half-written
 * words of another, and it is cleared the moment a publish succeeds.
 *
 * Every read and write is wrapped: `localStorage` throws outright in a browser set to block site
 * data, and a draft is a convenience — losing it must never take the composer down with it.
 */

import { ComposerValues, EMPTY_COMPOSER, composerIsEmpty } from './composer'

const KEY_PREFIX = 'expert.composer.draft.v1'

/** Enough of the fixture to show the expert what the draft is about without re-fetching it. */
export interface DraftFixture {
  id: string
  homeTeam: string
  awayTeam: string
  competition: string | null
  /** Local kickoff as already formatted for display, e.g. "2026-09-20 19:30". */
  kickoff: string | null
}

export interface ComposerDraft {
  fixture: DraftFixture | null
  values: ComposerValues
  /** ISO timestamp of the last keystroke that was saved. */
  savedAt: string
}

function keyFor(userId: string | null | undefined): string {
  return userId ? `${KEY_PREFIX}.${userId}` : `${KEY_PREFIX}.anonymous`
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asFlag(value: unknown): boolean {
  return value === true
}

/**
 * Rebuild `ComposerValues` from whatever was in storage.
 *
 * Field by field rather than a cast: the stored JSON is last week's shape, or another tab's, or
 * corrupt, and a cast would let a number or an object reach an input's `value` and break the page.
 */
function coerceValues(raw: unknown): ComposerValues {
  const source = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  return {
    homeWin: asText(source.homeWin),
    draw: asText(source.draw),
    awayWin: asText(source.awayWin),
    conviction: asText(source.conviction),
    bttsEnabled: asFlag(source.bttsEnabled),
    bttsYes: asText(source.bttsYes),
    bttsNo: asText(source.bttsNo),
    bttsConviction: asText(source.bttsConviction),
    over25Enabled: asFlag(source.over25Enabled),
    over25: asText(source.over25),
    under25: asText(source.under25),
    over35Enabled: asFlag(source.over35Enabled),
    over35: asText(source.over35),
    under35: asText(source.under35),
    totalsConviction: asText(source.totalsConviction),
    reasoning: asText(source.reasoning),
  }
}

function coerceFixture(raw: unknown): DraftFixture | null {
  if (!raw || typeof raw !== 'object') return null
  const source = raw as Record<string, unknown>
  const id = asText(source.id)
  if (!id) return null
  return {
    id,
    homeTeam: asText(source.homeTeam),
    awayTeam: asText(source.awayTeam),
    competition: typeof source.competition === 'string' ? source.competition : null,
    kickoff: typeof source.kickoff === 'string' ? source.kickoff : null,
  }
}

/** The stored draft, or null when there is none (or storage is unreadable). */
export function readDraft(userId: string | null | undefined): ComposerDraft | null {
  try {
    const raw = window.localStorage.getItem(keyFor(userId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const values = coerceValues(parsed.values)
    const fixture = coerceFixture(parsed.fixture)
    // A draft holding nothing at all is noise on the dashboard, not work to continue.
    if (composerIsEmpty(values) && !fixture) return null
    return {
      fixture,
      values,
      savedAt: typeof parsed.savedAt === 'string' ? parsed.savedAt : new Date().toISOString(),
    }
  } catch {
    return null
  }
}

/** Save the draft. A composer with nothing in it clears the slot instead of storing emptiness. */
export function writeDraft(userId: string | null | undefined, fixture: DraftFixture | null, values: ComposerValues): void {
  try {
    if (composerIsEmpty(values) && !fixture) {
      window.localStorage.removeItem(keyFor(userId))
      return
    }
    const draft: ComposerDraft = { fixture, values, savedAt: new Date().toISOString() }
    window.localStorage.setItem(keyFor(userId), JSON.stringify(draft))
  } catch {
    // A browser that refuses site data simply gets no draft. The composer keeps working.
  }
}

/** Forget the draft. Called on a successful publish and when the expert discards it by hand. */
export function clearDraft(userId: string | null | undefined): void {
  try {
    window.localStorage.removeItem(keyFor(userId))
  } catch {
    // Nothing to do: the draft was never durable in the first place.
  }
}

/** A draft's values, or a blank composer when there is no draft. */
export function draftValuesOr(draft: ComposerDraft | null): ComposerValues {
  return draft ? draft.values : { ...EMPTY_COMPOSER }
}

/** "3 minutes ago" for the dashboard's continue card. Null when the timestamp is unreadable. */
export function savedAgo(savedAt: string, now: Date = new Date()): string | null {
  const at = new Date(savedAt)
  if (Number.isNaN(at.getTime())) return null
  const minutes = Math.floor((now.getTime() - at.getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes === 1) return '1 minute ago'
  if (minutes < 60) return `${minutes} minutes ago`
  const hours = Math.floor(minutes / 60)
  if (hours === 1) return '1 hour ago'
  if (hours < 24) return `${hours} hours ago`
  const days = Math.floor(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}
