import React from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { mockLeagues } from '@/data/mockData'
import Card from '@/components/ui/Card'

const LeaguesPage: React.FC = () => {
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
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {mockLeagues.map(league => (
              <Link key={league.id} to={`/league/${league.id}`}>
                <Card hover>
                  <Card.Body>
                    <div className="flex items-center space-x-4">
                      <img
                        src={league.logo}
                        alt={league.name}
                        className="h-12 w-12"
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
        </div>
      </div>
    </>
  )
}

export default LeaguesPage
