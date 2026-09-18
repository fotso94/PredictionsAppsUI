import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { Match } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import ForecastProvenance, { ForecastAnomalies } from '@/components/ui/ForecastProvenance'
import DataFreshness from '@/components/ui/DataFreshness'
import { isPublished } from '@/components/ui/probability'
import { forecastAvailability } from '@/components/ui/forecastStatus'
import { onTeamLogoError } from '@/components/ui/imageFallback'
import EvidenceBrief from '@/components/match-detail/EvidenceBrief'
import MarketTable from '@/components/match-detail/MarketTable'
import RevisionHistory from '@/components/match-detail/RevisionHistory'
import SourcePanel, { AbsentSourceStrip } from '@/components/match-detail/SourcePanel'
import { confidenceStatement } from '@/components/match-detail/evidence'
import { footballDataService } from '@/services/football-data.service'
import { describeError } from '@/services/backend-match-data.service'
import { ProviderStatus } from '@/services/match-data-source'
import { providerLabel, betLabels } from '@/utils/predictionLabels'
import { isMatchLive, isMatchFinished, getMatchStatusText, getMatchStatusBadgeClasses } from '@/utils/matchFilters'

/**
 * One match, led by the evidence behind it.
 *
 * The page answers, in this order: what is known about the fixture, what is missing and why, how
 * current the model's view is — and only then the numbers themselves, attributed source by source.
 *
 * Three rules hold everywhere below:
 *  - a market a source did not publish is UNAVAILABLE, with the reason the backend gave. It is
 *    never 0%, never the complement of the other half, never borrowed from the other source;
 *  - a probability, a published confidence and a measured accuracy are three different things and
 *    are never allowed to read as one another (nothing here has been scored against a result yet);
 *  - a paused refresh is not a broken forecast. It is stated once, as its own clause, with the
 *    operational detail behind a disclosure instead of stacked beside the numbers.
 *
 * The fetch is the single-match endpoint, which reads what is stored and never triggers a provider
 * refresh, so opening this page spends no provider allowance.
 */
const MatchDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const [match, setMatch] = useState<Match | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null)
  /** Kept apart from `providerStatus === null`: "not asked yet" is not "we asked and could not". */
  const [statusLoaded, setStatusLoaded] = useState(false)

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
    footballDataService.getProviderStatus()
      .then(status => { if (!cancelled) setProviderStatus(status) })
      .finally(() => { if (!cancelled) setStatusLoaded(true) })
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
  const forecast = match.providerForecast ?? null
  const brief = match.brief ?? null
  const revisions = match.expertPredictionRevisions ?? []
  const forecastState = forecast?.state || 'unavailable'
  const showScore = (isMatchLive(match) || isMatchFinished(match)) && match.result
  const forecastAvail = forecastAvailability(providerStatus)

  /**
   * Whether each source stated a confidence of its own. GameForecastAPI publishes none, so its
   * badges are bands derived from the probability — which the panel says in words, because a
   * derived band must never be read as a validated accuracy.
   */
  const expertConfidencePublished = brief
    ? brief.reliability.expert.confidence_published
    : experts.some(expert => isPublished(expert.confidence_score))
  const modelConfidencePublished = brief
    ? brief.reliability.model.confidence_published
    : isPublished(forecast?.confidence_score)

  /**
   * The layout rule (and the reason the panels are built as a list): a source that published
   * nothing collapses to one line AFTER the analysis, so the available analysis gets the column —
   * and, on a phone, is not pushed below an empty box.
   */
  const expertPresent = experts.length > 0
  const modelPresent = forecast !== null
  const presentPanels = Number(expertPresent) + Number(modelPresent)

  /** The brief's own sentence for a source that has nothing here, when it supplied one. */
  const absentDetail = (source: 'model' | 'expert', fallback: string): string =>
    brief?.missing.find(entry => entry.scope === 'source' && entry.source === source)?.detail ?? fallback

  return (
    <>
      <Helmet>
        <title>{match.homeTeam.name} vs {match.awayTeam.name} - Match Analysis</title>
        <meta name="description" content={`Predictions for ${match.homeTeam.name} vs ${match.awayTeam.name} in ${match.league.name}`} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* Match Header */}
          <Card className="mb-6">
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

          {/*
            How current the page is, directly under the scoreline — the place the question is
            actually asked. It is a different scope from the evidence panel below, and says so:
            this is about our own refresh process (when fixtures, scores, results and forecasts
            last refreshed across the site), while the panel below is about the forecast held for
            THIS fixture. Neither is allowed to stand in for the other, and neither restates the
            other's facts.
          */}
          {statusLoaded && <DataFreshness status={providerStatus} className="mb-6" />}

          {/*
            The evidence first: who published anything, which markets they covered, how current it
            is, and every gap with the reason it exists. One statement about the state of the data,
            with the operational detail behind a disclosure rather than stacked beside the numbers.
          */}
          <EvidenceBrief
            brief={brief}
            forecast={forecast}
            experts={experts}
            availability={forecastAvail}
            className="mb-6"
          />

          <div className={`grid grid-cols-1 gap-6 ${presentPanels > 1 ? 'lg:grid-cols-2' : ''}`}>
            {expertPresent && (
              <SourcePanel
                source="expert"
                title="Expert Predictions"
                badge={<Badge variant="info">{experts.length} published</Badge>}
                confidenceNote={confidenceStatement(brief?.reliability.expert.detail, 'expert', experts[0])}
                derivedBands={!expertConfidencePublished}
                testId="expert-predictions"
                /* A correction appends; the view it replaced stays readable. */
                footer={revisions.length > 0
                  ? <RevisionHistory revisions={revisions} className="border-t border-dark-700 pt-4" />
                  : null}
              >
                {experts.map((expert, index) => (
                  <div key={index} className={index > 0 ? 'pt-6 border-t border-dark-700' : ''}>
                    <MarketTable prediction={expert} brief={brief} source="expert" />
                    {expert.analysis && (
                      <p className="mt-4 text-sm text-secondary-300 whitespace-pre-line">{expert.analysis}</p>
                    )}
                    <p className="mt-2 text-xs text-secondary-500">
                      Expert · {expert.source_type || 'expert_manual'}
                      {expert.publishedAt ? ` · published ${new Date(expert.publishedAt).toLocaleString()}` : ''}
                    </p>
                  </div>
                ))}
              </SourcePanel>
            )}

            {modelPresent && forecast && (
              <SourcePanel
                source="model"
                title="Model Forecast"
                badge={
                  <Badge variant={forecastState === 'available' ? 'success' : 'warning'}>
                    {providerLabel(forecast.providerName)}
                    {forecastState === 'stale' ? ' · out of date' : ''}
                    {forecastState === 'kickoff_passed' ? ' · for reference' : ''}
                  </Badge>
                }
                confidenceNote={confidenceStatement(brief?.reliability.model.detail, 'model', forecast)}
                derivedBands={!modelConfidencePublished}
                testId="provider-forecast"
              >
                {/*
                  Payload observations, kept visible and kept apart: a `warning` means the numbers do
                  not hold together and the reader needs it before reading them; a `note` is
                  bookkeeping and stays a quiet footnote.
                */}
                <ForecastAnomalies anomalies={forecast.anomalies} />
                <MarketTable prediction={forecast} brief={brief} source="model" />
                {forecast.analysis && (
                  <p className="text-sm text-secondary-300 whitespace-pre-line">{forecast.analysis}</p>
                )}
                {betLabels(forecast.recommendedBets).length > 0 && (
                  <div className="text-xs text-secondary-400">
                    <span className="text-secondary-300">Markets the provider flagged in its own payload: </span>
                    {betLabels(forecast.recommendedBets).join(' · ')}
                    <span className="block text-secondary-500">
                      Listed as the provider published them. Nothing on this page is advice to place a bet.
                    </span>
                  </div>
                )}
                {/* The three provider times, never collapsed into one "generated at". */}
                <ForecastProvenance prediction={forecast} className="border-t border-dark-700 pt-3" />
              </SourcePanel>
            )}
          </div>

          {/*
            Absence, stated but not given a column of its own.

            Only alongside analysis that IS here: when neither source published anything there is no
            column to protect, and the evidence panel above has already said what is missing and why.
            Repeating it twice more would be noise, not candour.
          */}
          {presentPanels === 1 && (
            <div className="mt-4 space-y-3">
              {!expertPresent && (
                <AbsentSourceStrip
                  source="expert"
                  detail={absentDetail('expert', 'No expert has published a prediction for this fixture.')}
                  note="Experts publish directly, so one appears here as soon as it is published."
                  testId="expert-missing"
                />
              )}
              {!modelPresent && (
                <AbsentSourceStrip
                  source="model"
                  detail={absentDetail('model', 'No model forecast has been retrieved for this fixture.')}
                  testId="forecast-missing"
                />
              )}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
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
