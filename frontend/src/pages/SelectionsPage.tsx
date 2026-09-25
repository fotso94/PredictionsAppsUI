import React, { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { Link, useLocation } from 'react-router-dom'
import clsx from 'clsx'
import Card from '@/components/ui/Card'
import { useT } from '@/i18n/react'
import { backendInstant, formatDateTime, formatPercentValue } from '@/i18n'
import useAuth from '@/hooks/useAuth'
import { describeSlipError, useSlips } from '@/services/slips.service'
import { selectionSentence, stateLabel } from '@/utils/marketLabels'
import type { ApiSlip, ApiSlipLeg, SlipStatus } from '@/types/markets'
import type { SignInHandoff } from '@/components/favourites/useMatchSaving'

/**
 * The reader's slips: drafts, saved combinations and bets recorded as placed elsewhere, each leg
 * with the state it reached once a result was stored and the rule that decided it.
 *
 * Every state word is one of five and each is defined by the backend (pending, won, lost, void,
 * unresolved). "Unresolved" is shown with the reason the backend gave, because it is the one state
 * a reader could mistake for a loss, and it is not one.
 */

type Filter = 'all' | SlipStatus

const LegLine: React.FC<{ leg: ApiSlipLeg }> = ({ leg }) => {
  const t = useT()
  const home = leg.match.home?.name ?? ''
  const away = leg.match.away?.name ?? ''
  const settlement = leg.settlement ?? {}
  const actual = typeof settlement.actual === 'string' ? settlement.actual : null
  const reason = typeof settlement.reason === 'string' ? settlement.reason : null
  const rule = typeof settlement.rule === 'string' ? settlement.rule : null
  return (
    <li className="rounded-lg bg-dark-800 px-3 py-2" data-testid="history-leg" data-state={leg.state}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm text-white">{home} v {away}</p>
          <p className="text-[11px] text-secondary-400">{leg.kickoff_utc ? formatDateTime(backendInstant(leg.kickoff_utc).at) : ''}{leg.match.competition ? ` · ${leg.match.competition.name}` : ''}</p>
          <p className="text-xs text-secondary-200">
            {selectionSentence(t, leg.selection, home, away)}
            <span className="ml-2 text-white">{leg.probability === null ? '—' : formatPercentValue(leg.probability * 100, 0)}</span>
            {leg.odds && <span className="ml-2 text-secondary-400">@ {leg.odds.value.toFixed(2)}</span>}
          </p>
        </div>
        <span className={clsx('rounded-md px-2 py-0.5 text-[11px] uppercase tracking-wide',
          leg.state === 'won' ? 'bg-success-500/20 text-success-300' : leg.state === 'lost' ? 'bg-danger-500/20 text-danger-300'
            : leg.state === 'void' ? 'bg-dark-700 text-secondary-300' : leg.state === 'unresolved' ? 'bg-warning-500/20 text-warning-200' : 'bg-dark-700 text-secondary-300')}
          data-testid="history-leg-state">
          {stateLabel(t, leg.state)}
        </span>
      </div>
      {leg.state === 'pending' && leg.started && <p className="mt-1 text-[11px] text-secondary-400">{t('selections.history.awaiting')}</p>}
      {actual && <p className="mt-1 text-[11px] text-secondary-400">{t('selections.history.actual', { actual })}</p>}
      {rule && leg.state !== 'pending' && <p className="text-[11px] text-secondary-500">{t('selections.history.settlementRule', { rule })}</p>}
      {leg.state === 'unresolved' && (
        <p className="text-[11px] text-warning-200">{t('selections.history.unresolvedNote')}{reason ? ` ${t('selections.history.settlementReason', { reason })}` : ''}</p>
      )}
    </li>
  )
}

const SlipCard: React.FC<{ slip: ApiSlip }> = ({ slip }) => {
  const t = useT()
  const { user } = useAuth()
  const { store, activeId } = useSlips(user?.id ?? null)
  const [error, setError] = useState<string | null>(null)
  const run = async (work: () => Promise<unknown>) => {
    setError(null)
    try { await work() } catch (failure) { setError(describeSlipError(failure)) }
  }
  const status = slip.status === 'recorded' ? t('selections.status.recorded') : slip.status === 'saved' ? t('selections.status.saved') : t('selections.status.draft')
  return (
    <Card data-testid="history-slip" data-status={slip.status} data-state={slip.state}>
      <Card.Header>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-base font-semibold text-white">{slip.name ?? t('selections.history.untitled')}</h2>
          <span className="text-xs text-secondary-300">{status} · {stateLabel(t, slip.state)}</span>
        </div>
        <p className="mt-1 text-[11px] text-secondary-400">
          {slip.status === 'recorded' && slip.recorded_at
            ? t('selections.history.recordedAt', { when: formatDateTime(backendInstant(slip.recorded_at).at) ?? '' })
            : t('selections.history.updated', { when: formatDateTime(backendInstant(slip.updated_at).at) ?? '' })}
          {slip.recorded_reference ? ` · ${t('selections.history.reference', { reference: slip.recorded_reference })}` : ''}
        </p>
        <p className="text-[11px] text-secondary-400" data-testid="history-counts">
          {t('selections.history.counts', { won: slip.counts.won, lost: slip.counts.lost, void: slip.counts.void, unresolved: slip.counts.unresolved, pending: slip.counts.pending })}
        </p>
      </Card.Header>
      <Card.Body>
        <ul className="space-y-2">{slip.legs.map(leg => <LegLine key={leg.id} leg={leg} />)}</ul>
        <div className="mt-3 space-y-1 text-xs text-secondary-300">
          {slip.price !== null ? (
            <p data-testid="history-price">
              {slip.counts.void > 0 ? t('selections.dock.priceOriginal', { price: slip.price.toFixed(2) }) : t('selections.dock.combinedPrice', { price: slip.price.toFixed(2) })}
            </p>
          ) : <p className="text-secondary-500">{slip.price_note}</p>}
          {slip.counts.void > 0 && slip.effective_price !== null && (
            <p data-testid="history-effective-price">{t('selections.dock.priceEffective', { price: slip.effective_price.toFixed(2) })} — {t('selections.history.voidNote')}</p>
          )}
          {slip.counts.void > 0 && slip.potential_withheld_reason && (
            <p className="text-warning-200" data-testid="history-potential-withheld">{t('selections.dock.potentialWithheld', { reason: slip.potential_withheld_reason })}</p>
          )}
          {slip.potential && <p data-testid="history-potential">{t('selections.dock.potential', { gross: `${slip.potential.gross_return} ${slip.potential.currency}`, net: `${slip.potential.net_profit} ${slip.potential.currency}` })}</p>}
          {slip.recorded_note && <p className="text-[11px] text-secondary-500">{slip.recorded_note}</p>}
        </div>
        {error && <p role="alert" className="mt-2 text-xs text-danger-300">{t('selections.dock.error', { reason: error })}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          {slip.status !== 'recorded' && (
            <button type="button" className={clsx('focus-ring rounded-md px-3 py-1 text-xs', activeId === slip.id ? 'bg-primary-600 text-white' : 'bg-dark-700 text-white hover:bg-dark-600')} onClick={() => store.select(slip.id)} data-testid="history-open">
              {t('selections.action.open')}
            </button>
          )}
          <button type="button" className="focus-ring rounded-md bg-dark-700 px-3 py-1 text-xs text-white hover:bg-dark-600" onClick={() => void run(() => store.duplicate(slip.id))} data-testid="history-duplicate">
            {t('selections.action.duplicate')}
          </button>
          {slip.status !== 'recorded' && (
            <button type="button" className="focus-ring rounded-md bg-dark-700 px-3 py-1 text-xs text-danger-300 hover:bg-dark-600" onClick={() => void run(() => store.remove(slip.id))} data-testid="history-delete">
              {t('selections.action.delete')}
            </button>
          )}
        </div>
      </Card.Body>
    </Card>
  )
}

const SelectionsPage: React.FC = () => {
  const t = useT()
  const location = useLocation()
  const { user, isAuthenticated } = useAuth()
  const slips = useSlips(user?.id ?? null)
  const [filter, setFilter] = useState<Filter>('all')
  const visible = slips.slips.filter(slip => filter === 'all' || slip.status === filter)
  const handoff: SignInHandoff = { from: location, at: Date.now() }
  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8">
      <Helmet><title>{t('selections.history.title')}</title></Helmet>
      <h1 className="text-2xl font-bold text-white">{t('selections.history.title')}</h1>
      <p className="mt-2 text-sm text-secondary-300">{t('selections.history.intro')}</p>
      <p className="mt-1 text-xs"><Link to="/selections/suggestions" className="focus-ring text-primary-300 underline" data-testid="history-suggestions-link">{t('selections.suggest.title')} →</Link></p>

      {!isAuthenticated && (
        <p className="mt-4 text-sm text-secondary-300" data-testid="history-signed-out">
          <Link to="/login" state={handoff} className="focus-ring text-primary-300 underline">{t('selections.history.signedOut')}</Link>
        </p>
      )}
      {isAuthenticated && slips.status === 'error' && (
        <p role="alert" className="mt-4 text-sm text-danger-300" data-testid="history-failed">{t('selections.history.loadFailed', { reason: slips.error ?? '' })}</p>
      )}
      {isAuthenticated && slips.status === 'ready' && (
        <>
          <div className="mt-4 flex flex-wrap gap-2" role="group">
            {(['all', 'draft', 'saved', 'recorded'] as Filter[]).map(value => (
              <button key={value} type="button" onClick={() => setFilter(value)}
                className={clsx('focus-ring rounded-full px-3 py-1 text-xs', filter === value ? 'bg-primary-600 text-white' : 'bg-dark-800 text-secondary-300 hover:text-white')}
                data-testid={`history-filter-${value}`} aria-pressed={filter === value}>
                {t(`selections.history.filter.${value}` as const)}
              </button>
            ))}
          </div>
          {visible.length === 0 ? (
            <p className="mt-4 text-sm text-secondary-400" data-testid="history-empty">{t('selections.history.empty')}</p>
          ) : (
            <div className="mt-4 space-y-4">{visible.map(slip => <SlipCard key={slip.id} slip={slip} />)}</div>
          )}
        </>
      )}
    </div>
  )
}

export default SelectionsPage
