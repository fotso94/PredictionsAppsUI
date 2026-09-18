import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { UserIcon, CpuChipIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { Match, MatchPredictions } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import { Badge, ConfidenceBadge } from '@/components/ui/Badge'
import ForecastProvenance, { ForecastAnomalies } from '@/components/ui/ForecastProvenance'
import { marketLead, publishedSide, formatPercent, isPublished, UNAVAILABLE_TEXT, PublishedSide } from '@/components/ui/probability'
import { forecastAvailability } from '@/components/ui/forecastStatus'
import { onTeamLogoError } from '@/components/ui/imageFallback'
import { footballDataService } from '@/services/football-data.service'
import { describeError } from '@/services/backend-match-data.service'
import { ProviderStatus } from '@/services/match-data-source'
import { providerLabel, betLabels } from '@/utils/predictionLabels'
import { isMatchLive, isMatchFinished, getMatchStatusText, getMatchStatusBadgeClasses } from '@/utils/matchFilters'

const MarketRow: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex justify-between items-center gap-4">
    <span className="text-secondary-400">{label}</span>
    <div className="flex items-center space-x-2 text-right">{children}</div>
  </div>
)

const Unavailable: React.FC<{ text?: string }> = ({ text = UNAVAILABLE_TEXT }) => (
  <span className="text-xs text-secondary-500">{text}</span>
)

/** "Over 2.5 (Over 58% / Under unavailable)" — every half labelled, none inferred from the other. */
const TwoWayMarket: React.FC<{ sides: [PublishedSide | null, PublishedSide | null]; lead: { known: PublishedSide[]; leader: PublishedSide | null } }> = ({ sides, lead }) => (
  <span className="text-white font-medium">
    {lead.leader ? lead.leader.label : lead.known[0].label}
    <span className="text-secondary-400 font-normal">
      {' ('}
      {sides.map((side, index) => (
        <React.Fragment key={index}>
          {index > 0 && ' / '}
          {side ? `${side.label} ${formatPercent(side.value)}` : UNAVAILABLE_TEXT.toLowerCase()}
        </React.Fragment>
      ))}
      {')'}
    </span>
    {!lead.leader && <span className="text-secondary-500 font-normal"> — one side only</span>}
  </span>
)

/** One prediction (expert or model) rendered market by market; missing markets are shown as unavailable. */
const PredictionBlock: React.FC<{ prediction: MatchPredictions }> = ({ prediction }) => {
  const { bothTeamsToScore, totalGoals, correctScore } = prediction
  /**
   * Value-based, NOT flag-based: a prediction with no `markets` object at all used to slip past
   * `markets?.matchResult === false` and render a 0% / 0% / 0% match result. The market exists only
   * if the probabilities themselves exist, and an explicit `matchResult: false` also hides it.
   */
  const outcome = prediction.outcome && prediction.markets?.matchResult !== false ? prediction.outcome : null
  const best = outcome ? Math.max(outcome.homeWin, outcome.draw, outcome.awayWin) : null
  const bestLabel = outcome && best !== null
    ? (best === outcome.homeWin ? 'Home Win' : best === outcome.draw ? 'Draw' : 'Away Win')
    : null

  const bttsYes = publishedSide('Yes', bothTeamsToScore?.yes)
  const bttsNo = publishedSide('No', bothTeamsToScore?.no)
  const bttsLead = marketLead({ label: 'Yes', value: bothTeamsToScore?.yes }, { label: 'No', value: bothTeamsToScore?.no })

  const over25 = publishedSide('Over 2.5', totalGoals?.over25)
  const under25 = publishedSide('Under 2.5', totalGoals?.under25)
  const lead25 = marketLead({ label: 'Over 2.5', value: totalGoals?.over25 }, { label: 'Under 2.5', value: totalGoals?.under25 })

  const over35 = publishedSide('Over 3.5', totalGoals?.over35)
  const under35 = publishedSide('Under 3.5', totalGoals?.under35)
  const lead35 = marketLead({ label: 'Over 3.5', value: totalGoals?.over35 }, { label: 'Under 3.5', value: totalGoals?.under35 })

  return (
    <div className="space-y-4">
      <MarketRow label="Match Outcome">
        {outcome && bestLabel !== null && best !== null ? (
          <>
            <span className="text-white font-medium">{bestLabel} <span className="text-secondary-400 font-normal">({formatPercent(best)})</span></span>
            <ConfidenceBadge level={outcome.confidence} />
          </>
        ) : <Unavailable />}
      </MarketRow>
      {outcome ? (
        <div className="grid grid-cols-3 gap-2 text-center text-sm">
          <div className="rounded bg-dark-800 py-2"><div className="text-secondary-400 text-xs">Home</div><div className="text-white">{formatPercent(outcome.homeWin)}</div></div>
          <div className="rounded bg-dark-800 py-2"><div className="text-secondary-400 text-xs">Draw</div><div className="text-white">{formatPercent(outcome.draw)}</div></div>
          <div className="rounded bg-dark-800 py-2"><div className="text-secondary-400 text-xs">Away</div><div className="text-white">{formatPercent(outcome.awayWin)}</div></div>
        </div>
      ) : (
        <p className="rounded bg-dark-800 px-3 py-2 text-xs text-secondary-500" data-testid="outcome-unavailable">
          This source published no match-result (1X2) market for this fixture.
        </p>
      )}
      <MarketRow label="Both Teams to Score">
        {bothTeamsToScore && bttsLead.known.length > 0 ? (
          <>
            <TwoWayMarket sides={[bttsYes, bttsNo]} lead={bttsLead} />
            <ConfidenceBadge level={bothTeamsToScore.confidence} />
          </>
        ) : <Unavailable />}
      </MarketRow>
      <MarketRow label="Over/Under 2.5 Goals">
        {totalGoals && lead25.known.length > 0 ? (
          <>
            <TwoWayMarket sides={[over25, under25]} lead={lead25} />
            <ConfidenceBadge level={totalGoals.confidence} />
          </>
        ) : <Unavailable />}
      </MarketRow>
      <MarketRow label="Over/Under 3.5 Goals">
        {totalGoals && lead35.known.length > 0 ? (
          <TwoWayMarket sides={[over35, under35]} lead={lead35} />
        ) : <Unavailable />}
      </MarketRow>
      <MarketRow label="Most Likely Score">
        {correctScore ? (
          <span className="text-white font-medium" data-testid="correct-score">
            {correctScore.mostLikely} <span className="text-secondary-400 font-normal">({formatPercent(correctScore.probability)})</span>
            {/*
              The remainder the provider assigned to every scoreline it did not list. Without it a
              short list of scorelines reads as near-certainty; it is never folded into the listed ones.
            */}
            {isPublished(prediction.exactScoreOther) && (
              <span className="text-secondary-400 font-normal"> · other scorelines {formatPercent(prediction.exactScoreOther)}</span>
            )}
          </span>
        ) : <Unavailable />}
      </MarketRow>
    </div>
  )
}

const MatchDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const [match, setMatch] = useState<Match | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!id) return
      try {
        setLoading(true)
        setError(null)
        const result = await footballDataService.getMatch(id)
        if (!cancelled) setMatch(result)
      } catch (err) {
        if (!cancelled) setError(describeError(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [id])

  /**
   * Whether forecast refreshes are running. The single-match endpoint carries no forecast_sync
   * report, so the provider-status endpoint is what lets this page say "paused" instead of
   * "unavailable" when the daily allowance is spent.
   */
  useEffect(() => {
    let cancelled = false
    footballDataService.getProviderStatus().then(status => {
      if (!cancelled) setProviderStatus(status)
    })
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
          <div className="text-secondary-400">Loading match...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center py-12">
          <h1 className="text-2xl font-bold text-white mb-4">Match data unavailable</h1>
          <p className="text-red-400 mb-6">{error}</p>
          <Button onClick={() => window.location.reload()}>Retry</Button>
        </div>
      </div>
    )
  }

  if (!match) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center py-12">
            <h1 className="text-2xl font-bold text-white mb-4">Match Not Found</h1>
            <p className="text-secondary-400 mb-6">The requested match could not be found.</p>
            <Link to="/predictions/today" className="text-primary-400 hover:text-primary-300">Browse today's matches →</Link>
          </div>
        </div>
      </div>
    )
  }

  const experts = match.expertPredictions && match.expertPredictions.length > 0
    ? match.expertPredictions
    : match.expertPrediction ? [match.expertPrediction] : []
  const forecast = match.providerForecast
  const forecastState = forecast?.state || 'unavailable'
  const showScore = (isMatchLive(match) || isMatchFinished(match)) && match.result
  const forecastAvail = forecastAvailability(providerStatus)

  return (
    <>
      <Helmet>
        <title>{match.homeTeam.name} vs {match.awayTeam.name} - Match Analysis</title>
        <meta name="description" content={`Predictions for ${match.homeTeam.name} vs ${match.awayTeam.name} in ${match.league.name}`} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* Match Header */}
          <Card className="mb-8">
            <Card.Body>
              <div className="text-center">
                <div className="flex items-center justify-center space-x-4 sm:space-x-8 mb-6">
                  <div className="text-center flex-1">
                    <img src={match.homeTeam.logo} alt={match.homeTeam.name} className="h-16 w-16 mx-auto mb-2"
                      onError={onTeamLogoError} />
                    <h2 className="text-lg sm:text-xl font-bold text-white">{match.homeTeam.name}</h2>
                    <p className="text-secondary-400">Home</p>
                  </div>
                  <div className="text-center">
                    {showScore && match.result ? (
                      <div className={`text-3xl font-bold ${isMatchLive(match) ? 'text-green-500' : 'text-white'}`}>
                        {match.result.homeScore} - {match.result.awayScore}
                      </div>
                    ) : (
                      <div className="text-2xl font-bold text-secondary-400">VS</div>
                    )}
                    <span className={`${getMatchStatusBadgeClasses(match)} mt-2 inline-block`}>
                      {getMatchStatusText(match)}{isMatchLive(match) && match.minute ? ` ${match.minute}'` : ''}
                    </span>
                  </div>
                  <div className="text-center flex-1">
                    <img src={match.awayTeam.logo} alt={match.awayTeam.name} className="h-16 w-16 mx-auto mb-2"
                      onError={onTeamLogoError} />
                    <h2 className="text-lg sm:text-xl font-bold text-white">{match.awayTeam.name}</h2>
                    <p className="text-secondary-400">Away</p>
                  </div>
                </div>
                <div className="text-secondary-400">
                  <p>
                    {match.league.id ? <Link to={`/league/${match.league.id}`} className="hover:text-white">{match.league.name}</Link> : match.league.name}
                    {/* the provider gives the round as a bare number, which reads as noise without its label */}
                    {' '}• {match.date} • {match.time}
                    {match.round ? ` • ${/^\d+$/.test(String(match.round)) ? `Matchday ${match.round}` : match.round}` : ''}
                  </p>
                  <p>{match.venue}</p>
                </div>
              </div>
            </Card.Body>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Expert predictions */}
            <Card data-testid="expert-predictions">
              <Card.Header>
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-white flex items-center space-x-2">
                    <UserIcon className="h-5 w-5 text-blue-400" />
                    <span>Expert Predictions</span>
                  </h3>
                  <Badge variant="info">{experts.length} published</Badge>
                </div>
              </Card.Header>
              <Card.Body className="space-y-6">
                {experts.length === 0 ? (
                  <p className="text-secondary-400 text-sm">No expert has published a prediction for this match yet.</p>
                ) : experts.map((expert, index) => (
                  <div key={index} className={index > 0 ? 'pt-6 border-t border-dark-700' : ''}>
                    <PredictionBlock prediction={expert} />
                    {expert.analysis && (
                      <p className="mt-4 text-sm text-secondary-300 whitespace-pre-line">{expert.analysis}</p>
                    )}
                    <p className="mt-2 text-xs text-secondary-500">
                      Expert · {expert.source_type || 'expert_manual'}
                      {expert.publishedAt ? ` · published ${new Date(expert.publishedAt).toLocaleString()}` : ''}
                    </p>
                  </div>
                ))}
              </Card.Body>
            </Card>

            {/* Provider forecast */}
            <Card data-testid="provider-forecast">
              <Card.Header>
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-white flex items-center space-x-2">
                    <CpuChipIcon className="h-5 w-5 text-yellow-400" />
                    <span>Model Forecast</span>
                  </h3>
                  {forecast && <Badge variant={forecastState === 'available' ? 'success' : 'warning'}>{providerLabel(forecast.providerName)}</Badge>}
                </div>
              </Card.Header>
              <Card.Body className="space-y-4">
                {!forecast ? (
                  <div className="space-y-2" data-testid="forecast-missing">
                    {/* Paused refresh and absent forecast are different facts; never merge the wording. */}
                    <p className="text-secondary-400 text-sm">
                      {forecastAvail?.paused
                        ? 'No model forecast has been loaded for this match yet, and forecast updates are currently paused.'
                        : 'No model forecast is available for this match.'}
                    </p>
                    {forecastAvail && (
                      <p className="text-xs text-secondary-500">{forecastAvail.message}</p>
                    )}
                  </div>
                ) : (
                  <>
                    {forecastAvail?.paused && (
                      <p className="rounded-lg border border-dark-700 bg-dark-800 px-3 py-2 text-xs text-secondary-400">
                        {forecastAvail.message}
                      </p>
                    )}
                    <ForecastAnomalies anomalies={forecast.anomalies} />
                    {forecastState !== 'available' && (
                      <div className="flex items-start space-x-2 rounded-lg border border-yellow-700/60 bg-yellow-900/20 px-3 py-2 text-sm text-yellow-200">
                        <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" />
                        <span>
                          {forecastState === 'stale' && 'This forecast is outdated and is shown for reference only.'}
                          {forecastState === 'kickoff_passed' && 'This forecast was made before kick-off and is shown for reference only.'}
                          {forecast.stateReason ? ` (${forecast.stateReason})` : ''}
                        </span>
                      </div>
                    )}
                    <PredictionBlock prediction={forecast} />
                    {forecast.analysis && (
                      <p className="text-sm text-secondary-300 whitespace-pre-line">{forecast.analysis}</p>
                    )}
                    {betLabels(forecast.recommendedBets).length > 0 && (
                      <div className="text-xs text-secondary-400">
                        <span className="text-secondary-300">Model's suggested markets: </span>
                        {betLabels(forecast.recommendedBets).join(' · ')}
                      </div>
                    )}
                    <ForecastProvenance prediction={forecast} className="border-t border-dark-700 pt-3" />
                  </>
                )}
              </Card.Body>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-8">
            {/* Odds */}
            <Card>
              <Card.Header>
                <h3 className="text-lg font-semibold text-white">Betting Odds</h3>
              </Card.Header>
              <Card.Body>
                {match.odds ? (
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div><div className="text-secondary-400 text-sm">Home Win</div><div className="text-xl font-bold text-white">{match.odds.homeWin.toFixed(2)}</div></div>
                    <div><div className="text-secondary-400 text-sm">Draw</div><div className="text-xl font-bold text-white">{match.odds.draw.toFixed(2)}</div></div>
                    <div><div className="text-secondary-400 text-sm">Away Win</div><div className="text-xl font-bold text-white">{match.odds.awayWin.toFixed(2)}</div></div>
                  </div>
                ) : (
                  <p className="text-secondary-400 text-sm">Bookmaker odds are not available (no odds feed is configured).</p>
                )}
              </Card.Body>
            </Card>

            {/* Data provenance */}
            <Card>
              <Card.Header>
                <h3 className="text-lg font-semibold text-white">Match Data</h3>
              </Card.Header>
              <Card.Body className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-secondary-400">Fixture source</span><span className="text-white">{match.provider || 'unknown'}</span></div>
                {match.externalId && <div className="flex justify-between"><span className="text-secondary-400">Provider fixture id</span><span className="text-white font-mono text-xs">{match.externalId}</span></div>}
                {match.kickoffUtc && <div className="flex justify-between"><span className="text-secondary-400">Kick-off (UTC)</span><span className="text-white">{match.kickoffUtc.replace('T', ' ').replace('Z', '')}</span></div>}
                {match.lastSyncedAt && <div className="flex justify-between"><span className="text-secondary-400">Last synced</span><span className="text-white">{new Date(match.lastSyncedAt).toLocaleString()}</span></div>}
                <div className="pt-3 flex flex-wrap gap-3">
                  {match.homeTeam.id && <Link to={`/teams/${match.homeTeam.id}`} className="text-primary-400 hover:text-primary-300">{match.homeTeam.name} →</Link>}
                  {match.awayTeam.id && <Link to={`/teams/${match.awayTeam.id}`} className="text-primary-400 hover:text-primary-300">{match.awayTeam.name} →</Link>}
                </div>
              </Card.Body>
            </Card>
          </div>
        </div>
      </div>
    </>
  )
}

export default MatchDetailPage
