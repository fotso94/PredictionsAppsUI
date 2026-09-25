import React, { useCallback, useEffect, useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { Link } from 'react-router-dom'
import Card from '@/components/ui/Card'
import { useT } from '@/i18n/react'
import { backendInstant, formatDateTime, formatPercentValue } from '@/i18n'
import useAuth from '@/hooks/useAuth'
import { getSuggestions } from '@/services/markets.service'
import { SlipConflict, describeSlipError, useSlips } from '@/services/slips.service'
import { footballDataService } from '@/services/football-data.service'
import { marketTitle, outcomeLabel } from '@/utils/marketLabels'
import type { League } from '@/types'
import type { ApiCombination, ApiSuggestedLeg, ApiSuggestions, MarketId } from '@/types/markets'

/**
 * Suggested combinations: the deterministic service's output, with every leg explained and every
 * shortfall stated. Generating or regenerating never costs a provider request — the backend reads
 * stored forecasts only — so the form can be used freely.
 */

const MARKET_CHOICES: MarketId[] = [
  'match_result', 'double_chance', 'draw_no_bet', 'total_goals', 'both_teams_score',
  'home_team_goals', 'away_team_goals', 'first_half_result', 'exact_score', 'team_to_score_first',
]
const DEFAULT_MARKETS: MarketId[] = MARKET_CHOICES.slice(0, 8)

const percent = (value: number): string => formatPercentValue(value * 100, 0)

const LegCard: React.FC<{ leg: ApiSuggestedLeg; onAdd: (leg: ApiSuggestedLeg, replace: boolean) => Promise<void>; onSlip: boolean }> = ({ leg, onAdd, onSlip }) => {
  const t = useT()
  const [conflict, setConflict] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const home = leg.match.home?.name ?? ''
  const away = leg.match.away?.name ?? ''
  const add = async (replace: boolean) => {
    setError(null)
    try { await onAdd(leg, replace); setConflict(false) } catch (failure) {
      if (failure instanceof SlipConflict) setConflict(true)
      else setError(describeSlipError(failure))
    }
  }
  const age = leg.why.forecast.age_hours
  const why = age === null
    ? t('selections.suggest.whyAgeUnknown', { probability: percent(leg.why.probability), provider: leg.why.forecast.provider ?? '' })
    : t('selections.suggest.why', { probability: percent(leg.why.probability), provider: leg.why.forecast.provider ?? '',
      age: t('selections.suggest.ageHours', { count: Math.round(age) }), state: leg.why.forecast.state ?? '' })
  return (
    <li className="rounded-lg bg-dark-800 px-3 py-2" data-testid="suggested-leg" data-match-id={leg.match.id}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm text-white">{home} v {away}</p>
          <p className="text-[11px] text-secondary-400">
            {leg.match.kickoff_utc ? formatDateTime(backendInstant(leg.match.kickoff_utc).at) : ''}{leg.match.competition ? ` · ${leg.match.competition.name}` : ''} · {t('selections.suggest.rank', { rank: leg.why.rank })}
          </p>
          <p className="text-xs text-secondary-200" data-testid="suggested-selection">
            {marketTitle(t, leg.selection.market_id, leg.selection.line, home, away)}: {outcomeLabel(t, leg.selection, home, away)}
            <span className="ml-2 font-semibold text-white">{percent(leg.why.probability)}</span>
          </p>
          <p className="text-[11px] text-secondary-400">{why}</p>
          {leg.why.provider_odds && (
            <p className="text-[11px] text-secondary-400">{t('selections.panel.priceProvider', { price: leg.why.provider_odds.value.toFixed(2), when: leg.why.provider_odds.captured_at ? (formatDateTime(backendInstant(leg.why.provider_odds.captured_at).at) ?? '') : '—' })}</p>
          )}
          {!leg.why.settlement.capable && <p className="text-[11px] text-warning-200">{t('selections.panel.notTracked', { reason: leg.why.settlement.reason ?? leg.why.settlement.rule })}</p>}
          {leg.why.warnings.map(w => <p key={w.code} className="text-[11px] text-warning-200">{t('selections.suggest.warnings', { message: w.message })}</p>)}
          {conflict && (
            <p className="text-[11px] text-warning-200" role="status">
              {t('selections.dock.oneOnly')}{' '}
              <button type="button" className="focus-ring underline" onClick={() => void add(true)}>{t('selections.action.replace')}</button>
            </p>
          )}
          {error && <p className="text-[11px] text-danger-300" role="alert">{t('selections.dock.error', { reason: error })}</p>}
        </div>
        {onSlip ? (
          <span className="rounded-md border border-primary-500/40 px-2 py-1 text-xs text-primary-300">{t('selections.action.added')}</span>
        ) : (
          <button type="button" className="focus-ring rounded-md bg-primary-600 px-2 py-1 text-xs font-medium text-white hover:bg-primary-500" onClick={() => void add(false)} data-testid="suggested-add">
            {t('selections.action.add')}
          </button>
        )}
      </div>
    </li>
  )
}

const SuggestionsPage: React.FC = () => {
  const t = useT()
  const { user } = useAuth()
  const { hasSelection, store } = useSlips(user?.id ?? null)
  const [legs, setLegs] = useState(3)
  const [minProbability, setMinProbability] = useState(60)
  const [maxProbability, setMaxProbability] = useState(95)
  const [markets, setMarkets] = useState<MarketId[]>(DEFAULT_MARKETS)
  const [competition, setCompetition] = useState('')
  const [days, setDays] = useState(7)
  const [oddsMin, setOddsMin] = useState('')
  const [oddsMax, setOddsMax] = useState('')
  const [includeStale, setIncludeStale] = useState(false)
  const [leagues, setLeagues] = useState<League[]>([])
  const [result, setResult] = useState<ApiSuggestions | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    footballDataService.getTopLeagues().then(setLeagues).catch(() => setLeagues([]))
  }, [])

  const generate = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const to = new Date(Date.now() + days * 86_400_000).toISOString()
      const data = await getSuggestions({
        legs, min_probability: minProbability / 100, max_probability: maxProbability / 100, markets,
        competitions: competition ? [competition] : undefined, to,
        odds_min: oddsMin ? Number(oddsMin.replace(',', '.')) : undefined,
        odds_max: oddsMax ? Number(oddsMax.replace(',', '.')) : undefined,
        include_stale: includeStale,
      })
      setResult(data)
    } catch (failure) {
      setError(describeSlipError(failure))
    } finally {
      setLoading(false)
    }
  }, [legs, minProbability, maxProbability, markets, competition, days, oddsMin, oddsMax, includeStale])

  useEffect(() => { void generate() }, [generate])

  const addLeg = async (leg: ApiSuggestedLeg, replace: boolean) => {
    await store.addSelection(leg.match, leg.selection, { replace, odds: leg.why.provider_odds?.value ?? null })
  }
  const addAll = async (combination: ApiCombination) => {
    for (const leg of combination.legs) {
      if (hasSelection(leg.match.id, leg.selection.selection_id)) continue
      try { await addLeg(leg, false) } catch (failure) { if (!(failure instanceof SlipConflict)) throw failure }
    }
  }

  const toggleMarket = (market: MarketId) => setMarkets(current => (current.includes(market) ? current.filter(m => m !== market) : [...current, market]))

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8">
      <Helmet><title>{t('selections.suggest.title')}</title></Helmet>
      <h1 className="text-2xl font-bold text-white">{t('selections.suggest.title')}</h1>
      <p className="mt-2 text-sm text-secondary-300">{t('selections.suggest.intro')}</p>
      <p className="mt-1 text-xs"><Link to="/selections" className="focus-ring text-primary-300 underline">{t('selections.history.title')}</Link></p>

      <Card className="mt-4">
        <Card.Body>
          <form className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" onSubmit={event => { event.preventDefault(); void generate() }} data-testid="suggest-form">
            <label className="flex flex-col text-xs text-secondary-300">
              {t('selections.suggest.legs')}
              <input type="number" min={2} max={6} value={legs} onChange={e => setLegs(Number(e.target.value))} className="mt-1 rounded border border-dark-600 bg-dark-900 px-2 py-1 text-sm text-white" data-testid="suggest-legs" />
            </label>
            <label className="flex flex-col text-xs text-secondary-300">
              {t('selections.suggest.minProbability')} ({minProbability}%)
              <input type="range" min={0} max={100} value={minProbability} onChange={e => setMinProbability(Number(e.target.value))} className="mt-1" data-testid="suggest-min" />
            </label>
            <label className="flex flex-col text-xs text-secondary-300">
              {t('selections.suggest.maxProbability')} ({maxProbability}%)
              <input type="range" min={0} max={100} value={maxProbability} onChange={e => setMaxProbability(Number(e.target.value))} className="mt-1" data-testid="suggest-max" />
            </label>
            <label className="flex flex-col text-xs text-secondary-300">
              {t('selections.suggest.competitions')}
              <select value={competition} onChange={e => setCompetition(e.target.value)} className="mt-1 rounded border border-dark-600 bg-dark-900 px-2 py-1 text-sm text-white" data-testid="suggest-competition">
                <option value="">{t('selections.suggest.anyCompetition')}</option>
                {leagues.map(league => <option key={league.id} value={league.id}>{league.name}</option>)}
              </select>
            </label>
            <label className="flex flex-col text-xs text-secondary-300">
              {t('selections.suggest.window')}
              <select value={days} onChange={e => setDays(Number(e.target.value))} className="mt-1 rounded border border-dark-600 bg-dark-900 px-2 py-1 text-sm text-white" data-testid="suggest-days">
                {[1, 2, 3, 7, 14].map(n => <option key={n} value={n}>{t('selections.suggest.days', { count: n })}</option>)}
              </select>
            </label>
            <div className="flex flex-col text-xs text-secondary-300">
              {t('selections.suggest.oddsRange')}
              <div className="mt-1 flex gap-2">
                <input type="text" inputMode="decimal" value={oddsMin} onChange={e => setOddsMin(e.target.value)} placeholder="1.50" className="w-20 rounded border border-dark-600 bg-dark-900 px-2 py-1 text-sm text-white" data-testid="suggest-odds-min" />
                <input type="text" inputMode="decimal" value={oddsMax} onChange={e => setOddsMax(e.target.value)} placeholder="3.00" className="w-20 rounded border border-dark-600 bg-dark-900 px-2 py-1 text-sm text-white" data-testid="suggest-odds-max" />
              </div>
              <span className="mt-1 text-[11px] text-secondary-500">{t('selections.suggest.oddsRangeNote')}</span>
            </div>
            <fieldset className="sm:col-span-2 lg:col-span-3">
              <legend className="text-xs text-secondary-300">{t('selections.suggest.markets')}</legend>
              <div className="mt-1 flex flex-wrap gap-2">
                {MARKET_CHOICES.map(market => (
                  <label key={market} className="flex items-center gap-1 rounded border border-dark-600 px-2 py-1 text-xs text-secondary-200">
                    <input type="checkbox" checked={markets.includes(market)} onChange={() => toggleMarket(market)} data-testid={`suggest-market-${market}`} />
                    {marketTitle(t, market, null, t('selections.market.homeTeam'), t('selections.market.awayTeam')).trim()}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="flex items-center gap-2 text-xs text-secondary-300">
              <input type="checkbox" checked={includeStale} onChange={e => setIncludeStale(e.target.checked)} data-testid="suggest-stale" />
              {t('selections.suggest.includeStale')}
            </label>
            <div className="sm:col-span-2 lg:col-span-3">
              <button type="submit" className="focus-ring rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-500 disabled:opacity-50" disabled={loading} data-testid="suggest-generate">
                {t('selections.suggest.generate')}
              </button>
            </div>
          </form>
        </Card.Body>
      </Card>

      {error && <p role="alert" className="mt-4 text-sm text-danger-300" data-testid="suggest-error">{t('selections.suggest.loadFailed', { reason: error })}</p>}

      {result && (
        <div className="mt-4 space-y-4" data-testid="suggest-results">
          <p className="text-xs text-secondary-400" data-testid="suggest-generated">
            {t('selections.suggest.generatedAt', { when: formatDateTime(backendInstant(result.generated_at).at) ?? '', qualifying: result.pool.qualifying, considered: result.pool.fixtures_in_window })}
            <span className="block">{t('selections.suggest.excluded', {
              stale: result.pool.excluded.stale ?? 0, noForecast: result.pool.excluded.no_forecast ?? 0,
              belowThreshold: result.pool.excluded.below_threshold ?? 0, aboveCeiling: result.pool.excluded.above_ceiling ?? 0,
              oddsFilter: result.pool.excluded.odds_filter ?? 0,
            })}</span>
          </p>
          {result.combinations.length === 0 && (
            <p className="rounded-lg border border-dark-700 bg-dark-800/60 px-3 py-2 text-sm text-secondary-200" role="status" data-testid="suggest-none">
              {t('selections.suggest.none', { reason: result.shortfall ?? '' })}
            </p>
          )}
          {result.combinations.length > 0 && result.shortfall && (
            <p className="text-xs text-warning-200" role="status" data-testid="suggest-shortfall">{t('selections.suggest.shortfall', { reason: result.shortfall })}</p>
          )}
          {result.combinations.map(combination => (
            <Card key={combination.index} data-testid="suggested-combination">
              <Card.Header>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="text-base font-semibold text-white">{t('selections.suggest.combination', { index: combination.index })}</h2>
                  <button type="button" className="focus-ring rounded-md bg-dark-700 px-3 py-1 text-xs text-white hover:bg-dark-600" onClick={() => void addAll(combination)} data-testid="suggested-add-all">
                    {t('selections.action.addAll')}
                  </button>
                </div>
                <p className="mt-1 text-xs text-secondary-300" data-testid="suggested-combined">
                  {t('selections.dock.combinedProbability', { value: formatPercentValue(combination.combined_probability.value * 100, 1) })}
                  <span className="block text-[11px] text-secondary-500">{t('selections.dock.combinedProbabilityNote')}</span>
                  <span className="block text-[11px] text-secondary-500">
                    {combination.combined_odds ? t('selections.suggest.combinedOdds', { price: combination.combined_odds.value.toFixed(2) }) : t('selections.suggest.noCombinedOdds')}
                  </span>
                </p>
              </Card.Header>
              <Card.Body>
                <ul className="space-y-2">
                  {combination.legs.map(leg => (
                    <LegCard key={leg.match.id} leg={leg} onAdd={addLeg} onSlip={hasSelection(leg.match.id, leg.selection.selection_id)} />
                  ))}
                </ul>
              </Card.Body>
            </Card>
          ))}
          <p className="text-[11px] text-secondary-500">{t('selections.dock.disclaimer')}</p>
        </div>
      )}
    </div>
  )
}

export default SuggestionsPage
