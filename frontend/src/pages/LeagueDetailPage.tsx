import React from 'react'
import { useParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { mockLeagues } from '@/data/mockData'
import Card from '@/components/ui/Card'

const LeagueDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const league = mockLeagues.find(l => l.id === id)

  if (!league) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center py-12">
            <h1 className="text-2xl font-bold text-white mb-4">League Not Found</h1>
            <p className="text-secondary-400">The requested league could not be found.</p>
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
          <div className="mb-8">
            <div className="flex items-center space-x-4 mb-4">
              <img src={league.logo} alt={league.name} className="h-16 w-16" />
              <div>
                <h1 className="text-3xl font-bold text-white">{league.name}</h1>
                <p className="text-secondary-400">{league.country} • {league.season}</p>
              </div>
            </div>
          </div>

          <Card>
            <Card.Body>
              <div className="text-center py-12">
                <h3 className="text-xl font-semibold text-white mb-4">Coming Soon</h3>
                <p className="text-secondary-400">
                  Detailed league information, standings, and fixtures will be available soon.
                </p>
              </div>
            </Card.Body>
          </Card>
        </div>
      </div>
    </>
  )
}

export default LeagueDetailPage
