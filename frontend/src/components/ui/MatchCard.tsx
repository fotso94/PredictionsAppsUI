import React from 'react'
import { Link } from 'react-router-dom'
import { CalendarIcon, ClockIcon, MapPinIcon } from '@heroicons/react/24/outline'
import { Match } from '@/types'
import Card from './Card'
import { ConfidenceBadge } from './Badge'
import { format } from 'date-fns'

interface MatchCardProps {
  match: Match
  showPredictions?: boolean
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
      return format(new Date(dateString), 'MMM dd')
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

  return (
    <Card hover className="overflow-hidden">
      <Card.Body className="p-0">
        {/* League Header */}
        <div className="px-4 py-2 bg-dark-800 border-b border-dark-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <img 
                src={match.league.logo} 
                alt={match.league.name}
                className="h-4 w-4"
                onError={(e) => {
                  e.currentTarget.src = '/leagues/default.png'
                }}
              />
              <span className="text-xs text-secondary-400">{match.league.name}</span>
            </div>
            <div className="flex items-center space-x-2 text-xs text-secondary-400">
              <CalendarIcon className="h-3 w-3" />
              <span>{formatDate(match.date)}</span>
              <ClockIcon className="h-3 w-3" />
              <span>{formatTime(match.time)}</span>
            </div>
          </div>
        </div>

        {/* Teams */}
        <div className="p-4">
          <div className="flex items-center justify-between mb-4">
            {/* Home Team */}
            <div className="flex items-center space-x-3 flex-1">
              <img 
                src={match.homeTeam.logo} 
                alt={match.homeTeam.name}
                className="h-8 w-8"
                onError={(e) => {
                  e.currentTarget.src = '/teams/default.png'
                }}
              />
              <div>
                <div className="font-medium text-white">{match.homeTeam.name}</div>
                <div className="text-xs text-secondary-400">Home</div>
              </div>
            </div>

            {/* VS */}
            <div className="px-4">
              <div className="text-secondary-400 text-sm font-medium">VS</div>
            </div>

            {/* Away Team */}
            <div className="flex items-center space-x-3 flex-1 justify-end">
              <div className="text-right">
                <div className="font-medium text-white">{match.awayTeam.name}</div>
                <div className="text-xs text-secondary-400">Away</div>
              </div>
              <img 
                src={match.awayTeam.logo} 
                alt={match.awayTeam.name}
                className="h-8 w-8"
                onError={(e) => {
                  e.currentTarget.src = '/teams/default.png'
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
              {/* Predictions */}
              <div className="space-y-3">
                {/* Outcome Prediction */}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-secondary-400">Most Likely:</span>
                  <div className="flex items-center space-x-2">
                    <span className={`text-sm font-medium ${getOutcomeColor(
                      match.predictions.outcome.homeWin,
                      match.predictions.outcome.draw,
                      match.predictions.outcome.awayWin
                    )}`}>
                      {getMostLikelyOutcome(
                        match.predictions.outcome.homeWin,
                        match.predictions.outcome.draw,
                        match.predictions.outcome.awayWin
                      )}
                    </span>
                    <ConfidenceBadge level={match.predictions.outcome.confidence} />
                  </div>
                </div>

                {/* BTTS Prediction */}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-secondary-400">Both Teams to Score:</span>
                  <div className="flex items-center space-x-2">
                    <span className={`text-sm font-medium ${
                      match.predictions.bothTeamsToScore.yes > match.predictions.bothTeamsToScore.no
                        ? 'text-success-400'
                        : 'text-danger-400'
                    }`}>
                      {match.predictions.bothTeamsToScore.yes > match.predictions.bothTeamsToScore.no ? 'Yes' : 'No'}
                    </span>
                    <ConfidenceBadge level={match.predictions.bothTeamsToScore.confidence} />
                  </div>
                </div>

                {/* Over/Under Prediction */}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-secondary-400">Total Goals:</span>
                  <div className="flex items-center space-x-2">
                    <span className={`text-sm font-medium ${
                      match.predictions.totalGoals.over25 > match.predictions.totalGoals.under25
                        ? 'text-success-400'
                        : 'text-warning-400'
                    }`}>
                      {match.predictions.totalGoals.over25 > match.predictions.totalGoals.under25 ? 'Over 2.5' : 'Under 2.5'}
                    </span>
                    <ConfidenceBadge level={match.predictions.totalGoals.confidence} />
                  </div>
                </div>
              </div>

              {/* Odds */}
              <div className="mt-4 pt-4 border-t border-dark-700">
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
