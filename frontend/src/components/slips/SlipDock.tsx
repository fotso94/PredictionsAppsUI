import React, { useCallback, useEffect, useState } from 'react'
import clsx from 'clsx'
import { Link, useLocation } from 'react-router-dom'
import { useT } from '@/i18n/react'
import { backendInstant, formatDateTime, formatPercentValue } from '@/i18n'
import useAuth from '@/hooks/useAuth'
import { describeSlipError, useSlips, type DockLeg } from '@/services/slips.service'
import { selectionSentence, stateLabel } from '@/utils/marketLabels'
import { combinedPrice, combinedProbability, combinedProbabilityWithheld, slipText } from '@/utils/slipText'
import type { SignInHandoff } from '@/components/favourites/useMatchSaving'

/**
 * The persistent selection panel: a docked button on every page with the leg count, and the slip
 * itself when opened — legs, the price the reader's bookmaker offers for each, an optional stake,
 * and the four things a reader can do with it: copy it, save it, record it as placed elsewhere,
 * or clear it.
 *
 * A leg that has kicked off is flagged, not removed: the reader chose it, and a prematch selection
 * that is no longer prematch is a fact the reader should see, not one the panel should tidy away.
 * The flag is recomputed every thirty seconds so a draft left open crosses kickoff visibly.
 *
 * Money words are exact: a combined price exists only when every leg has a price; a return is a
 * quoted figure from that price; and "recorded" is the reader's own statement, never a confirmation.
 */

const TICK_MS = 30_000
const CURRENCIES = ['XAF', 'EUR', 'USD', 'GBP', 'NGN', 'GHS', 'KES', 'ZAR', 'CAD']

const useNow = (): number => {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS)
    return () => window.clearInterval(timer)
  }, [])
  return now
}

const LegRow: React.FC<{
  leg: DockLeg
  editable: boolean
  onRemove: () => Promise<void>
  onOdds: (odds: number | null) => Promise<void>
}> = ({ leg, editable, onRemove, onOdds }) => {
  const t = useT()
  const [odds, setOdds] = useState(leg.odds ? String(leg.odds.value) : '')
  useEffect(() => { setOdds(leg.odds ? String(leg.odds.value) : '') }, [leg.odds])
  const commit = async () => {
    const value = odds.trim().replace(',', '.')
    if (value === '') { if (leg.odds) await onOdds(null); return }
    const parsed = Number(value)
    if (!Number.isFinite(parsed) || parsed <= 1) return
    if (!leg.odds || Math.abs(leg.odds.value - parsed) > 1e-9) await onOdds(parsed)
  }
  const when = leg.kickoffUtc ? formatDateTime(backendInstant(leg.kickoffUtc).at) : null
  return (
    <li className="rounded-lg bg-dark-800 px-3 py-2" data-testid="slip-leg" data-match-id={leg.matchId} data-state={leg.state}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm text-white">{leg.home} v {leg.away}</p>
          <p className="text-[11px] text-secondary-400">{when ?? ''}{leg.competition ? ` · ${leg.competition}` : ''}</p>
          <p className="text-xs text-secondary-200" data-testid="slip-leg-selection">
            {selectionSentence(t, leg.selection, leg.home, leg.away)}
            <span className="ml-2 text-white">{leg.probability === null ? '—' : formatPercentValue(leg.probability * 100, 0)}</span>
          </p>
        </div>
        <div className="flex flex-shrink-0 flex-col items-end gap-1">
          {leg.state !== 'draft' && leg.state !== 'pending' && (
            <span className="text-[11px] uppercase tracking-wide text-secondary-300" data-testid="slip-leg-state">{stateLabel(t, leg.state)}</span>
          )}
          {editable && (
            <button type="button" className="focus-ring text-[11px] text-secondary-400 underline hover:text-white" onClick={() => void onRemove()} data-testid="slip-leg-remove">
              {t('selections.action.remove')}
            </button>
          )}
        </div>
      </div>
      {leg.started && (
        <p className="mt-1 text-[11px] text-warning-200" role="status" data-testid="slip-leg-started">{t('selections.dock.started')}</p>
      )}
      {leg.forecastChanged && leg.currentAvailable && (
        <p className="mt-1 text-[11px] text-secondary-400" data-testid="slip-leg-changed">
          {t('selections.dock.forecastChanged', { current: leg.currentProbability === null ? '—' : formatPercentValue(leg.currentProbability * 100, 0) })}
        </p>
      )}
      {leg.forecastChanged && !leg.currentAvailable && (
        <p className="mt-1 text-[11px] text-secondary-400" data-testid="slip-leg-changed">{t('selections.dock.unavailableNow')}</p>
      )}
      {editable && (
        <label className="mt-1 flex items-center gap-2 text-[11px] text-secondary-400">
          {t('selections.dock.oddsLabel')}
          <input
            type="text"
            inputMode="decimal"
            className="w-20 rounded border border-dark-600 bg-dark-900 px-2 py-0.5 text-xs text-white"
            placeholder={t('selections.dock.oddsPlaceholder')}
            value={odds}
            onChange={event => setOdds(event.target.value)}
            onBlur={() => void commit()}
            onKeyDown={event => { if (event.key === 'Enter') void commit() }}
            data-testid="slip-leg-odds"
          />
          {leg.odds?.source === 'provider_snapshot' && <span>{t('selections.copy.priceProvider')}</span>}
        </label>
      )}
    </li>
  )
}

const SlipDock: React.FC = () => {
  const t = useT()
  const now = useNow()
  const location = useLocation()
  const { user, isAuthenticated } = useAuth()
  const slips = useSlips(user?.id ?? null, now)
  const { active, legs, store, signedIn, handoffRefused } = slips
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [name, setName] = useState(active?.name ?? '')
  const [stake, setStake] = useState(active?.stake ?? '')
  const [currency, setCurrency] = useState(active?.currency ?? 'XAF')
  const [recording, setRecording] = useState(false)
  const [reference, setReference] = useState('')
  const [recordPrice, setRecordPrice] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => { setName(active?.name ?? ''); setStake(active?.stake ?? ''); setCurrency(active?.currency ?? 'XAF') }, [active?.id, active?.name, active?.stake, active?.currency])

  const run = useCallback(async (work: () => Promise<unknown>) => {
    setError(null)
    try { await work() } catch (failure) { setError(describeSlipError(failure)) }
  }, [])

  const editable = !active || active.status !== 'recorded'
  const price = active?.price ?? combinedPrice(legs)
  const voided = (active?.counts.void ?? 0) > 0
  const effective = active ? active.effective_price : price
  const missingPrices = legs.filter(l => !l.odds).length
  const chance = combinedProbability(legs)
  const chanceWithheld = combinedProbabilityWithheld(legs)

  const copy = async () => {
    const text = slipText(t, {
      name: active?.name ?? null, legs, price, priceSource: active?.price_source ?? (price !== null ? 'user' : null),
      stake: active?.stake ?? null, currency: active?.currency ?? null, potential: active?.potential ?? null,
      combinedProbability: chance,
    })
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      window.prompt(t('selections.action.copy'), text)
    }
  }

  const save = () => run(async () => {
    if (!active) return
    await store.update(active.id, { name: name.trim() || null, status: 'saved' })
    setNotice(t('selections.dock.saved', { name: name.trim() }))
  })

  const record = () => run(async () => {
    if (!active) return
    const parsedPrice = recordPrice.trim() ? Number(recordPrice.replace(',', '.')) : null
    await store.record(active.id, {
      reference: reference.trim() || null,
      price: parsedPrice && Number.isFinite(parsedPrice) && parsedPrice > 1 ? parsedPrice : null,
      currency: stake.trim() ? currency : null,
      stake: stake.trim() || null,
    })
    setRecording(false)
    setNotice(t('selections.dock.recorded'))
  })

  const commitStake = () => run(async () => {
    if (!active) return
    if ((active.stake ?? '') === stake.trim() && (active.currency ?? 'XAF') === currency) return
    await store.update(active.id, { currency: stake.trim() ? currency : null, stake: stake.trim() || '' })
  })

  const handoff: SignInHandoff = { from: location, at: Date.now() }
  const count = legs.length

  return (
    <>
      <button
        type="button"
        className={clsx('focus-ring fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium shadow-lg',
          count > 0 ? 'bg-primary-600 text-white hover:bg-primary-500' : 'bg-dark-800 text-secondary-200 hover:bg-dark-700')}
        onClick={() => setOpen(value => !value)}
        aria-expanded={open}
        aria-controls="slip-dock"
        data-testid="slip-dock-toggle"
        data-signed-in={signedIn}
      >
        <span>{open ? t('selections.action.hideSlip') : t('selections.action.showSlip')}</span>
        <span className="rounded-full bg-dark-950/40 px-2 text-xs" data-testid="slip-dock-count">{count}</span>
      </button>
      {open && (
        <aside
          id="slip-dock"
          className="fixed bottom-16 left-0 right-0 z-40 mx-auto max-h-[75vh] w-full overflow-y-auto rounded-t-xl border border-dark-700 bg-dark-900 p-4 shadow-2xl sm:left-auto sm:right-4 sm:w-96 sm:rounded-xl"
          aria-label={t('selections.dock.title')}
          data-testid="slip-dock"
        >
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="text-base font-semibold text-white">{t('selections.dock.title')}</h2>
            <span className="text-xs text-secondary-400">{t('selections.dock.count', { count })}</span>
          </div>
          {!signedIn && <p className="mb-2 text-[11px] text-secondary-400" data-testid="slip-dock-signed-out">{t('selections.dock.signedOut')}</p>}
          {active?.status === 'saved' && active.name && <p className="mb-2 text-xs text-secondary-300">{t('selections.dock.saved', { name: active.name })}</p>}
          {active?.status === 'recorded' && <p className="mb-2 text-xs text-secondary-300" data-testid="slip-dock-recorded">{t('selections.dock.recorded')}</p>}
          {handoffRefused.length > 0 && (
            <p className="mb-2 text-xs text-warning-200" role="status" data-testid="slip-dock-handoff">
              {t('selections.dock.handoffRefused', { count: handoffRefused.length, reasons: handoffRefused.map(r => r.reason).join('; ') })}
            </p>
          )}
          {notice && <p className="mb-2 text-xs text-primary-300" role="status" data-testid="slip-dock-notice">{notice}</p>}
          {error && <p className="mb-2 text-xs text-danger-300" role="alert" data-testid="slip-dock-error">{t('selections.dock.error', { reason: error })}</p>}

          {count === 0 ? (
            <p className="text-sm text-secondary-400" data-testid="slip-dock-empty">{t('selections.dock.empty')}</p>
          ) : (
            <ul className="space-y-2">
              {legs.map(leg => (
                <LegRow
                  key={leg.matchId}
                  leg={leg}
                  editable={editable}
                  onRemove={() => run(() => store.removeLeg(leg.matchId))}
                  onOdds={odds => run(() => store.setLegOdds(leg.matchId, odds))}
                />
              ))}
            </ul>
          )}

          {count > 0 && (
            <div className="mt-3 space-y-2 text-xs" data-testid="slip-dock-summary">
              {price !== null ? (
                <p className="text-white" data-testid="slip-combined-price">
                  {voided ? t('selections.dock.priceOriginal', { price: price.toFixed(2) }) : t('selections.dock.combinedPrice', { price: price.toFixed(2) })}
                </p>
              ) : (
                <p className="text-secondary-400" data-testid="slip-combined-price-missing">{t('selections.dock.combinedPriceMissing', { count: missingPrices })}</p>
              )}
              {voided && effective !== null && (
                <p className="text-white" data-testid="slip-effective-price">{t('selections.dock.priceEffective', { price: effective.toFixed(2) })}</p>
              )}
              {voided && active?.potential_withheld_reason && (
                <p className="text-warning-200" data-testid="slip-potential-withheld">{t('selections.dock.potentialWithheld', { reason: active.potential_withheld_reason })}</p>
              )}
              {chance !== null && (
                <p className="text-secondary-300" data-testid="slip-combined-probability">
                  {t('selections.dock.combinedProbability', { value: formatPercentValue(chance * 100, 1) })}
                  <span className="block text-[11px] text-secondary-500">{t('selections.dock.combinedProbabilityNote')}</span>
                </p>
              )}
              {chanceWithheld && (
                <p className="text-[11px] text-secondary-400" data-testid="slip-combined-probability-withheld">{t('selections.dock.combinedProbabilityWithheld')}</p>
              )}
              {signedIn && active && editable && (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col text-[11px] text-secondary-400">
                    {t('selections.dock.stakeLabel')}
                    <input type="text" inputMode="decimal" className="w-24 rounded border border-dark-600 bg-dark-900 px-2 py-1 text-xs text-white"
                      value={stake} onChange={e => setStake(e.target.value)} onBlur={() => void commitStake()} data-testid="slip-stake" />
                  </label>
                  <label className="flex flex-col text-[11px] text-secondary-400">
                    {t('selections.dock.currencyLabel')}
                    <select className="rounded border border-dark-600 bg-dark-900 px-2 py-1 text-xs text-white" value={currency}
                      onChange={e => setCurrency(e.target.value)} onBlur={() => void commitStake()} data-testid="slip-currency">
                      {CURRENCIES.map(code => <option key={code} value={code}>{code}</option>)}
                    </select>
                  </label>
                </div>
              )}
              {active?.potential && (
                <p className="text-secondary-300" data-testid="slip-potential">
                  {t('selections.dock.potential', { gross: `${active.potential.gross_return} ${active.potential.currency}`, net: `${active.potential.net_profit} ${active.potential.currency}` })}
                  <span className="block text-[11px] text-secondary-500">{t('selections.dock.potentialNote')}</span>
                </p>
              )}
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-2">
            {count > 0 && (
              <button type="button" className="focus-ring rounded-md bg-dark-700 px-3 py-1.5 text-xs text-white hover:bg-dark-600" onClick={() => void copy()} data-testid="slip-copy">
                {copied ? t('selections.action.copied') : t('selections.action.copy')}
              </button>
            )}
            {count > 0 && editable && (
              <button type="button" className="focus-ring rounded-md bg-dark-700 px-3 py-1.5 text-xs text-white hover:bg-dark-600" onClick={() => run(() => store.clearActive())} data-testid="slip-clear">
                {t('selections.action.clear')}
              </button>
            )}
            {signedIn && active && !editable && (
              <button type="button" className="focus-ring rounded-md bg-dark-700 px-3 py-1.5 text-xs text-white hover:bg-dark-600" onClick={() => run(() => store.duplicate(active.id))} data-testid="slip-duplicate">
                {t('selections.action.duplicate')}
              </button>
            )}
            {signedIn && active && !editable && (
              <button type="button" className="focus-ring rounded-md bg-dark-700 px-3 py-1.5 text-xs text-white hover:bg-dark-600" onClick={() => store.startNew()} data-testid="slip-new">
                {t('selections.action.new')}
              </button>
            )}
            <Link to="/selections" className="focus-ring rounded-md px-3 py-1.5 text-xs text-primary-300 hover:text-primary-200" data-testid="slip-history-link">
              {t('selections.history.title')} →
            </Link>
          </div>

          {count > 0 && !isAuthenticated && (
            <p className="mt-3 text-xs text-secondary-400" data-testid="slip-sign-in">
              <Link to="/login" state={handoff} className="focus-ring text-primary-300 underline">{t('selections.dock.saveHint')}</Link>
            </p>
          )}

          {count > 0 && signedIn && active && editable && (
            <div className="mt-3 space-y-2 border-t border-dark-700 pt-3" data-testid="slip-save-block">
              <label className="flex flex-col text-[11px] text-secondary-400">
                {t('selections.dock.nameLabel')}
                <input type="text" className="rounded border border-dark-600 bg-dark-900 px-2 py-1 text-xs text-white" value={name}
                  onChange={e => setName(e.target.value)} maxLength={120} data-testid="slip-name" />
              </label>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="focus-ring rounded-md bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-500 disabled:opacity-50"
                  onClick={() => void save()} disabled={!name.trim()} data-testid="slip-save">
                  {t('selections.action.save')}
                </button>
                <button type="button" className="focus-ring rounded-md bg-dark-700 px-3 py-1.5 text-xs text-white hover:bg-dark-600"
                  onClick={() => setRecording(value => !value)} data-testid="slip-record-open">
                  {t('selections.action.record')}
                </button>
              </div>
              {recording && (
                <div className="space-y-2 rounded-lg border border-dark-700 p-2" data-testid="slip-record-form">
                  <p className="text-[11px] text-secondary-400">{t('selections.dock.recordHint')}</p>
                  <label className="flex flex-col text-[11px] text-secondary-400">
                    {t('selections.dock.referenceLabel')}
                    <input type="text" className="rounded border border-dark-600 bg-dark-900 px-2 py-1 text-xs text-white" value={reference}
                      onChange={e => setReference(e.target.value)} maxLength={120} data-testid="slip-record-reference" />
                  </label>
                  <label className="flex flex-col text-[11px] text-secondary-400">
                    {t('selections.dock.priceLabel')}
                    <input type="text" inputMode="decimal" className="w-28 rounded border border-dark-600 bg-dark-900 px-2 py-1 text-xs text-white" value={recordPrice}
                      onChange={e => setRecordPrice(e.target.value)} data-testid="slip-record-price" />
                  </label>
                  <button type="button" className="focus-ring rounded-md bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-500"
                    onClick={() => void record()} data-testid="slip-record-confirm">
                    {t('selections.action.record')}
                  </button>
                </div>
              )}
            </div>
          )}
          <p className="mt-3 text-[11px] text-secondary-500" data-testid="slip-disclaimer">{t('selections.dock.disclaimer')}</p>
        </aside>
      )}
    </>
  )
}

export default SlipDock
