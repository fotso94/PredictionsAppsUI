import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { League } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { footballDataService } from '@/services/football-data.service'

const LeaguesPage: React.FC = () => {
  const [leagues, setLeagues] = useState<League[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [usingMockData, setUsingMockData] = useState(false)

  useEffect(() => {
    async function fetchLeagues() {
      try {
        setLoading(true)
        setError(null)
        console.log('LeaguesPage: Fetching top leagues from API-Football...')

        const data = await footballDataService.getTopLeagues()

        console.log('LeaguesPage: Leagues received:', data.length, 'leagues')
        console.log('LeaguesPage: Leagues data:', data)

        setLeagues(data)
        setUsingMockData(false)
      } catch (err) {
        console.error('LeaguesPage: Error fetching leagues:', err)
        setError(err instanceof Error ? err.message : 'Failed to fetch leagues from API-Football')
        setLeagues([])
        setUsingMockData(false)
      } finally {
        setLoading(false)
      }
    }

    fetchLeagues()
  }, [])

  return (
    <>
      <Helmet>
        <title>Leagues - Soccer Predictions</title>
        <meta name="description" content="Browse all available soccer leagues and competitions with predictions and analysis." />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">Leagues</h1>
            <p className="text-secondary-400">Browse all available leagues and competitions</p>
            {usingMockData && (
              <div className="mt-2">
                <Badge variant="warning">⚠️ Using Mock Data</Badge>
              </div>
            )}
          </div>

          {/* Loading State */}
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
              <div className="text-secondary-400">Loading leagues...</div>
            </div>
          ) : error && !usingMockData ? (
            /* Error State */
            <div className="text-center py-12">
              <div className="text-red-400 mb-4">❌ {error}</div>
              <Button onClick={() => window.location.reload()}>Retry</Button>
            </div>
          ) : leagues.length === 0 ? (
            /* No Leagues State */
            <div className="text-center py-12">
              <div className="text-secondary-400 mb-4">
                No leagues available. This might be a data issue.
              </div>
              <div className="text-secondary-500 text-sm mb-4">
                Check browser console for details.
              </div>
              <Button onClick={() => window.location.reload()}>Retry</Button>
            </div>
          ) : (
            /* Leagues Grid */
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {leagues.map(league => (
                <Link key={league.id} to={`/league/${league.id}`}>
                  <Card hover>
                    <Card.Body>
                      <div className="flex items-center space-x-4">
                        <img
                          src={league.logo}
                          alt={league.name}
                          className="h-12 w-12 object-contain"
                          onError={(e) => {
                            e.currentTarget.src = '/leagues/default.svg'
                          }}
                        />
                        <div>
                          <h3 className="text-lg font-semibold text-white">{league.name}</h3>
                          <p className="text-secondary-400">{league.country}</p>
                          <p className="text-secondary-500 text-sm">{league.season}</p>
                        </div>
                      </div>
                    </Card.Body>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

export default LeaguesPage
