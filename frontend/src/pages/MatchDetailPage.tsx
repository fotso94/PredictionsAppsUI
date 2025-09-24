import React from 'react'
import { useParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { mockTodayMatches, mockTomorrowMatches } from '@/data/mockData'
import Card from '@/components/ui/Card'
import { ConfidenceBadge } from '@/components/ui/Badge'


const MatchDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  
  const allMatches = [...mockTodayMatches, ...mockTomorrowMatches]
  const match = allMatches.find(m => m.id === id)

  if (!match) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center py-12">
            <h1 className="text-2xl font-bold text-white mb-4">Match Not Found</h1>
            <p className="text-secondary-400">The requested match could not be found.</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      <Helmet>
        <title>{match.homeTeam.name} vs {match.awayTeam.name} - Match Analysis</title>
        <meta name="description" content={`Detailed analysis and predictions for ${match.homeTeam.name} vs ${match.awayTeam.name} in ${match.league.name}`} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* Match Header */}
          <Card className="mb-8">
            <Card.Body>
              <div className="text-center">
                <div className="flex items-center justify-center space-x-8 mb-6">
                  <div className="text-center">
                    <img
                      src={match.homeTeam.logo}
                      alt={match.homeTeam.name}
                      className="h-16 w-16 mx-auto mb-2"
                      onError={(e) => {
                        e.currentTarget.src = '/teams/default.svg'
                      }}
                    />
                    <h2 className="text-xl font-bold text-white">{match.homeTeam.name}</h2>
                    <p className="text-secondary-400">Home</p>
                  </div>
                  <div className="text-2xl font-bold text-secondary-400">VS</div>
                  <div className="text-center">
                    <img
                      src={match.awayTeam.logo}
                      alt={match.awayTeam.name}
                      className="h-16 w-16 mx-auto mb-2"
                      onError={(e) => {
                        e.currentTarget.src = '/teams/default.svg'
                      }}
                    />
                    <h2 className="text-xl font-bold text-white">{match.awayTeam.name}</h2>
                    <p className="text-secondary-400">Away</p>
                  </div>
                </div>
                <div className="text-secondary-400">
                  <p>{match.league.name} • {match.date} • {match.time}</p>
                  <p>{match.venue}</p>
                </div>
              </div>
            </Card.Body>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Predictions */}
            <Card>
              <Card.Header>
                <h3 className="text-lg font-semibold text-white">Our Predictions</h3>
              </Card.Header>
              <Card.Body className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-secondary-400">Match Outcome</span>
                  <div className="flex items-center space-x-2">
                    <span className="text-white font-medium">
                      {match.predictions.outcome.homeWin > match.predictions.outcome.awayWin ? 'Home Win' : 'Away Win'}
                    </span>
                    <ConfidenceBadge level={match.predictions.outcome.confidence} />
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-secondary-400">Both Teams to Score</span>
                  <div className="flex items-center space-x-2">
                    <span className="text-white font-medium">
                      {match.predictions.bothTeamsToScore.yes > match.predictions.bothTeamsToScore.no ? 'Yes' : 'No'}
                    </span>
                    <ConfidenceBadge level={match.predictions.bothTeamsToScore.confidence} />
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-secondary-400">Total Goals</span>
                  <div className="flex items-center space-x-2">
                    <span className="text-white font-medium">
                      {match.predictions.totalGoals.over25 > match.predictions.totalGoals.under25 ? 'Over 2.5' : 'Under 2.5'}
                    </span>
                    <ConfidenceBadge level={match.predictions.totalGoals.confidence} />
                  </div>
                </div>
              </Card.Body>
            </Card>

            {/* Odds */}
            <Card>
              <Card.Header>
                <h3 className="text-lg font-semibold text-white">Betting Odds</h3>
              </Card.Header>
              <Card.Body>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <div className="text-secondary-400 text-sm">Home Win</div>
                    <div className="text-xl font-bold text-white">{match.odds.homeWin.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-secondary-400 text-sm">Draw</div>
                    <div className="text-xl font-bold text-white">{match.odds.draw.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-secondary-400 text-sm">Away Win</div>
                    <div className="text-xl font-bold text-white">{match.odds.awayWin.toFixed(2)}</div>
                  </div>
                </div>
              </Card.Body>
            </Card>
          </div>

          {/* Analysis */}
          <Card className="mt-8">
            <Card.Header>
              <h3 className="text-lg font-semibold text-white">Match Analysis</h3>
            </Card.Header>
            <Card.Body>
              <p className="text-secondary-300 mb-4">{match.predictions.analysis}</p>
              <div>
                <h4 className="text-white font-medium mb-2">Key Factors:</h4>
                <ul className="list-disc list-inside space-y-1">
                  {match.predictions.keyFactors.map((factor, index) => (
                    <li key={index} className="text-secondary-300">{factor}</li>
                  ))}
                </ul>
              </div>
            </Card.Body>
          </Card>

          {/* Team Stats */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-8">
            <Card>
              <Card.Header>
                <h3 className="text-lg font-semibold text-white">{match.homeTeam.name} Stats</h3>
              </Card.Header>
              <Card.Body className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-secondary-400">Matches Played</span>
                  <span className="text-white">{match.homeTeam.stats.matchesPlayed}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-400">Wins</span>
                  <span className="text-white">{match.homeTeam.stats.wins}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-400">Goals For</span>
                  <span className="text-white">{match.homeTeam.stats.goalsFor}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-400">Goals Against</span>
                  <span className="text-white">{match.homeTeam.stats.goalsAgainst}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-400">Form</span>
                  <div className="flex space-x-1">
                    {match.homeTeam.stats.form.map((result, index) => (
                      <span
                        key={index}
                        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                          result === 'W' ? 'bg-success-600 text-white' :
                          result === 'D' ? 'bg-warning-600 text-white' :
                          'bg-danger-600 text-white'
                        }`}
                      >
                        {result}
                      </span>
                    ))}
                  </div>
                </div>
              </Card.Body>
            </Card>

            <Card>
              <Card.Header>
                <h3 className="text-lg font-semibold text-white">{match.awayTeam.name} Stats</h3>
              </Card.Header>
              <Card.Body className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-secondary-400">Matches Played</span>
                  <span className="text-white">{match.awayTeam.stats.matchesPlayed}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-400">Wins</span>
                  <span className="text-white">{match.awayTeam.stats.wins}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-400">Goals For</span>
                  <span className="text-white">{match.awayTeam.stats.goalsFor}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-400">Goals Against</span>
                  <span className="text-white">{match.awayTeam.stats.goalsAgainst}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-400">Form</span>
                  <div className="flex space-x-1">
                    {match.awayTeam.stats.form.map((result, index) => (
                      <span
                        key={index}
                        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                          result === 'W' ? 'bg-success-600 text-white' :
                          result === 'D' ? 'bg-warning-600 text-white' :
                          'bg-danger-600 text-white'
                        }`}
                      >
                        {result}
                      </span>
                    ))}
                  </div>
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
