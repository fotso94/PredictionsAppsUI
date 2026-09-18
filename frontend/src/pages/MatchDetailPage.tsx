import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { UserIcon, CpuChipIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { Match, MatchPredictions } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import { Badge, ConfidenceBadge } from '@/components/ui/Badge'
import { footballDataService } from '@/services/football-data.service'
import { describeError } from '@/services/backend-match-data.service'
import { providerLabel, betLabels } from '@/utils/predictionLabels'
import { isMatchLive, isMatchFinished, getMatchStatusText, getMatchStatusBadgeClasses } from '@/utils/matchFilters'

const pctText = (value: number) => `${Math.round(value)}%`

const MarketRow: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex justify-between items-center gap-4">
    <span className="text-secondary-400">{label}</span>
    <div className="flex items-center space-x-2 text-right">{children}</div>
  </div>
)

const Unavailable: React.FC<{ text?: string }> = ({ text = 'Unavailable' }) => (
  <span className="text-xs text-secondary-500">{text}</span>
)

/** One prediction (expert or model) rendered market by market; missing markets are shown as unavailable. */
const PredictionBlock: React.FC<{ prediction: MatchPredictions }> = ({ prediction }) => {
  const { outcome, bothTeamsToScore, totalGoals, correctScore } = prediction
  const best = Math.max(outcome.homeWin, outcome.draw, outcome.awayWin)
  const bestLabel = best === outcome.homeWin ? 'Home Win' : best === outcome.draw ? 'Draw' : 'Away Win'
  return (
    <div className="space-y-4">
      <MarketRow label="Match Outcome">
        {prediction.markets?.matchResult === false ? <Unavailable /> : (
          <>
            <span className="text-white font-medium">{bestLabel} <span className="text-secondary-400 font-normal">({pctText(best)})</span></span>
            <ConfidenceBadge level={outcome.confidence} />
          </>
        )}
      </MarketRow>
      {prediction.markets?.matchResult !== false && (
        <div className="grid grid-cols-3 gap-2 text-center text-sm">
          <div className="rounded bg-dark-800 py-2"><div className="text-secondary-400 text-xs">Home</div><div className="text-white">{pctText(outcome.homeWin)}</div></div>
          <div className="rounded bg-dark-800 py-2"><div className="text-secondary-400 text-xs">Draw</div><div className="text-white">{pctText(outcome.draw)}</div></div>
          <div className="rounded bg-dark-800 py-2"><div className="text-secondary-400 text-xs">Away</div><div className="text-white">{pctText(outcome.awayWin)}</div></div>
        </div>
      )}
      <MarketRow label="Both Teams to Score">
        {bothTeamsToScore ? (
          <>
            <span className="text-white font-medium">
              {bothTeamsToScore.yes > bothTeamsToScore.no ? 'Yes' : 'No'}
              <span className="text-secondary-400 font-normal"> (Yes {pctText(bothTeamsToScore.yes)} / No {pctText(bothTeamsToScore.no)})</span>
            </span>
            <ConfidenceBadge level={bothTeamsToScore.confidence} />
          </>
        ) : <Unavailable />}
      </MarketRow>
      <MarketRow label="Over/Under 2.5 Goals">
        {totalGoals ? (
          <>
            <span className="text-white font-medium">
              {totalGoals.over25 > totalGoals.under25 ? 'Over 2.5' : 'Under 2.5'}
              <span className="text-secondary-400 font-normal"> (Over {pctText(totalGoals.over25)} / Under {pctText(totalGoals.under25)})</span>
            </span>
            <ConfidenceBadge level={totalGoals.confidence} />
          </>
        ) : <Unavailable />}
      </MarketRow>
      <MarketRow label="Over/Under 3.5 Goals">
        {totalGoals && totalGoals.over35 !== null && totalGoals.under35 !== null ? (
          <span className="text-white font-medium">
            {totalGoals.over35 > totalGoals.under35 ? 'Over 3.5' : 'Under 3.5'}
            <span className="text-secondary-400 font-normal"> (Over {pctText(totalGoals.over35)} / Under {pctText(totalGoals.under35)})</span>
          </span>
        ) : <Unavailable />}
      </MarketRow>
      <MarketRow label="Most Likely Score">
        {correctScore ? (
          <span className="text-white font-medium">{correctScore.mostLikely} <span className="text-secondary-400 font-normal">({pctText(correctScore.probability)})</span></span>
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
                      onError={(e) => { e.currentTarget.src = '/teams/default.svg' }} />
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
                      onError={(e) => { e.currentTarget.src = '/teams/default.svg' }} />
                    <h2 className="text-lg sm:text-xl font-bold text-white">{match.awayTeam.name}</h2>
                    <p className="text-secondary-400">Away</p>
                  </div>
                </div>
                <div className="text-secondary-400">
                  <p>
                    {match.league.id ? <Link to={`/league/${match.league.id}`} className="hover:text-white">{match.league.name}</Link> : match.league.name}
                    {' '}• {match.date} • {match.time}{match.round ? ` • ${match.round}` : ''}
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
                  <p className="text-secondary-400 text-sm">No model forecast is available for this match.</p>
                ) : (
                  <>
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
                    <p className="text-xs text-secondary-500">
                      {providerLabel(forecast.providerName)}
                      {forecast.generatedAt ? ` · generated ${new Date(forecast.generatedAt).toLocaleString()}` : ''}
                      {forecast.matchConfidence ? ` · fixture match: ${forecast.matchConfidence}` : ''}
                    </p>
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
