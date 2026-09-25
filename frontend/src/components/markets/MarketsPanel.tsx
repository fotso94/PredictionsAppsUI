import React, { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import Card from '@/components/ui/Card'
import Disclosure from '@/components/match-detail/Disclosure'
import { useT } from '@/i18n/react'
import { backendInstant, formatDateTime, formatPercentValue } from '@/i18n'
import useAuth from '@/hooks/useAuth'
import { getCapabilities, getMatchMarkets } from '@/services/markets.service'
import { SlipConflict, describeSlipError, useSlips } from '@/services/slips.service'
import { groupTitle, marketTitle, outcomeLabel } from '@/utils/marketLabels'
import { summaryOf } from '@/utils/matchSummary'
import type { Match } from '@/types'
import type { ApiCapabilityFamily, ApiMarket, ApiMarketEnvelope, ApiMarketSelection } from '@/types/markets'

/**
 * Every selection the stored model forecast supports for one fixture, grouped, each with its
 * published probability, where the number came from, what it would settle on, and an "Add"
 * control that puts it on the reader's slip.
 *
 * The panel says only what the backend's market contract says (backend/app/services/markets.py):
 * a probability is the provider's or arithmetic on the provider's, labelled which; a price appears
 * only when the payload carried one for exactly that selection; a market the provider did not
 * publish is listed as not published, with the backend's reason, never as 0%. Team names are the
 * provider's and are never translated; every other word comes from the catalogue.
 *
 * Nothing here is advice. The last line of the panel says so, and no wording above it contradicts it.
 */

export interface MarketsPanelProps {
  match: Match
  className?: string
}

const percent = (value: number | null): string => (value === null ? '—' : formatPercentValue(value * 100, 0))

const SelectionRow: React.FC<{
  selection: ApiMarketSelection
  home: string
  away: string
  onSlip: boolean
  fixtureTaken: boolean
  closed: boolean
  onAdd: (selection: ApiMarketSelection, replace: boolean) => Promise<void>
}> = ({ selection, home, away, onSlip, fixtureTaken, closed, onAdd }) => {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const add = async (replace: boolean) => {
    setBusy(true)
    setError(null)
    try {
      await onAdd(selection, replace)
      setConflict(false)
    } catch (failure) {
      if (failure instanceof SlipConflict) setConflict(true)
      else setError(describeSlipError(failure))
    } finally {
      setBusy(false)
    }
  }

  const label = outcomeLabel(t, selection, home, away)
  const price = selection.odds
  return (
    <li
      className="flex flex-col gap-1 rounded-lg bg-dark-800 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
      data-testid="market-selection"
      data-selection-id={selection.selection_id}
      data-available={selection.available}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-sm text-white">{label}</span>
          <span className="text-sm font-semibold text-white" data-testid="selection-probability">
            {selection.available ? percent(selection.probability) : t('probability.unavailable')}
          </span>
          {selection.probability_source === 'calculated' && selection.calculation && (
            <span className="text-[11px] text-secondary-400" title={selection.calculation.formula}>
              {t('selections.panel.calculated', { formula: selection.calculation.formula })}
            </span>
          )}
        </div>
        {!selection.available && selection.unavailable_reason && (
          <p className="text-[11px] text-secondary-500">{t('selections.panel.unavailable', { reason: selection.unavailable_reason })}</p>
        )}
        {price && (
          <p className="text-[11px] text-secondary-400" data-testid="selection-price">
            {t('selections.panel.priceProvider', {
              price: price.value.toFixed(2),
              when: price.captured_at ? (formatDateTime(backendInstant(price.captured_at).at) ?? '') : '—',
            })}
          </p>
        )}
        {selection.warnings.filter(w => w.severity === 'warning').map(w => (
          <p key={w.code} className="text-[11px] text-warning-200">{w.message}</p>
        ))}
        {conflict && (
          <p className="text-[11px] text-warning-200" role="status" data-testid="selection-conflict">
            {t('selections.dock.oneOnly')}{' '}
            <button type="button" className="focus-ring underline" onClick={() => void add(true)} disabled={busy}>
              {t('selections.action.replace')}
            </button>
          </p>
        )}
        {error && <p className="text-[11px] text-danger-300" role="alert">{t('selections.dock.error', { reason: error })}</p>}
      </div>
      <div className="flex-shrink-0">
        {onSlip ? (
          <span className="rounded-md border border-primary-500/40 px-2 py-1 text-xs text-primary-300" data-testid="selection-on-slip">
            {t('selections.action.added')}
          </span>
        ) : (
          <button
            type="button"
            className={clsx('focus-ring rounded-md px-2 py-1 text-xs font-medium',
              selection.available && !closed ? 'bg-primary-600 text-white hover:bg-primary-500' : 'bg-dark-700 text-secondary-500')}
            disabled={!selection.available || closed || busy}
            onClick={() => void add(fixtureTaken)}
            data-testid="selection-add"
          >
            {fixtureTaken && !onSlip ? t('selections.action.replace') : t('selections.action.add')}
          </button>
        )}
      </div>
    </li>
  )
}

const MarketBlock: React.FC<{
  market: ApiMarket
  home: string
  away: string
  closed: boolean
  hasSelection: (matchId: string, selectionId: string) => boolean
  fixtureTaken: boolean
  matchId: string
  onAdd: (selection: ApiMarketSelection, replace: boolean) => Promise<void>
}> = ({ market, home, away, closed, hasSelection, fixtureTaken, matchId, onAdd }) => {
  const t = useT()
  const title = marketTitle(t, market.market_id, market.line, home, away)
  const settlement = market.settlement
  return (
    <div className="space-y-1" data-testid="market-block" data-market-id={market.market_id} data-line={market.line ?? ''}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h4 className="text-sm font-medium text-white">{title}</h4>
        <span className="text-[11px] text-secondary-500">
          {settlement.capable
            ? t('selections.panel.settles', { rule: settlement.rule })
            : t('selections.panel.notTracked', { reason: settlement.reason ?? settlement.rule })}
        </span>
      </div>
      {market.warnings.filter(w => w.severity === 'warning').map(w => (
        <p key={w.code} className="text-[11px] text-warning-200">{w.message}</p>
      ))}
      {market.available ? (
        <ul className="space-y-1">
          {market.selections.map(selection => (
            <SelectionRow
              key={selection.selection_id}
              selection={selection}
              home={home}
              away={away}
              closed={closed}
              onSlip={hasSelection(matchId, selection.selection_id)}
              fixtureTaken={fixtureTaken}
              onAdd={onAdd}
            />
          ))}
        </ul>
      ) : (
        <p className="rounded-lg bg-dark-800 px-3 py-2 text-xs text-secondary-500" data-testid="market-unavailable">
          {t('selections.panel.unavailable', { reason: market.unavailable_reason ?? '' })}
        </p>
      )}
      {market.market_id === 'exact_score' && market.remainder !== null && market.remainder !== undefined && (
        <p className="text-[11px] text-secondary-500">{t('selections.panel.remainder', { value: percent(market.remainder) })}</p>
      )}
    </div>
  )
}

const MarketsPanel: React.FC<MarketsPanelProps> = ({ match, className }) => {
  const t = useT()
  const { user } = useAuth()
  const { hasSelection, fixtureTaken, store } = useSlips(user?.id ?? null)
  const [envelope, setEnvelope] = useState<ApiMarketEnvelope | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [missing, setMissing] = useState<ApiCapabilityFamily[]>([])
  const summary = useMemo(() => summaryOf(match), [match])
  const home = match.homeTeam.name
  const away = match.awayTeam.name

  useEffect(() => {
    let alive = true
    setEnvelope(null)
    setError(null)
    getMatchMarkets(match.id)
      .then(data => { if (alive) setEnvelope(data) })
      .catch(failure => { if (alive) setError(describeSlipError(failure)) })
    getCapabilities()
      .then(data => { if (alive) setMissing(data.families.filter(f => f.status === 'unavailable')) })
      .catch(() => { /* the "not offered" list is informational; its absence hides nothing that exists */ })
    return () => { alive = false }
  }, [match.id])

  const closed = envelope?.forecast.state === 'kickoff_passed'
  const onAdd = async (selection: ApiMarketSelection, replace: boolean) => {
    await store.addSelection(summary, selection, { replace })
  }

  const forecastLine = envelope && envelope.provider
    ? t('selections.panel.builtFrom', {
      provider: envelope.provider,
      retrieved: envelope.forecast.retrieved_at ? (formatDateTime(backendInstant(envelope.forecast.retrieved_at).at) ?? '') : '—',
      modelRun: envelope.forecast.model_run_at
        ? (formatDateTime(backendInstant(envelope.forecast.model_run_at).at) ?? '')
        : t('selections.panel.modelRunUnknown'),
    })
    : null

  return (
    <Card className={className} data-testid="markets-panel">
      <Card.Header>
        <h3 className="text-lg font-semibold text-white">{t('selections.panel.title')}</h3>
        <p className="mt-1 text-xs text-secondary-400">{t('selections.panel.intro')}</p>
      </Card.Header>
      <Card.Body>
        {error && <p role="alert" className="text-sm text-danger-300">{t('selections.dock.error', { reason: error })}</p>}
        {!error && !envelope && <p className="text-sm text-secondary-400">…</p>}
        {envelope && (!envelope.provider || envelope.reason) && (
          <p className="text-sm text-secondary-400" data-testid="markets-none">{t('selections.panel.noForecast')}</p>
        )}
        {envelope && envelope.provider && !envelope.reason && (
          <div className="space-y-5">
            <p className="text-[11px] text-secondary-500" data-testid="markets-provenance">
              {forecastLine}
              {envelope.forecast.snapshot_id && (
                <span className="block">{t('selections.panel.snapshot', { id: envelope.forecast.snapshot_id.slice(0, 8) })}</span>
              )}
            </p>
            {envelope.forecast.state === 'stale' && (
              <p className="rounded-lg border border-warning-500/40 bg-warning-500/10 px-3 py-2 text-xs text-warning-200" role="status">
                {t('selections.panel.state.stale', { reason: envelope.forecast.state_reason ?? '' })}
              </p>
            )}
            {closed && (
              <p className="rounded-lg border border-dark-700 bg-dark-800/60 px-3 py-2 text-xs text-secondary-300" role="status" data-testid="markets-closed">
                {t('selections.panel.state.kickoffPassed')}
              </p>
            )}
            {envelope.anomalies.filter(a => a.severity === 'warning').map(a => (
              <p key={a.code} className="text-xs text-warning-200">{a.message}</p>
            ))}
            {envelope.groups.map(group => (
              <section key={group.group} className="space-y-3" data-testid="market-group" data-group={group.group}>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-secondary-300">{groupTitle(t, group.group)}</h4>
                {group.markets.map(market => (
                  <MarketBlock
                    key={`${market.market_id}@${market.line ?? ''}`}
                    market={market}
                    home={home}
                    away={away}
                    closed={Boolean(closed)}
                    hasSelection={hasSelection}
                    fixtureTaken={fixtureTaken(match.id)}
                    matchId={match.id}
                    onAdd={onAdd}
                  />
                ))}
              </section>
            ))}
            {envelope.recommended_bets.length > 0 && (
              <section className="space-y-1" data-testid="provider-recommended">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-secondary-300">{t('selections.panel.recommended')}</h4>
                <ul className="text-xs text-secondary-300">
                  {envelope.recommended_bets.map(bet => (
                    <li key={bet.rank}>
                      {bet.resolved && bet.selection_id
                        ? (() => {
                          const found = envelope.groups.flatMap(g => g.markets).flatMap(m => m.selections)
                            .find(s => s.selection_id === bet.selection_id)
                          return found
                            ? `${marketTitle(t, found.market_id, found.line, home, away)}: ${outcomeLabel(t, found, home, away)} — ${percent(found.probability)}`
                            : String(bet.raw)
                        })()
                        : t('selections.panel.recommendedUnresolved', { raw: String(bet.raw), reason: bet.reason ?? '' })}
                    </li>
                  ))}
                </ul>
                <p className="text-[11px] text-secondary-500">{t('selections.panel.recommendedNote')}</p>
              </section>
            )}
            {missing.length > 0 && (
              <Disclosure summary={t('selections.panel.missing')} testId="markets-missing">
                <p className="mb-2 text-xs text-secondary-400">{t('selections.panel.missingIntro')}</p>
                <ul className="space-y-1 text-xs text-secondary-300">
                  {missing.map(family => (
                    <li key={family.family}>
                      <span className="text-white">{family.family.replace(/_/g, ' ')}</span>
                      {family.reason ? ` — ${family.reason}` : ''}
                    </li>
                  ))}
                </ul>
              </Disclosure>
            )}
            <p className="text-[11px] text-secondary-500" data-testid="markets-disclaimer">{t('selections.dock.disclaimer')}</p>
          </div>
        )}
      </Card.Body>
    </Card>
  )
}

export default MarketsPanel
