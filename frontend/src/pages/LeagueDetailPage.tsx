import React, { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { League, Team, Match, LeagueStanding } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import MatchCard from '@/components/ui/MatchCard'
import { footballDataService } from '@/services/football-data.service'

const LeagueDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()

  const [league, setLeague] = useState<League | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [matches, setMatches] = useState<Match[]>([])
  const [standings, setStandings] = useState<LeagueStanding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [usingMockData, setUsingMockData] = useState(false)

  useEffect(() => {
    async function fetchLeagueData() {
      if (!id) return

      try {
        setLoading(true)
        setError(null)
        console.log('Fetching league details from API-Football for ID:', id)

        // First, get all leagues to find the current one
        const allLeagues = await footballDataService.getTopLeagues()
        const foundLeague = allLeagues.find(l => l.id === id)

        if (!foundLeague) {
          setError('League not found')
          setLoading(false)
          return
        }

        setLeague(foundLeague)

        // Fetch teams, standings, and fixtures in parallel
        console.log('Fetching teams, standings, and fixtures for league:', foundLeague.name)
        const leagueIdNum = parseInt(id)
        const [teamsData, standingsData, matchesData] = await Promise.all([
          footballDataService.getTeamsByLeague(leagueIdNum),
          footballDataService.getStandings(leagueIdNum),
          footballDataService.getFixturesByLeague(leagueIdNum, undefined, { next: 10 })
        ])

        console.log('Teams received:', teamsData.length, 'teams')
        console.log('Standings received:', standingsData.length, 'standings')
        console.log('Matches received:', matchesData.length, 'matches')

        // Filter to show only upcoming matches (future dates)
        const now = new Date()
        const upcomingMatches = matchesData.filter(match => {
          const matchDate = new Date(match.date)
          return matchDate >= now
        }).sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())

        console.log('Upcoming matches:', upcomingMatches.length, 'matches')

        setTeams(teamsData)
        setStandings(standingsData)
        setMatches(upcomingMatches)
        setUsingMockData(false)
      } catch (err) {
        console.error('Error fetching league data:', err)
        setError(err instanceof Error ? err.message : 'Failed to fetch league data from API-Football')
        setTeams([])
        setStandings([])
        setMatches([])
        setUsingMockData(false)
      } finally {
        setLoading(false)
      }
    }

    fetchLeagueData()
  }, [id])

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
            <div className="text-secondary-400">Loading league details...</div>
          </div>
        </div>
      </div>
    )
  }

  if (!league) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center py-12">
            <h1 className="text-2xl font-bold text-white mb-4">League Not Found</h1>
            <p className="text-secondary-400">The requested league could not be found.</p>
            {error && <p className="text-red-400 mt-2">Error: {error}</p>}
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      <Helmet>
        <title>{league.name} - Soccer Predictions</title>
        <meta name="description" content={`${league.name} predictions, standings, and match analysis for the ${league.season} season.`} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* League Header */}
          <div className="mb-8">
            <div className="flex items-center space-x-4 mb-4">
              <img
                src={league.logo}
                alt={league.name}
                className="h-16 w-16 object-contain"
                onError={(e) => {
                  e.currentTarget.src = '/leagues/default.svg'
                }}
              />
              <div>
                <h1 className="text-3xl font-bold text-white">{league.name}</h1>
                <p className="text-secondary-400">{league.country} • {league.season}</p>
              </div>
            </div>
            {usingMockData && (
              <Badge variant="warning">⚠️ Using Mock Data - Limited Information Available</Badge>
            )}
          </div>

          {/* Error State */}
          {error && !usingMockData ? (
            <Card>
              <Card.Body>
                <div className="text-center py-12">
                  <div className="text-red-400 mb-4">❌ {error}</div>
                  <Button onClick={() => window.location.reload()}>Retry</Button>
                </div>
              </Card.Body>
            </Card>
          ) : usingMockData ? (
            /* Mock Data State */
            <Card>
              <Card.Body>
                <div className="text-center py-12">
                  <h3 className="text-xl font-semibold text-white mb-4">Limited Data Available</h3>
                  <p className="text-secondary-400">
                    Detailed league information, standings, and fixtures are not available in mock mode.
                  </p>
                  <p className="text-secondary-500 mt-2 text-sm">
                    Please ensure the API is properly configured to view full league details.
                  </p>
                </div>
              </Card.Body>
            </Card>
          ) : (
            /* Real Data Display */
            <div className="space-y-8">
              {/* Standings Section */}
              {standings.length > 0 && (
                <Card>
                  <Card.Header>
                    <h2 className="text-xl font-semibold text-white">Standings</h2>
                  </Card.Header>
                  <Card.Body>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-dark-700">
                            <th className="text-left py-3 px-2 text-secondary-400 font-medium">#</th>
                            <th className="text-left py-3 px-2 text-secondary-400 font-medium">Team</th>
                            <th className="text-center py-3 px-2 text-secondary-400 font-medium">P</th>
                            <th className="text-center py-3 px-2 text-secondary-400 font-medium">W</th>
                            <th className="text-center py-3 px-2 text-secondary-400 font-medium">D</th>
                            <th className="text-center py-3 px-2 text-secondary-400 font-medium">L</th>
                            <th className="text-center py-3 px-2 text-secondary-400 font-medium">GF</th>
                            <th className="text-center py-3 px-2 text-secondary-400 font-medium">GA</th>
                            <th className="text-center py-3 px-2 text-secondary-400 font-medium">GD</th>
                            <th className="text-center py-3 px-2 text-secondary-400 font-medium">Pts</th>
                          </tr>
                        </thead>
                        <tbody>
                          {standings.map((standing) => (
                            <tr key={standing.team.id} className="border-b border-dark-800 hover:bg-dark-800 transition-colors">
                              <td className="py-3 px-2 text-white font-medium">{standing.position}</td>
                              <td className="py-3 px-2">
                                <div className="flex items-center space-x-2">
                                  <img
                                    src={standing.team.logo}
                                    alt={standing.team.name}
                                    className="h-6 w-6 object-contain"
                                    onError={(e) => {
                                      e.currentTarget.src = '/teams/default.svg'
                                    }}
                                  />
                                  <span className="text-white">{standing.team.name}</span>
                                </div>
                              </td>
                              <td className="text-center py-3 px-2 text-secondary-300">{standing.matchesPlayed}</td>
                              <td className="text-center py-3 px-2 text-green-400">{standing.wins}</td>
                              <td className="text-center py-3 px-2 text-yellow-400">{standing.draws}</td>
                              <td className="text-center py-3 px-2 text-red-400">{standing.losses}</td>
                              <td className="text-center py-3 px-2 text-secondary-300">{standing.goalsFor}</td>
                              <td className="text-center py-3 px-2 text-secondary-300">{standing.goalsAgainst}</td>
                              <td className="text-center py-3 px-2 text-secondary-300">{standing.goalDifference > 0 ? '+' : ''}{standing.goalDifference}</td>
                              <td className="text-center py-3 px-2 text-white font-bold">{standing.points}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card.Body>
                </Card>
              )}

              {/* Teams Section */}
              {teams.length > 0 && (
                <Card>
                  <Card.Header>
                    <h2 className="text-xl font-semibold text-white">Teams ({teams.length})</h2>
                  </Card.Header>
                  <Card.Body>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                      {teams.map(team => (
                        <div key={team.id} className="flex items-center space-x-3 p-3 rounded-lg bg-dark-800 hover:bg-dark-700 transition-colors">
                          <img
                            src={team.logo}
                            alt={team.name}
                            className="h-8 w-8 object-contain"
                            onError={(e) => {
                              e.currentTarget.src = '/teams/default.svg'
                            }}
                          />
                          <span className="text-sm text-white truncate">{team.name}</span>
                        </div>
                      ))}
                    </div>
                  </Card.Body>
                </Card>
              )}

              {/* Upcoming Matches Section */}
              {matches.length > 0 && (
                <div>
                  <h2 className="text-xl font-semibold text-white mb-4">Upcoming Matches</h2>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {matches.map(match => (
                      <MatchCard key={match.id} match={match} />
                    ))}
                  </div>
                </div>
              )}

              {/* No Data State */}
              {teams.length === 0 && matches.length === 0 && (
                <Card>
                  <Card.Body>
                    <div className="text-center py-12">
                      <h3 className="text-xl font-semibold text-white mb-4">No Data Available</h3>
                      <p className="text-secondary-400">
                        No teams or fixtures found for this league at the moment.
                      </p>
                    </div>
                  </Card.Body>
                </Card>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

export default LeagueDetailPage
