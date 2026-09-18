import React from 'react'
import { Link } from 'react-router-dom'
import { CalendarIcon, ClockIcon, MapPinIcon, UserIcon, CpuChipIcon } from '@heroicons/react/24/outline'
import { Match } from '@/types'
import Card from './Card'
import { ConfidenceBadge } from './Badge'
import { format } from 'date-fns'
import { isMatchLive, isMatchFinished, getMatchStatusText, getMatchStatusBadgeClasses } from '@/utils/matchFilters'
import { predictionSourceLabel } from '@/utils/predictionLabels'

interface MatchCardProps {
  match: Match
  showPredictions?: boolean
}

const forecastStateText = (state?: string | null): string | null => {
  switch (state) {
    case 'stale': return 'Model forecast is outdated and hidden until refreshed'
    case 'kickoff_passed': return 'Model forecast archived (match already started)'
    default: return null
  }
}

const MatchCard: React.FC<MatchCardProps> = ({ match, showPredictions = true }) => {
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
  const hiddenForecastNote = !prediction ? forecastStateText(match.providerForecast?.state) : null
  const showScore = (isMatchLive(match) || isMatchFinished(match)) && match.result

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
                onError={(e) => {
                  e.currentTarget.src = '/leagues/default.svg'
                }}
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
              {(isMatchLive(match) || match.status === 'postponed' || match.status === 'cancelled') && (
                <span className={getMatchStatusBadgeClasses(match)}>
                  {getMatchStatusText(match)}{isMatchLive(match) && match.minute ? ` ${match.minute}'` : ''}
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
                onError={(e) => {
                  e.currentTarget.src = '/teams/default.svg'
                }}
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
                  <div className={`text-2xl font-bold ${isMatchLive(match) ? 'text-green-500' : 'text-white'}`}>
                    {match.result.homeScore} - {match.result.awayScore}
                  </div>
                  {match.status === 'halftime' && (
                    <div className="text-xs text-secondary-400 mt-1">HT</div>
                  )}
                  {isMatchFinished(match) && (
                    <div className="text-xs text-secondary-400 mt-1">FT</div>
                  )}
                </div>
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
                onError={(e) => {
                  e.currentTarget.src = '/teams/default.svg'
                }}
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
                  {/* Outcome Prediction */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary-400">Most Likely:</span>
                    <div className="flex items-center space-x-2">
                      <span className={`text-sm font-medium ${getOutcomeColor(
                        prediction.outcome.homeWin,
                        prediction.outcome.draw,
                        prediction.outcome.awayWin
                      )}`}>
                        {getMostLikelyOutcome(
                          prediction.outcome.homeWin,
                          prediction.outcome.draw,
                          prediction.outcome.awayWin
                        )}
                        <span className="text-secondary-400 font-normal"> ({Math.round(Math.max(prediction.outcome.homeWin, prediction.outcome.draw, prediction.outcome.awayWin))}%)</span>
                      </span>
                      <ConfidenceBadge level={prediction.outcome.confidence} />
                    </div>
                  </div>

                  {/* BTTS Prediction */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary-400">Both Teams to Score:</span>
                    {prediction.bothTeamsToScore ? (
                      <div className="flex items-center space-x-2">
                        <span className={`text-sm font-medium ${
                          prediction.bothTeamsToScore.yes > prediction.bothTeamsToScore.no
                            ? 'text-success-400'
                            : 'text-danger-400'
                        }`}>
                          {prediction.bothTeamsToScore.yes > prediction.bothTeamsToScore.no ? 'Yes' : 'No'}
                          <span className="text-secondary-400 font-normal"> ({Math.round(Math.max(prediction.bothTeamsToScore.yes, prediction.bothTeamsToScore.no))}%)</span>
                        </span>
                        <ConfidenceBadge level={prediction.bothTeamsToScore.confidence} />
                      </div>
                    ) : (
                      <span className="text-xs text-secondary-500">Unavailable</span>
                    )}
                  </div>

                  {/* Over/Under Prediction */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary-400">Total Goals:</span>
                    {prediction.totalGoals ? (
                      <div className="flex items-center space-x-2">
                        <span className={`text-sm font-medium ${
                          prediction.totalGoals.over25 > prediction.totalGoals.under25
                            ? 'text-success-400'
                            : 'text-warning-400'
                        }`}>
                          {prediction.totalGoals.over25 > prediction.totalGoals.under25 ? 'Over 2.5' : 'Under 2.5'}
                          <span className="text-secondary-400 font-normal"> ({Math.round(Math.max(prediction.totalGoals.over25, prediction.totalGoals.under25))}%)</span>
                        </span>
                        <ConfidenceBadge level={prediction.totalGoals.confidence} />
                      </div>
                    ) : (
                      <span className="text-xs text-secondary-500">Unavailable</span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-dark-700 px-3 py-3 text-center" data-testid="match-prediction-unavailable">
                  <p className="text-sm text-secondary-400">No prediction available yet</p>
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
