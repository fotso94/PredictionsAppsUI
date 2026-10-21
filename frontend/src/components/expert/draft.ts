/**
 * The composer's unpublished drafts: one per signed-in expert AND fixture, in this browser only.
 *
 * WHAT A DRAFT IS NOT: it is not a submission, not a queue entry, and not a thing any timer acts
 * on. Nothing in this module talks to the API. A draft exists so that closing the tab halfway
 * through writing a prediction does not lose the work, and so the dashboard can offer "continue
 * where you left off" instead of a blank start. A prediction becomes public when, and only when,
 * the expert presses publish in the composer — autosaving here can never cause that.
 *
 * ONE KEY PER (USER, FIXTURE), and that is the fix for QA finding 2. The first version kept one
 * slot per user, so opening fixture B wrote B's empty form over A's draft in the composer's first
 * render, and A's words were gone before a key was pressed. Now a write for B goes to B's key and
 * is structurally unable to touch A's, and two tabs on two fixtures cannot race one slot.
 *
 *   key:   expert.composer.draft.v2.<userId>.<fixtureId>   (both segments encoded, dots included,
 *          so a prefix scan of one user can never match another user's keys)
 *   entry: { v: 2, fixture, values, savedAt }
 *
 * THE RULES, each one an owner decision:
 *  - No user id, nothing stored and nothing read. There is no shared "anonymous" slot.
 *  - An empty composer is never stored. Writing an empty one REMOVES that fixture's draft (the
 *    expert erased their own words) and never touches another fixture's.
 *  - Nothing removes a draft except a confirmed discard, a successful publish of that fixture, the
 *    expert emptying it, and the cap below. Not kickoff, not age, not logout (the user id in the
 *    key already keeps accounts apart).
 *  - The cap: at most DRAFT_CAP drafts per user. Over it, the only drafts ever evicted are the
 *    oldest-saved of those whose fixture kicked off more than EVICTABLE_AFTER_KICKOFF_MS ago. A
 *    draft with no known kickoff, a future fixture or one inside that grace is never evicted, so
 *    the cap can be exceeded rather than lose live work.
 *  - A browser that refuses the write (quota, blocked site data) is reported to the caller as
 *    'failed', so the page can say so. Nothing here ever throws into a page.
 *
 * THE v1 KEY (`expert.composer.draft.v1.<userId>`) is migrated the first time this user's drafts
 * are read: a non-empty draft with a fixture goes to that fixture's key unless a draft saved at
 * the same time or later is already there; a non-empty draft without a fixture goes to the
 * UNASSIGNED slot; an empty one is simply removed. Idempotent, because a test (or another tab)
 * may write the v1 key again at any time. `.v1.anonymous` cannot be attributed to anyone and is
 * left where it is.
 */

import { ComposerValues, EMPTY_COMPOSER, composerIsEmpty } from './composer'

const PREFIX = 'expert.composer.draft'
const V1_PREFIX = `${PREFIX}.v1`
const V2_PREFIX = `${PREFIX}.v2`

/** The slot a legacy draft with no fixture is kept in. Never a real fixture id. */
export const UNASSIGNED = '__unassigned'

/** At most this many drafts per expert before the cap evicts anything. */
export const DRAFT_CAP = 50
/** Only a draft whose fixture kicked off longer ago than this can be evicted by the cap. */
export const EVICTABLE_AFTER_KICKOFF_MS = 7 * 24 * 60 * 60 * 1000

/** Enough of the fixture to show the expert what the draft is about without re-fetching it. */
export interface DraftFixture {
  id: string
  homeTeam: string
  awayTeam: string
  competition: string | null
  /** Local kickoff as already formatted for display, e.g. "2026-09-20 19:30". */
  kickoff: string | null
  /** The kickoff instant (ISO, UTC) when known. Null for a legacy draft or an unknown kickoff. */
  kickoffUtc: string | null
}

export interface ComposerDraft {
  /** The fixture id this draft is stored under, or UNASSIGNED. */
  slot: string
  fixture: DraftFixture | null
  values: ComposerValues
  /** ISO timestamp of the last keystroke that was saved. */
  savedAt: string
}

/** What a write did. 'failed' is the one a page must tell the expert about. */
export type DraftWriteResult = 'saved' | 'removed' | 'skipped' | 'failed'

/** encodeURIComponent leaves '.' alone; the key uses '.' as its separator, so it is encoded too. */
function segment(value: string): string {
  return encodeURIComponent(value).replace(/\./g, '%2E')
}

function userPrefix(userId: string): string {
  return `${V2_PREFIX}.${segment(userId)}.`
}

function keyFor(userId: string, slot: string): string {
  return `${userPrefix(userId)}${segment(slot)}`
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
    kickoffUtc: typeof source.kickoffUtc === 'string' && !Number.isNaN(Date.parse(source.kickoffUtc))
      ? source.kickoffUtc
      : null,
  }
}

function time(iso: string): number {
  const at = Date.parse(iso)
  return Number.isNaN(at) ? 0 : at
}

/**
 * One stored entry, or null when it is unreadable, empty, or not what its key says it is.
 *
 * An entry under fixture A's key that names fixture B is refused rather than shown: the key is the
 * promise that A's draft is about A.
 */
function parseEntry(raw: string | null, slot: string): ComposerDraft | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const values = coerceValues(parsed.values)
    // A draft holding nothing at all is noise, not work to continue.
    if (composerIsEmpty(values)) return null
    const fixture = coerceFixture(parsed.fixture)
    if (slot === UNASSIGNED ? fixture !== null : fixture?.id !== slot) return null
    const savedAt = typeof parsed.savedAt === 'string' && !Number.isNaN(Date.parse(parsed.savedAt))
      ? parsed.savedAt
      : new Date(0).toISOString()
    return { slot, fixture, values, savedAt }
  } catch {
    return null
  }
}

function serialise(fixture: DraftFixture | null, values: ComposerValues, savedAt: string): string {
  return JSON.stringify({ v: 2, fixture, values, savedAt })
}

/** Every stored v2 key of this user, as [key, slot]. Unreadable storage is no keys. */
function userKeys(userId: string): Array<[string, string]> {
  const prefix = userPrefix(userId)
  const out: Array<[string, string]> = []
  try {
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i)
      if (!key || !key.startsWith(prefix)) continue
      const rest = key.slice(prefix.length)
      if (!rest || rest.includes('.')) continue
      try {
        out.push([key, decodeURIComponent(rest)])
      } catch {
        // A key this module did not write. Leave it alone.
      }
    }
  } catch {
    return []
  }
  return out
}

/**
 * Move the one v1 draft this user may still have into the v2 store. Safe to call any number of
 * times; see the header for the rules.
 */
export function migrateLegacyDraft(userId: string | null | undefined): void {
  if (!userId) return
  const legacyKey = `${V1_PREFIX}.${userId}`
  try {
    const raw = window.localStorage.getItem(legacyKey)
    if (raw === null) return
    let parsed: Record<string, unknown> = {}
    try {
      parsed = JSON.parse(raw) as Record<string, unknown>
    } catch {
      // Unreadable is treated as empty: there are no words in it to keep.
    }
    const values = coerceValues(parsed.values)
    if (!composerIsEmpty(values)) {
      const fixture = coerceFixture(parsed.fixture)
      const slot = fixture?.id ?? UNASSIGNED
      const savedAt = typeof parsed.savedAt === 'string' && !Number.isNaN(Date.parse(parsed.savedAt))
        ? parsed.savedAt
        : new Date().toISOString()
      const existing = parseEntry(window.localStorage.getItem(keyFor(userId, slot)), slot)
      if (!existing || time(existing.savedAt) < time(savedAt)) {
        // If this write throws, the v1 key stays and the next read tries again.
        window.localStorage.setItem(keyFor(userId, slot), serialise(fixture, values, savedAt))
      }
    }
    window.localStorage.removeItem(legacyKey)
  } catch {
    // Storage refused. The legacy draft stays where it is, and nothing is lost.
  }
}

/** This user's draft for one fixture (or UNASSIGNED), or null when there is none. */
export function readDraft(userId: string | null | undefined, fixtureId: string | null | undefined): ComposerDraft | null {
  if (!userId || !fixtureId) return null
  migrateLegacyDraft(userId)
  try {
    return parseEntry(window.localStorage.getItem(keyFor(userId, fixtureId)), fixtureId)
  } catch {
    return null
  }
}

/** Every draft this user has in this browser, newest first. */
export function listDrafts(userId: string | null | undefined): ComposerDraft[] {
  if (!userId) return []
  migrateLegacyDraft(userId)
  const drafts: ComposerDraft[] = []
  for (const [key, slot] of userKeys(userId)) {
    try {
      const draft = parseEntry(window.localStorage.getItem(key), slot)
      if (draft) drafts.push(draft)
    } catch {
      // One unreadable entry does not hide the others.
    }
  }
  return drafts.sort((a, b) => time(b.savedAt) - time(a.savedAt))
}

/** True when the fixture's kickoff is known and has passed. */
export function draftKickedOff(draft: ComposerDraft, now: number = Date.now()): boolean {
  const kickoff = draft.fixture?.kickoffUtc
  if (!kickoff) return false
  const at = Date.parse(kickoff)
  return !Number.isNaN(at) && at <= now
}

/** Over the cap, drop the oldest-saved drafts whose fixture kicked off over a week ago. */
function enforceCap(userId: string, keepSlot: string): void {
  const drafts = listDrafts(userId)
  let excess = drafts.length - DRAFT_CAP
  if (excess <= 0) return
  const now = Date.now()
  const evictable = drafts
    .filter(draft => draft.slot !== keepSlot)
    .filter(draft => {
      const kickoff = draft.fixture?.kickoffUtc ? Date.parse(draft.fixture.kickoffUtc) : NaN
      return !Number.isNaN(kickoff) && now - kickoff > EVICTABLE_AFTER_KICKOFF_MS
    })
    .sort((a, b) => time(a.savedAt) - time(b.savedAt))
  for (const draft of evictable) {
    if (excess <= 0) break
    try {
      window.localStorage.removeItem(keyFor(userId, draft.slot))
      excess -= 1
    } catch {
      return
    }
  }
}

/**
 * Save this fixture's draft, or remove it when the composer is empty. Only ever touches the key of
 * `fixture.id` (or `slot`, for the UNASSIGNED draft).
 */
export function writeDraft(
  userId: string | null | undefined,
  fixture: DraftFixture,
  values: ComposerValues,
): DraftWriteResult {
  // A pasted id that happens to be the reserved slot's name is not a fixture this can store.
  if (!userId || !fixture.id || fixture.id === UNASSIGNED) return 'skipped'
  const key = keyFor(userId, fixture.id)
  try {
    if (composerIsEmpty(values)) {
      window.localStorage.removeItem(key)
      return 'removed'
    }
    window.localStorage.setItem(key, serialise(fixture, values, new Date().toISOString()))
  } catch {
    // QuotaExceededError, or a browser that refuses site data. The page says so; the words stay
    // in the page's own state for as long as it is open.
    return 'failed'
  }
  enforceCap(userId, fixture.id)
  return 'saved'
}

/** Forget one draft. Called on a confirmed discard and on a successful publish of that fixture. */
export function clearDraft(userId: string | null | undefined, fixtureId: string | null | undefined): void {
  if (!userId || !fixtureId) return
  try {
    window.localStorage.removeItem(keyFor(userId, fixtureId))
  } catch {
    // Nothing to do: the draft was never durable in the first place.
  }
}

/**
 * Give the UNASSIGNED draft to a fixture, only if that fixture has no draft of its own.
 *
 * Returns the draft now stored under the fixture, or null when the fixture already had one (then
 * nothing moved and both drafts are where they were) or the write was refused.
 */
export function assignUnassignedDraft(userId: string | null | undefined, fixture: DraftFixture): ComposerDraft | null {
  if (!userId) return null
  const unassigned = readDraft(userId, UNASSIGNED)
  if (!unassigned || readDraft(userId, fixture.id)) return null
  try {
    window.localStorage.setItem(keyFor(userId, fixture.id), serialise(fixture, unassigned.values, unassigned.savedAt))
    window.localStorage.removeItem(keyFor(userId, UNASSIGNED))
  } catch {
    return null
  }
  return { slot: fixture.id, fixture, values: unassigned.values, savedAt: unassigned.savedAt }
}

/** A draft's values, or a blank composer when there is no draft. */
export function draftValuesOr(draft: ComposerDraft | null): ComposerValues {
  return draft ? draft.values : { ...EMPTY_COMPOSER }
}
