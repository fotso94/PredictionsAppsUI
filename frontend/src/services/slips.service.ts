/**
 * The selection slip: one store for the dock on every page, the match-page "Add" buttons, and the
 * history page, so they cannot disagree about what is on the slip.
 *
 * TWO HOMES FOR A DRAFT. A signed-in reader's slips live on the server (/api/v1/me/slips) and are
 * private to the account. A visitor who is not signed in can still build a draft: it lives in this
 * browser only (localStorage, `selections.draft.v1`) and is handed to the account the moment they
 * sign in — each leg re-validated by the server, and any it refuses reported rather than dropped
 * silently. Signing out leaves the server's slips where they are and clears the dock.
 *
 * WHAT IS REMEMBERED ON A LEG is the server's business (see backend/app/services/slips.py): the
 * probability at the moment of adding is stored with the leg, and the current one is served
 * beside it. The local draft keeps the same fact the same way — the selection as it was when the
 * reader chose it.
 *
 * FAILURE IS NEVER AN EMPTY RESULT. A read that fails keeps the last slips received and reports
 * `status: 'error'` with the server's own message; a write that fails rethrows, and the caller
 * says so. There is no optimistic state to roll back: every write applies the slip the server
 * returned, and a dock that briefly shows the previous leg count is better than one that shows a
 * leg the server refused.
 */

import { useCallback, useEffect, useSyncExternalStore } from 'react'
import apiClient, { tokenManager } from './api-client'
import { getErrorMessage } from '@/utils/errors'
import type { ApiMarketSelection, ApiMatchSummary, ApiSlip, ApiSlipLeg, SlipLegInput, SlipStatus } from '@/types/markets'

const API = '/api/v1/me/slips'
export const LOCAL_DRAFT_KEY = 'selections.draft.v1'
/**
 * Selections a browser draft handed to ONE account that have not reached it yet, per account.
 *
 * The anonymous draft belongs to nobody. The moment an account signs in, the draft becomes that
 * account's pending transfer - synchronously, before any request leaves - and from then on it is
 * stored under that account's id. If the account changes while the transfer is on the wire, what
 * has not been sent stays here, for that account, and is resumed the next time it signs in. It is
 * never offered to whoever signed in next.
 */
export const TRANSFER_KEY_PREFIX = 'selections.transfer.v1.'

/** A leg of the browser-only draft: the selection as it was chosen, and enough of the fixture to show it. */
export interface LocalLeg {
  match: ApiMatchSummary
  selection: ApiMarketSelection
  odds: number | null
  addedAt: string
}

export interface LocalDraft {
  legs: LocalLeg[]
}

export interface SlipsState {
  status: 'idle' | 'loading' | 'ready' | 'error'
  error: string | null
  /** Every slip of the signed-in account, newest first. Empty while signed out. */
  slips: ApiSlip[]
  /** The slip the dock edits; null when a new one will be started by the next add. */
  activeId: string | null
  /** The browser-only draft, used while signed out. */
  local: LocalDraft
  /** Legs the server refused when a local draft was handed to the account, with its reason each. */
  handoffRefused: Array<{ leg: LocalLeg; reason: string }>
  /** True when a transfer stopped on a failure that may pass; the unsent legs are kept and retried. */
  handoffPaused: boolean
  signedIn: boolean
  userId: string | null
}

const EMPTY_LOCAL: LocalDraft = { legs: [] }

function readLocal(): LocalDraft {
  try {
    const raw = localStorage.getItem(LOCAL_DRAFT_KEY)
    if (!raw) return EMPTY_LOCAL
    const parsed = JSON.parse(raw) as LocalDraft
    return Array.isArray(parsed?.legs) ? { legs: parsed.legs } : EMPTY_LOCAL
  } catch {
    return EMPTY_LOCAL
  }
}

const transferKey = (userId: string): string => `${TRANSFER_KEY_PREFIX}${userId}`

/**
 * One account's pending transfer: the selections not yet delivered and, once the first one has
 * been, the slip they are being delivered TO. Without the destination a transfer resumed after a
 * partial failure or a reload would open a second slip for the rest of the same draft.
 */
interface PendingTransfer {
  slipId: string | null
  legs: LocalLeg[]
  /**
   * Set just before the request that CREATES the destination leaves: the ids of every slip the
   * account held at that moment. While it is set and no destination is known, that request may
   * have created a slip whose answer never arrived, so a resumed transfer looks for it - a slip
   * not in this list, carrying the selection that request carried - before creating another.
   */
  creating: { before: string[] } | null
}

function readTransfer(userId: string): PendingTransfer {
  try {
    const raw = localStorage.getItem(transferKey(userId))
    const parsed = raw ? (JSON.parse(raw) as { legs?: LocalLeg[]; slipId?: unknown; creating?: { before?: unknown } | null }) : null
    const before = parsed?.creating?.before
    return {
      slipId: typeof parsed?.slipId === 'string' && parsed.slipId ? parsed.slipId : null,
      legs: Array.isArray(parsed?.legs) ? parsed.legs : [],
      creating: Array.isArray(before) ? { before: before.filter((id): id is string => typeof id === 'string') } : null,
    }
  } catch {
    return { slipId: null, legs: [], creating: null }
  }
}

function writeTransfer(userId: string, transfer: PendingTransfer): void {
  try {
    if (transfer.legs.length === 0) localStorage.removeItem(transferKey(userId))
    else localStorage.setItem(transferKey(userId), JSON.stringify(transfer))
  } catch {
    // Storage refused: the transfer still runs from memory; an interrupted one is lost on reload.
  }
}

const sameLeg = (a: LocalLeg, b: LocalLeg): boolean =>
  a.match.id === b.match.id && a.selection.selection_id === b.selection.selection_id

/** A refusal the server will give again whatever happens: drop the leg and say why. */
function permanentlyRefused(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status
  return status === 404 || status === 409 || status === 422
}

/** The remembered destination itself can no longer take legs: deleted, or recorded since. */
function destinationGone(error: unknown): boolean {
  const code = slipErrorCode(error)
  return code === 'not_found' || code === 'recorded_immutable'
}

function writeLocal(draft: LocalDraft): void {
  try {
    if (draft.legs.length === 0) localStorage.removeItem(LOCAL_DRAFT_KEY)
    else localStorage.setItem(LOCAL_DRAFT_KEY, JSON.stringify(draft))
  } catch {
    // Storage refused: the draft lives in memory for this session and is lost on reload.
  }
}

class SlipsStore {
  private state: SlipsState = {
    status: 'idle', error: null, slips: [], activeId: null, local: readLocal(), handoffRefused: [],
    handoffPaused: false, signedIn: false, userId: null,
  }

  private listeners = new Set<() => void>()

  private session = 0

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  getSnapshot = (): SlipsState => this.state

  private set(patch: Partial<SlipsState>): void {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach(listener => listener())
  }

  /* ------------------------------------------------------------------ identity */

  /**
   * Bind the store to the signed-in account (or to nobody). Signing in with a local draft hands
   * it to the account; signing out clears the account's slips from view and the dock.
   */
  bindAccount = async (userId: string | null): Promise<void> => {
    if (userId === this.state.userId && (userId === null || this.state.status !== 'idle')) return
    // Every identity change ends the session: what was on screen belonged to somebody else, and
    // a write or read still on the wire for them may not land here (see `guard`).
    this.session += 1
    const session = this.session
    if (!userId) {
      this.set({ signedIn: false, userId: null, slips: [], activeId: null, status: 'idle', error: null, handoffRefused: [], handoffPaused: false })
      return
    }
    // Cleared BEFORE the first await: the previous account's slips must not stay on screen for
    // even one render of the next account's session.
    this.set({ signedIn: true, userId, slips: [], activeId: null, status: 'loading', error: null, handoffRefused: [], handoffPaused: false })
    try {
      await this.handOffLocalDraft(session, userId)
      if (session !== this.session) return
      await this.load(session)
    } catch (error) {
      if (session !== this.session) return
      this.set({ status: 'error', error: getErrorMessage(error, 'Your slips could not be loaded.') })
    }
  }

  /**
   * Hand the browser draft, and anything this account's earlier transfer left unsent, to `userId`.
   *
   * EVERY REQUEST BELONGS TO `userId`, and is checked to, before it leaves and after it answers:
   *
   * - The draft is claimed synchronously: moved into `userId`'s pending transfer and cleared from
   *   the shared browser draft before the first request, so no later sign-in can claim it too.
   * - Each request carries the access token captured when this transfer began, explicitly, and is
   *   marked so the client never refreshes and retries it under whatever token is stored by then.
   *   A token in storage that is no longer the captured one means the identity may have changed:
   *   the transfer stops. (A legitimate refresh for the same account stops it too; it resumes on
   *   the next sign-in or reload, which costs a delay and never a leak.)
   * - The identity is re-checked after every await. On a change the transfer stops at once: what
   *   was not sent stays in `userId`'s pending transfer and nothing touches the new session.
   * - A leg the server accepted leaves the pending list at once, so it is never sent twice. A leg it
   *   refuses for good (409/422/404) leaves too, with the reason shown. Any other failure - network,
   *   5xx, 401 - stops the transfer and keeps this leg and the rest pending, to be retried.
   * - An answer can be lost after the server applied the request. For a leg added to the known
   *   destination, the server's one-selection-per-fixture refusal on the retry says so, and the slip
   *   is read to confirm it. For the request that CREATES the destination there is no id to read:
   *   the account's slips are listed before it leaves, and a resumed transfer adopts a slip that is
   *   new since then and carries that selection instead of creating a second one.
   */
  private async handOffLocalDraft(session: number, userId: string): Promise<void> {
    const claimed = this.state.local.legs
    const transfer = readTransfer(userId)
    for (const leg of claimed) {
      if (!transfer.legs.some(p => sameLeg(p, leg))) transfer.legs.push(leg)
    }
    writeTransfer(userId, transfer)
    if (claimed.length > 0) {
      writeLocal(EMPTY_LOCAL)
      this.set({ local: EMPTY_LOCAL })
    }
    if (transfer.legs.length === 0) return

    const token = tokenManager.getAccessToken()
    const stillThisAccount = (): boolean =>
      session === this.session && this.state.userId === userId
      && token !== null && tokenManager.getAccessToken() === token
    const bound = { headers: { Authorization: `Bearer ${token}` }, _retry: true }
    const refused: Array<{ leg: LocalLeg; reason: string }> = []
    let destination: string | null = transfer.slipId
    let paused = false
    const delivered = (leg: LocalLeg): void => {
      transfer.legs.splice(transfer.legs.findIndex(l => sameLeg(l, leg)), 1)
      writeTransfer(userId, transfer)
    }

    for (const leg of [...transfer.legs]) {
      if (!stillThisAccount()) return
      const body: SlipLegInput = { match_id: leg.match.id, selection_id: leg.selection.selection_id, odds: leg.odds }
      try {
        if (destination) {
          try {
            await apiClient.post<ApiSlip>(`${API}/${destination}/legs`, body, bound)
          } catch (error) {
            if (!destinationGone(error)) throw error
            // The slip this transfer was filling is gone or recorded: start a new one below.
            destination = null
            transfer.slipId = null
            writeTransfer(userId, transfer)
            if (!stillThisAccount()) return
          }
        }
        if (!destination && transfer.creating) {
          // An earlier attempt sent the request that creates the destination and never learned its
          // answer. If the server applied it, that slip exists and already carries this leg.
          const adopted = await this.createdMeanwhile(transfer.creating.before, leg, bound)
          if (!stillThisAccount()) return
          if (adopted === undefined) { paused = true; break }
          transfer.creating = null
          if (adopted) {
            destination = adopted
            transfer.slipId = adopted
          } else {
            writeTransfer(userId, transfer)
          }
        }
        if (!destination) {
          const before = await this.slipIds(bound)
          if (!stillThisAccount()) return
          if (before === null) { paused = true; break }
          // Written down BEFORE the request leaves: if its answer is lost, this is what lets the
          // resumed transfer recognise the slip it made.
          transfer.creating = { before }
          writeTransfer(userId, transfer)
          const { data } = await apiClient.post<ApiSlip>(API, { name: null, legs: [body] }, bound)
          destination = data.id
          // Remembered before anything else can go wrong, so a resumed transfer fills THIS slip.
          transfer.slipId = destination
          transfer.creating = null
        }
        delivered(leg)
      } catch (error) {
        if (slipErrorCode(error) === 'one_per_match' && destination && await this.alreadyOn(destination, leg, bound)) {
          // A previous attempt reached the server although its answer was lost: it is there already.
          delivered(leg)
        } else if (permanentlyRefused(error)) {
          // Refused for good. A refused CREATE made nothing, so there is nothing to look for later.
          if (!destination) transfer.creating = null
          delivered(leg)
          refused.push({ leg, reason: describeSlipError(error) })
        } else {
          paused = true
        }
      }
      if (!stillThisAccount()) return
      if (paused) break
    }
    this.set({ handoffRefused: refused, handoffPaused: paused, activeId: destination ?? this.state.activeId })
  }

  /** The ids of every slip this account holds, or null when they cannot be read now. */
  private async slipIds(bound: object): Promise<string[] | null> {
    try {
      const { data } = await apiClient.get<{ slips: ApiSlip[] }>(API, bound)
      return data.slips.map(slip => slip.id)
    } catch {
      return null
    }
  }

  /**
   * The slip an unanswered create made, if it made one: a slip the account did not hold `before`
   * that carries exactly this selection and can still take legs; the newest by the server's own
   * clock when there are several. Null when there is none, undefined when that cannot be read now.
   */
  private async createdMeanwhile(before: string[], leg: LocalLeg, bound: object): Promise<string | null | undefined> {
    try {
      const { data } = await apiClient.get<{ slips: ApiSlip[] }>(API, bound)
      const known = new Set(before)
      const made = data.slips
        .filter(slip => !known.has(slip.id) && slip.status !== 'recorded'
          && slip.legs.some(l => l.match.id === leg.match.id && l.selection.selection_id === leg.selection.selection_id))
        .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
      return made[0]?.id ?? null
    } catch {
      return undefined
    }
  }

  /** Whether `slipId` already carries exactly this selection on this fixture. */
  private async alreadyOn(slipId: string, leg: LocalLeg, bound: object): Promise<boolean> {
    try {
      const { data } = await apiClient.get<ApiSlip>(`${API}/${slipId}`, bound)
      return data.legs.some(l => l.match.id === leg.match.id && l.selection.selection_id === leg.selection.selection_id)
    } catch {
      return false
    }
  }

  /* ------------------------------------------------------------------ reads */

  load = async (session: number = this.session): Promise<ApiSlip[]> => {
    if (!this.state.signedIn) return []
    const { data } = await apiClient.get<{ slips: ApiSlip[] }>(API)
    if (session !== this.session) return this.state.slips
    const slips = data.slips
    const active = this.state.activeId && slips.some(s => s.id === this.state.activeId)
      ? this.state.activeId
      : (slips.find(s => s.status === 'draft')?.id ?? null)
    this.set({ slips, activeId: active, status: 'ready', error: null })
    return slips
  }

  reload = (): Promise<ApiSlip[]> => this.load()

  /* ------------------------------------------------------------------ the dock's slip */

  active = (): ApiSlip | null => this.state.slips.find(s => s.id === this.state.activeId) ?? null

  select = (id: string | null): void => { this.set({ activeId: id }) }

  /** Start a fresh draft: the next add creates it. */
  startNew = (): void => { this.set({ activeId: null }) }

  /**
   * Refuse an answer that belongs to a session that has ended.
   *
   * A write issued as account A can come back after account B has signed in on the same machine;
   * applying it would put A's slip on B's screen - the favourites store had exactly this hole.
   * Every write captures the session it was issued in and checks it here before touching state.
   */
  private guard(session: number): void {
    if (session !== this.session) throw new SessionEnded()
  }

  private apply(slip: ApiSlip, makeActive = true, session: number = this.session): ApiSlip {
    this.guard(session)
    const others = this.state.slips.filter(s => s.id !== slip.id)
    this.set({ slips: [slip, ...others], activeId: makeActive ? slip.id : this.state.activeId, status: 'ready', error: null })
    return slip
  }

  /** True when the given selection is on the dock's slip (or on the local draft). */
  hasSelection = (matchId: string, selectionId: string): boolean => {
    if (!this.state.signedIn) {
      return this.state.local.legs.some(l => l.match.id === matchId && l.selection.selection_id === selectionId)
    }
    const slip = this.active()
    return Boolean(slip?.legs.some(l => l.match.id === matchId && l.selection.selection_id === selectionId))
  }

  /** The fixture already has a (different) selection on the dock's slip. */
  fixtureTaken = (matchId: string): boolean => {
    if (!this.state.signedIn) return this.state.local.legs.some(l => l.match.id === matchId)
    return Boolean(this.active()?.legs.some(l => l.match.id === matchId))
  }

  /**
   * Add a selection. Signed out, it goes on the browser draft; signed in, on the active slip
   * (created if there is none). One selection per fixture: a second on the same fixture REPLACES
   * the first on the local draft and is refused by the server on an account slip — the dock offers
   * "replace" explicitly, which removes the old leg first.
   */
  addSelection = async (match: ApiMatchSummary, selection: ApiMarketSelection, options: { replace?: boolean; odds?: number | null } = {}): Promise<void> => {
    if (!this.state.signedIn) {
      const others = this.state.local.legs.filter(l => l.match.id !== match.id)
      if (!options.replace && others.length !== this.state.local.legs.length) {
        throw new SlipConflict('one_per_match')
      }
      const local = { legs: [...others, { match, selection, odds: options.odds ?? selection.odds?.value ?? null, addedAt: new Date().toISOString() }] }
      writeLocal(local)
      this.set({ local })
      return
    }
    const session = this.session
    const slip = this.active()
    const body: SlipLegInput = { match_id: match.id, selection_id: selection.selection_id, odds: options.odds ?? null }
    if (!slip) {
      const { data } = await apiClient.post<ApiSlip>(API, { name: null, legs: [body] })
      this.apply(data, true, session)
      return
    }
    const existing = slip.legs.find(l => l.match.id === match.id)
    if (existing) {
      if (!options.replace) throw new SlipConflict('one_per_match')
      // One request, one step: the server validates the replacement before it removes anything,
      // so a refused replacement leaves the original leg exactly where it was.
      const { data } = await apiClient.put<ApiSlip>(`${API}/${slip.id}/legs/${existing.id}`, { selection_id: selection.selection_id, odds: options.odds ?? null })
      this.apply(data, true, session)
      return
    }
    const { data } = await apiClient.post<ApiSlip>(`${API}/${slip.id}/legs`, body)
    this.apply(data, true, session)
  }

  removeLeg = async (matchId: string): Promise<void> => {
    if (!this.state.signedIn) {
      const local = { legs: this.state.local.legs.filter(l => l.match.id !== matchId) }
      writeLocal(local)
      this.set({ local })
      return
    }
    const session = this.session
    const slip = this.active()
    const leg = slip?.legs.find(l => l.match.id === matchId)
    if (!slip || !leg) return
    const { data } = await apiClient.delete<ApiSlip>(`${API}/${slip.id}/legs/${leg.id}`)
    this.apply(data, true, session)
  }

  setLegOdds = async (matchId: string, odds: number | null): Promise<void> => {
    if (!this.state.signedIn) {
      const local = { legs: this.state.local.legs.map(l => (l.match.id === matchId ? { ...l, odds } : l)) }
      writeLocal(local)
      this.set({ local })
      return
    }
    const session = this.session
    const slip = this.active()
    const leg = slip?.legs.find(l => l.match.id === matchId)
    if (!slip || !leg) return
    const { data } = await apiClient.patch<ApiSlip>(`${API}/${slip.id}/legs/${leg.id}`, { odds })
    this.apply(data, true, session)
  }

  clearActive = async (): Promise<void> => {
    if (!this.state.signedIn) {
      writeLocal(EMPTY_LOCAL)
      this.set({ local: EMPTY_LOCAL })
      return
    }
    const session = this.session
    const slip = this.active()
    if (!slip) return
    if (slip.status === 'draft') {
      await apiClient.delete(`${API}/${slip.id}`)
      this.guard(session)
      this.set({ slips: this.state.slips.filter(s => s.id !== slip.id), activeId: null })
    } else {
      this.set({ activeId: null })
    }
  }

  /* ------------------------------------------------------------------ slip-level writes (signed in) */

  update = async (id: string, patch: { name?: string | null; note?: string | null; status?: SlipStatus; currency?: string | null; stake?: string | null }): Promise<ApiSlip> => {
    const session = this.session
    const { data } = await apiClient.patch<ApiSlip>(`${API}/${id}`, patch)
    return this.apply(data, id === this.state.activeId, session)
  }

  record = async (id: string, body: { reference?: string | null; currency?: string | null; stake?: string | null; price?: number | null }): Promise<ApiSlip> => {
    const session = this.session
    const { data } = await apiClient.post<ApiSlip>(`${API}/${id}/record`, body)
    const recorded = this.apply(data, false, session)
    if (this.state.activeId === id) this.set({ activeId: null })
    return recorded
  }

  duplicate = async (id: string): Promise<ApiSlip> => {
    const session = this.session
    const { data } = await apiClient.post<ApiSlip>(`${API}/${id}/duplicate`)
    return this.apply(data, true, session)
  }

  remove = async (id: string): Promise<void> => {
    const session = this.session
    await apiClient.delete(`${API}/${id}`)
    this.guard(session)
    this.set({ slips: this.state.slips.filter(s => s.id !== id), activeId: this.state.activeId === id ? null : this.state.activeId })
  }

  /** Test seam. */
  reset = (): void => {
    this.session += 1
    this.state = { status: 'idle', error: null, slips: [], activeId: null, local: readLocal(), handoffRefused: [], handoffPaused: false, signedIn: false, userId: null }
    this.listeners.forEach(listener => listener())
  }
}

/** An answer that arrived after the session that asked for it had ended. Applied nowhere. */
export class SessionEnded extends Error {
  constructor() {
    super('This slip answer belongs to a session that has ended, and was discarded.')
  }
}

export class SlipConflict extends Error {
  code: 'one_per_match'

  constructor(code: 'one_per_match') {
    super(code)
    this.code = code
  }
}

/** The backend's own reason for a refused slip write, or the generic message. */
export function describeSlipError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object' && 'message' in (detail as Record<string, unknown>)) {
    return String((detail as Record<string, unknown>).message)
  }
  if (typeof detail === 'string') return detail
  return getErrorMessage(error, 'The request did not go through.')
}

export function slipErrorCode(error: unknown): string | null {
  if (error instanceof SlipConflict) return error.code
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object' && 'code' in (detail as Record<string, unknown>)) {
    return String((detail as Record<string, unknown>).code)
  }
  return null
}

const slipsStore = new SlipsStore()
export default slipsStore

/* ------------------------------------------------------------------ the hook */

export interface DockLeg {
  matchId: string
  home: string
  away: string
  competition: string | null
  kickoffUtc: string | null
  selection: ApiMarketSelection | ApiSlipLeg['selection']
  probability: number | null
  probabilitySource: 'provider' | 'calculated'
  modelRunAt: string | null
  odds: { value: number; source: string } | null
  started: boolean
  state: ApiSlipLeg['state'] | 'draft'
  forecastChanged: boolean
  currentAvailable: boolean
  currentProbability: number | null
  legId: string | null
}

function dockLegsFrom(slip: ApiSlip | null, local: LocalDraft, signedIn: boolean, now: number): DockLeg[] {
  if (!signedIn) {
    return local.legs.map(leg => ({
      matchId: leg.match.id, home: leg.match.home?.name ?? '', away: leg.match.away?.name ?? '',
      competition: leg.match.competition?.name ?? null, kickoffUtc: leg.match.kickoff_utc,
      selection: leg.selection, probability: leg.selection.probability, probabilitySource: leg.selection.probability_source,
      modelRunAt: null, odds: leg.odds ? { value: leg.odds, source: leg.selection.odds?.value === leg.odds ? 'provider_snapshot' : 'user' } : null,
      started: Boolean(leg.match.kickoff_utc && Date.parse(leg.match.kickoff_utc) <= now),
      state: 'draft', forecastChanged: false, currentAvailable: true, currentProbability: null, legId: null,
    }))
  }
  if (!slip) return []
  return slip.legs.map(leg => ({
    matchId: leg.match.id, home: leg.match.home?.name ?? '', away: leg.match.away?.name ?? '',
    competition: leg.match.competition?.name ?? null, kickoffUtc: leg.kickoff_utc,
    selection: leg.selection, probability: leg.probability, probabilitySource: leg.probability_source,
    modelRunAt: leg.model_run_at, odds: leg.odds ? { value: leg.odds.value, source: leg.odds.source } : null,
    started: leg.started || Boolean(leg.kickoff_utc && Date.parse(leg.kickoff_utc) <= now),
    state: leg.state, forecastChanged: leg.current.forecast_changed, currentAvailable: leg.current.available,
    currentProbability: leg.current.probability, legId: leg.id,
  }))
}

export function useSlips(userId: string | null | undefined, now: number = Date.now()) {
  const state = useSyncExternalStore(slipsStore.subscribe, slipsStore.getSnapshot, slipsStore.getSnapshot)
  useEffect(() => { void slipsStore.bindAccount(userId ?? null) }, [userId])
  const active = state.slips.find(s => s.id === state.activeId) ?? null
  const legs = dockLegsFrom(active, state.local, state.signedIn, now)
  const hasSelection = useCallback((matchId: string, selectionId: string) => slipsStore.hasSelection(matchId, selectionId), [])
  const fixtureTaken = useCallback((matchId: string) => slipsStore.fixtureTaken(matchId), [])
  return { ...state, active, legs, hasSelection, fixtureTaken, store: slipsStore }
}
