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
import apiClient from './api-client'
import { getErrorMessage } from '@/utils/errors'
import type { ApiMarketSelection, ApiMatchSummary, ApiSlip, ApiSlipLeg, SlipLegInput, SlipStatus } from '@/types/markets'

const API = '/api/v1/me/slips'
export const LOCAL_DRAFT_KEY = 'selections.draft.v1'

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
    signedIn: false, userId: null,
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
    this.session += 1
    const session = this.session
    if (!userId) {
      this.set({ signedIn: false, userId: null, slips: [], activeId: null, status: 'idle', error: null, handoffRefused: [] })
      return
    }
    this.set({ signedIn: true, userId, status: 'loading', error: null, handoffRefused: [] })
    try {
      await this.handOffLocalDraft(session)
      if (session !== this.session) return
      await this.load(session)
    } catch (error) {
      if (session !== this.session) return
      this.set({ status: 'error', error: getErrorMessage(error, 'Your slips could not be loaded.') })
    }
  }

  private async handOffLocalDraft(session: number): Promise<void> {
    const draft = this.state.local
    if (draft.legs.length === 0) return
    const refused: Array<{ leg: LocalLeg; reason: string }> = []
    let created: ApiSlip | null = null
    for (const leg of draft.legs) {
      const body: SlipLegInput = { match_id: leg.match.id, selection_id: leg.selection.selection_id, odds: leg.odds }
      try {
        const response: { data: ApiSlip } = created
          ? await apiClient.post<ApiSlip>(`${API}/${created.id}/legs`, body)
          : await apiClient.post<ApiSlip>(API, { name: null, legs: [body] })
        created = response.data
      } catch (error) {
        refused.push({ leg, reason: describeSlipError(error) })
      }
    }
    if (session !== this.session) return
    writeLocal(EMPTY_LOCAL)
    this.set({ local: EMPTY_LOCAL, handoffRefused: refused, activeId: created?.id ?? this.state.activeId })
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

  private apply(slip: ApiSlip, makeActive = true): ApiSlip {
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
    const slip = this.active()
    const body: SlipLegInput = { match_id: match.id, selection_id: selection.selection_id, odds: options.odds ?? null }
    if (!slip) {
      const { data } = await apiClient.post<ApiSlip>(API, { name: null, legs: [body] })
      this.apply(data)
      return
    }
    const existing = slip.legs.find(l => l.match.id === match.id)
    if (existing) {
      if (!options.replace) throw new SlipConflict('one_per_match')
      await apiClient.delete<ApiSlip>(`${API}/${slip.id}/legs/${existing.id}`)
    }
    const { data } = await apiClient.post<ApiSlip>(`${API}/${slip.id}/legs`, body)
    this.apply(data)
  }

  removeLeg = async (matchId: string): Promise<void> => {
    if (!this.state.signedIn) {
      const local = { legs: this.state.local.legs.filter(l => l.match.id !== matchId) }
      writeLocal(local)
      this.set({ local })
      return
    }
    const slip = this.active()
    const leg = slip?.legs.find(l => l.match.id === matchId)
    if (!slip || !leg) return
    const { data } = await apiClient.delete<ApiSlip>(`${API}/${slip.id}/legs/${leg.id}`)
    this.apply(data)
  }

  setLegOdds = async (matchId: string, odds: number | null): Promise<void> => {
    if (!this.state.signedIn) {
      const local = { legs: this.state.local.legs.map(l => (l.match.id === matchId ? { ...l, odds } : l)) }
      writeLocal(local)
      this.set({ local })
      return
    }
    const slip = this.active()
    const leg = slip?.legs.find(l => l.match.id === matchId)
    if (!slip || !leg) return
    const { data } = await apiClient.patch<ApiSlip>(`${API}/${slip.id}/legs/${leg.id}`, { odds })
    this.apply(data)
  }

  clearActive = async (): Promise<void> => {
    if (!this.state.signedIn) {
      writeLocal(EMPTY_LOCAL)
      this.set({ local: EMPTY_LOCAL })
      return
    }
    const slip = this.active()
    if (!slip) return
    if (slip.status === 'draft') {
      await apiClient.delete(`${API}/${slip.id}`)
      this.set({ slips: this.state.slips.filter(s => s.id !== slip.id), activeId: null })
    } else {
      this.set({ activeId: null })
    }
  }

  /* ------------------------------------------------------------------ slip-level writes (signed in) */

  update = async (id: string, patch: { name?: string | null; note?: string | null; status?: SlipStatus; currency?: string | null; stake?: string | null }): Promise<ApiSlip> => {
    const { data } = await apiClient.patch<ApiSlip>(`${API}/${id}`, patch)
    return this.apply(data, id === this.state.activeId)
  }

  record = async (id: string, body: { reference?: string | null; currency?: string | null; stake?: string | null; price?: number | null }): Promise<ApiSlip> => {
    const { data } = await apiClient.post<ApiSlip>(`${API}/${id}/record`, body)
    const recorded = this.apply(data, false)
    if (this.state.activeId === id) this.set({ activeId: null })
    return recorded
  }

  duplicate = async (id: string): Promise<ApiSlip> => {
    const { data } = await apiClient.post<ApiSlip>(`${API}/${id}/duplicate`)
    return this.apply(data, true)
  }

  remove = async (id: string): Promise<void> => {
    await apiClient.delete(`${API}/${id}`)
    this.set({ slips: this.state.slips.filter(s => s.id !== id), activeId: this.state.activeId === id ? null : this.state.activeId })
  }

  /** Test seam. */
  reset = (): void => {
    this.session += 1
    this.state = { status: 'idle', error: null, slips: [], activeId: null, local: readLocal(), handoffRefused: [], signedIn: false, userId: null }
    this.listeners.forEach(listener => listener())
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
