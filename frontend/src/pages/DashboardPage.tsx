import React from 'react'
import { Helmet } from 'react-helmet-async'
import { mockUser, mockPredictions } from '@/data/mockData'
import Card from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

const DashboardPage: React.FC = () => {
  return (
    <>
      <Helmet>
        <title>Dashboard - Soccer Predictions</title>
        <meta name="description" content="Your personal dashboard with prediction history, statistics, and favorite teams." />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">Dashboard</h1>
            <p className="text-secondary-400">Welcome back, {mockUser.firstName}!</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <Card>
              <Card.Body className="text-center">
                <div className="text-2xl font-bold text-white">{mockUser.stats.totalPredictions}</div>
                <div className="text-secondary-400">Total Predictions</div>
              </Card.Body>
            </Card>
            <Card>
              <Card.Body className="text-center">
                <div className="text-2xl font-bold text-success-400">{mockUser.stats.accuracy}%</div>
                <div className="text-secondary-400">Accuracy Rate</div>
              </Card.Body>
            </Card>
            <Card>
              <Card.Body className="text-center">
                <div className="text-2xl font-bold text-primary-400">{mockUser.stats.streak.current}</div>
                <div className="text-secondary-400">Current Streak</div>
              </Card.Body>
            </Card>
          </div>

          <Card>
            <Card.Header>
              <h3 className="text-lg font-semibold text-white">Recent Predictions</h3>
            </Card.Header>
            <Card.Body>
              <div className="space-y-4">
                {mockPredictions.map(prediction => (
                  <div key={prediction.id} className="flex items-center justify-between p-4 bg-dark-800 rounded-lg">
                    <div>
                      <div className="text-white font-medium">{prediction.selection}</div>
                      <div className="text-secondary-400 text-sm">{prediction.market}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-white">{prediction.odds}</div>
                      <Badge variant={prediction.status === 'won' ? 'success' : prediction.status === 'lost' ? 'danger' : 'secondary'}>
                        {prediction.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            </Card.Body>
          </Card>
        </div>
      </div>
    </>
  )
}

export default DashboardPage
