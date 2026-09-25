import React from 'react'
import { Link } from 'react-router-dom'
import { CalendarIcon, ClockIcon, MapPinIcon, UserIcon, CpuChipIcon } from '@heroicons/react/24/outline'
import { Match } from '@/types'
import { ForecastSyncStatus } from '@/services/match-data-source'
import Card from './Card'
import { ConfidenceBadge } from './Badge'
import { ForecastAnomalies } from './ForecastProvenance'
import { format } from 'date-fns'
import { isMatchLive, isMatchFinished, getMatchStatusText, getMatchStatusBadgeClasses } from '@/utils/matchFilters'
import { predictionSourceLabel, forecastSyncMessage } from '@/utils/predictionLabels'
import { marketLead, formatPercent, unavailableText } from './probability'
import { periodLines } from './scoreline'
import { resultDelay } from '@/utils/resultDelay'
import { ResultDelayLabel, ResultDelayNotice } from './ResultDelayNotice'
import { onTeamLogoError, onLeagueLogoError } from './imageFallback'

interface MatchCardProps {
  match: Match
  showPredictions?: boolean
  /**
   * Last forecast-refresh report from the list this card came from. When refreshes are paused the
   * empty state must say so instead of implying no forecast exists.
   */
  forecastSync?: ForecastSyncStatus | null
}

const forecastStateText = (state?: string | null): string | null => {
  switch (state) {
    case 'stale': return 'Model forecast is outdated and hidden until refreshed'
    case 'kickoff_passed': return 'Model forecast archived (match already started)'
    default: return null
  }
}

/** A market the source did not publish. Never rendered as 0%. */
const Unavailable: React.FC = () => (
  <span className="text-xs text-secondary-500">{unavailableText()}</span>
)

const MatchCard: React.FC<MatchCardProps> = ({ match, showPredictions = true, forecastSync = null }) => {
  const formatTime = (time: string) => {
    try {
      const [hours, minutes] = time.split(':')
      const date = new Date()
      date.setHours(parseInt(hours), parseInt(minutes))
      return format(date, 'HH:mm')
    } catch {
      return time
    }
  }

  const formatDate = (dateString: string) => {
    try {
      return format(new Date(`${dateString}T12:00:00Z`), 'MMM dd')
    } catch {
      return dateString
    }
  }

  const getOutcomeColor = (homeWin: number, draw: number, awayWin: number) => {
    const max = Math.max(homeWin, draw, awayWin)
    if (max === homeWin) return 'text-success-400'
    if (max === draw) return 'text-warning-400'
    return 'text-primary-400'
  }

  const getMostLikelyOutcome = (homeWin: number, draw: number, awayWin: number) => {
    const max = Math.max(homeWin, draw, awayWin)
    if (max === homeWin) return 'Home Win'
    if (max === draw) return 'Draw'
    return 'Away Win'
  }

  const prediction = match.predictions
  const isExpertPrediction = prediction?.source === 'expert'
  // A model forecast publishes no confidence score, so its badge is only the strength of the
  // probability. Saying otherwise would attribute a judgement the model never made.
  const confidenceBasis = isExpertPrediction ? 'published' : 'derived'
  const hiddenForecastNote = !prediction ? forecastStateText(match.providerForecast?.state) : null
  const pausedNote = !prediction ? forecastSyncMessage(forecastSync) : null
  /*
   * Read before anything asks the stored status what is happening. Past the backend's deadline for
   * a result, `isMatchLive` is still true and would put a pulsing LIVE badge, a minute and a
   * scoreline on a match that ended hours ago — so the delay withholds all three and the notice
   * below takes the scoreline's place.
   */
  const delay = resultDelay(match)
  const live = isMatchLive(match) && !delay
  const showScore = (live || isMatchFinished(match)) && match.result

  /**
   * The 1X2 market. `outcome` is null when the source published no match-result market, and
   * `markets.matchResult === false` says the same thing explicitly — either way the row must read
   * "Unavailable" rather than a green "Home Win (0%)" from a zero-filled block.
   */
  const outcome = prediction?.outcome && prediction.markets?.matchResult !== false ? prediction.outcome : null
  const btts = prediction?.bothTeamsToScore
    ? marketLead({ label: 'Yes', value: prediction.bothTeamsToScore.yes }, { label: 'No', value: prediction.bothTeamsToScore.no })
    : null
  const totals = prediction?.totalGoals
    ? marketLead({ label: 'Over 2.5', value: prediction.totalGoals.over25 }, { label: 'Under 2.5', value: prediction.totalGoals.under25 })
    : null

  return (
    <Card hover className="overflow-hidden">
      <Card.Body className="p-0">
        {/* League Header */}
        <div className="px-4 py-2 bg-dark-800 border-b border-dark-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 min-w-0">
              <img
                src={match.league.logo}
                alt={match.league.name}
                className="h-4 w-4"
                onError={onLeagueLogoError}
              />
              <span className="text-xs text-secondary-400 truncate">{match.league.name}</span>
              {prediction && (isExpertPrediction ? (
                <span className="inline-flex items-center space-x-1 text-xs text-blue-300" title="Published by one of our experts">
                  <UserIcon className="h-4 w-4 text-blue-400" />
                  <span className="hidden sm:inline">Expert</span>
                </span>
              ) : (
                <span className="inline-flex items-center space-x-1 text-xs text-yellow-300" title={predictionSourceLabel(prediction)}>
                  <CpuChipIcon className="h-4 w-4 text-yellow-400" />
                  <span className="hidden sm:inline">{predictionSourceLabel(prediction)}</span>
                </span>
              ))}
            </div>
            <div className="flex items-center space-x-2">
              {delay ? (
                <ResultDelayLabel delay={delay} />
              ) : (live || match.status === 'postponed' || match.status === 'cancelled') && (
                <span className={getMatchStatusBadgeClasses(match)}>
                  {getMatchStatusText(match)}{live && match.minute ? ` ${match.minute}'` : ''}
                </span>
              )}
              <div className="flex items-center space-x-2 text-xs text-secondary-400">
                <CalendarIcon className="h-3 w-3" />
                <span>{formatDate(match.date)}</span>
                <ClockIcon className="h-3 w-3" />
                <span>{formatTime(match.time)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Teams */}
        <div className="p-4">
          <div className="flex items-center justify-between mb-4">
            {/* Home Team */}
            <div className="flex items-center space-x-3 flex-1 min-w-0">
              <img 
                src={match.homeTeam.logo} 
                alt={match.homeTeam.name}
                className="h-8 w-8"
                onError={onTeamLogoError}
              />
              <div className="min-w-0">
                <div className="font-medium text-white truncate">{match.homeTeam.name}</div>
                <div className="text-xs text-secondary-400">Home</div>
              </div>
            </div>

            {/* VS or Score */}
            <div className="px-4">
              {showScore && match.result ? (
                <div className="text-center">
                  <div className={`text-2xl font-bold ${live ? 'text-green-500' : 'text-white'}`}>
                    {match.result.homeScore} - {match.result.awayScore}
                  </div>
                  {/*
                    The rest of the tie, beside the score and never folded into it. A shoot-out
                    is not a scoreline: 0-0 won 4-3 on penalties is the draw every market settles
                    on and a win to everyone who watched it, and the line above can only say one
                    of those. Empty for the ordinary match, which is most of them.
                  */}
                  {periodLines(match.result).map(line => (
                    <div key={line} className="mt-1 text-xs text-secondary-300" data-testid="match-score-period">
                      {line}
                    </div>
                  ))}
                  {match.status === 'halftime' && !delay && (
                    <div className="text-xs text-secondary-400 mt-1">HT</div>
                  )}
                  {isMatchFinished(match) && (
                    <div className="text-xs text-secondary-400 mt-1">FT</div>
                  )}
                </div>
              ) : delay ? (
                /* "VS" reads as a fixture still to come, and this one's kickoff has been and gone. */
                <ResultDelayNotice delay={delay} className="max-w-[12rem]" />
              ) : (
                <div className="text-secondary-400 text-sm font-medium">VS</div>
              )}
            </div>

            {/* Away Team */}
            <div className="flex items-center space-x-3 flex-1 justify-end min-w-0">
              <div className="text-right min-w-0">
                <div className="font-medium text-white truncate">{match.awayTeam.name}</div>
                <div className="text-xs text-secondary-400">Away</div>
              </div>
              <img 
                src={match.awayTeam.logo} 
                alt={match.awayTeam.name}
                className="h-8 w-8"
                onError={onTeamLogoError}
              />
            </div>
          </div>

          {/* Venue */}
          <div className="flex items-center space-x-1 text-xs text-secondary-400 mb-4">
            <MapPinIcon className="h-3 w-3" />
            <span>{match.venue}</span>
          </div>

          {showPredictions && (
            <>
              {prediction ? (
                <div className="space-y-3" data-testid="match-prediction">
                  <ForecastAnomalies anomalies={prediction.anomalies} />

                  {/* Outcome Prediction (1X2) */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary-400">Most Likely:</span>
                    {outcome ? (
                      <div className="flex items-center space-x-2" data-testid="match-outcome">
                        <span className={`text-sm font-medium ${getOutcomeColor(outcome.homeWin, outcome.draw, outcome.awayWin)}`}>
                          {getMostLikelyOutcome(outcome.homeWin, outcome.draw, outcome.awayWin)}
                          <span className="text-secondary-400 font-normal"> ({formatPercent(Math.max(outcome.homeWin, outcome.draw, outcome.awayWin))})</span>
                        </span>
                        <ConfidenceBadge level={outcome.confidence} basis={confidenceBasis} />
                      </div>
                    ) : (
                      <span data-testid="match-outcome-unavailable"><Unavailable /></span>
                    )}
                  </div>

                  {/* BTTS Prediction */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary-400">Both Teams to Score:</span>
                    {btts && btts.known.length > 0 && prediction.bothTeamsToScore ? (
                      <div className="flex items-center space-x-2">
                        {btts.leader ? (
                          <span className={`text-sm font-medium ${btts.leader.label === 'Yes' ? 'text-success-400' : 'text-danger-400'}`}>
                            {btts.leader.label}
                            <span className="text-secondary-400 font-normal"> ({formatPercent(btts.leader.value)})</span>
                          </span>
                        ) : (
                          // Only one half published: showing it as the favourite would mean inferring the other.
                          <span className="text-sm font-medium text-secondary-300">
                            {btts.known[0].label} {formatPercent(btts.known[0].value)}
                            <span className="text-secondary-500 font-normal"> · other side {unavailableText().toLowerCase()}</span>
                          </span>
                        )}
                        <ConfidenceBadge level={prediction.bothTeamsToScore.confidence} basis={confidenceBasis} />
                      </div>
                    ) : (
                      <Unavailable />
                    )}
                  </div>

                  {/* Over/Under Prediction */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary-400">Total Goals:</span>
                    {totals && totals.known.length > 0 && prediction.totalGoals ? (
                      <div className="flex items-center space-x-2">
                        {totals.leader ? (
                          <span className={`text-sm font-medium ${totals.leader.label.startsWith('Over') ? 'text-success-400' : 'text-warning-400'}`}>
                            {totals.leader.label}
                            <span className="text-secondary-400 font-normal"> ({formatPercent(totals.leader.value)})</span>
                          </span>
                        ) : (
                          <span className="text-sm font-medium text-secondary-300">
                            {totals.known[0].label} {formatPercent(totals.known[0].value)}
                            <span className="text-secondary-500 font-normal"> · other side {unavailableText().toLowerCase()}</span>
                          </span>
                        )}
                        <ConfidenceBadge level={prediction.totalGoals.confidence} basis={confidenceBasis} />
                      </div>
                    ) : (
                      <Unavailable />
                    )}
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-dark-700 px-3 py-3 text-center" data-testid="match-prediction-unavailable">
                  {/* A paused refresh is not the same as "no forecast exists" — say which it is. */}
                  <p className="text-sm text-secondary-400">
                    {pausedNote ? 'Forecast updates are paused' : 'No prediction available yet'}
                  </p>
                  {pausedNote && <p className="text-xs text-secondary-500 mt-1">{pausedNote}</p>}
                  {hiddenForecastNote && <p className="text-xs text-secondary-500 mt-1">{hiddenForecastNote}</p>}
                </div>
              )}

              {/* Odds */}
              <div className="mt-4 pt-4 border-t border-dark-700">
                {match.odds ? (
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <div className="text-xs text-secondary-400">1</div>
                      <div className="text-sm font-medium text-white">{match.odds.homeWin.toFixed(2)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-secondary-400">X</div>
                      <div className="text-sm font-medium text-white">{match.odds.draw.toFixed(2)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-secondary-400">2</div>
                      <div className="text-sm font-medium text-white">{match.odds.awayWin.toFixed(2)}</div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center text-xs text-secondary-500">Bookmaker odds unavailable</div>
                )}
              </div>
            </>
          )}
        </div>

        {/* View Details Link */}
        <div className="px-4 py-3 bg-dark-800 border-t border-dark-700">
          <Link 
            to={`/match/${match.id}`}
            className="text-primary-400 hover:text-primary-300 text-sm font-medium transition-colors"
          >
            View Full Analysis →
          </Link>
        </div>
      </Card.Body>
    </Card>
  )
}

export default MatchCard
