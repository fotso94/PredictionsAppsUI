import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import {
  ChartBarIcon,
  TrophyIcon,
  UsersIcon,
  ArrowTrendingUpIcon,
  ArrowRightIcon,
  FireIcon
} from '@heroicons/react/24/outline'
import { Match } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import MatchCard from '@/components/ui/MatchCard'
import { motion } from 'framer-motion'
import { footballDataService } from '@/services/football-data.service'

const HomePage: React.FC = () => {
  const [todayMatches, setTodayMatches] = useState<Match[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchTodayMatches() {
      try {
        setLoading(true)
        const matches = await footballDataService.getTodayFixtures()
        setTodayMatches(matches)
      } catch (error) {
        console.error('Error fetching today\'s matches:', error)
        setTodayMatches([])
      } finally {
        setLoading(false)
      }
    }

    fetchTodayMatches()
  }, [])

  const stats = [
    {
      name: 'Total Predictions',
      value: '15,234',
      icon: ChartBarIcon,
      change: '+12%',
      changeType: 'increase' as const,
    },
    {
      name: 'Accuracy Rate',
      value: '78.5%',
      icon: TrophyIcon,
      change: '+2.1%',
      changeType: 'increase' as const,
    },
    {
      name: 'Active Users',
      value: '8,429',
      icon: UsersIcon,
      change: '+18%',
      changeType: 'increase' as const,
    },
    {
      name: 'Success Rate',
      value: '82.3%',
      icon: ArrowTrendingUpIcon,
      change: '+5.2%',
      changeType: 'increase' as const,
    },
  ]

  // Get featured matches (high confidence predictions)
  const featuredMatches = todayMatches
    .filter(m => m.predictions.outcome.confidence === 'high' || m.predictions.outcome.confidence === 'very-high')
    .slice(0, 3)

  return (
    <>
      <Helmet>
        <title>Soccer Predictions - Professional Football Analytics & Betting Tips</title>
        <meta name="description" content="Get accurate soccer predictions with advanced analytics. Professional football betting tips, match analysis, and expert insights for today's games." />
      </Helmet>

      <div className="min-h-screen">
        {/* Hero Section */}
        <section className="relative overflow-hidden bg-gradient-to-br from-dark-900 via-dark-800 to-dark-900">
          <div className="absolute inset-0 bg-gradient-to-r from-primary-900/20 to-transparent" />
          <div className="relative mx-auto max-w-7xl px-4 py-24 sm:px-6 lg:px-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8 }}
              className="text-center"
            >
              <h1 className="text-4xl font-bold tracking-tight text-white sm:text-6xl">
                Professional{' '}
                <span className="text-gradient">Soccer Predictions</span>
              </h1>
              <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-secondary-300">
                Get accurate match predictions powered by advanced analytics and expert insights. 
                Join thousands of successful bettors who trust our professional analysis.
              </p>
              <div className="mt-10 flex items-center justify-center gap-x-6">
                <Button size="lg" asChild>
                  <Link to="/predictions/today">
                    View Today's Predictions
                    <ArrowRightIcon className="ml-2 h-5 w-5" />
                  </Link>
                </Button>
                <Button variant="outline" size="lg" asChild>
                  <Link to="/register">Start Free Trial</Link>
                </Button>
              </div>
            </motion.div>
          </div>
        </section>

        {/* Stats Section */}
        <section className="py-16 bg-dark-900">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2 }}
              className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4"
            >
              {stats.map((stat) => (
                <Card key={stat.name} className="text-center">
                  <Card.Body>
                    <div className="flex items-center justify-center">
                      <div className="rounded-lg bg-primary-900 p-3">
                        <stat.icon className="h-6 w-6 text-primary-300" />
                      </div>
                    </div>
                    <div className="mt-4">
                      <div className="text-2xl font-bold text-white">{stat.value}</div>
                      <div className="text-sm text-secondary-400">{stat.name}</div>
                      <div className="mt-2 flex items-center justify-center">
                        <span className="text-success-400 text-sm font-medium">
                          {stat.change} from last month
                        </span>
                      </div>
                    </div>
                  </Card.Body>
                </Card>
              ))}
            </motion.div>
          </div>
        </section>

        {/* Featured Predictions */}
        <section className="py-16 bg-dark-950">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.4 }}
            >
              <div className="flex items-center justify-between mb-8">
                <div>
                  <h2 className="text-3xl font-bold text-white">
                    <FireIcon className="inline h-8 w-8 text-primary-500 mr-2" />
                    Featured Predictions
                  </h2>
                  <p className="mt-2 text-secondary-400">
                    Today's top predictions with highest confidence levels
                  </p>
                </div>
                <Button variant="outline" asChild>
                  <Link to="/predictions/today">View All</Link>
                </Button>
              </div>

              {loading ? (
                <div className="text-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
                  <div className="text-secondary-400">Loading featured predictions...</div>
                </div>
              ) : featuredMatches.length > 0 ? (
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                  {featuredMatches.map((match, index) => (
                    <motion.div
                      key={match.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.5, delay: 0.1 * index }}
                    >
                      <MatchCard match={match} />
                    </motion.div>
                  ))}
                </div>
              ) : (
                <Card>
                  <Card.Body>
                    <div className="text-center py-12">
                      <p className="text-secondary-400">No featured predictions available at the moment.</p>
                      <Button className="mt-4" asChild>
                        <Link to="/predictions/today">View All Predictions</Link>
                      </Button>
                    </div>
                  </Card.Body>
                </Card>
              )}
            </motion.div>
          </div>
        </section>

        {/* Today's Matches Preview */}
        <section className="py-16 bg-dark-900">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.6 }}
            >
              <div className="flex items-center justify-between mb-8">
                <div>
                  <h2 className="text-3xl font-bold text-white">Today's Matches</h2>
                  <p className="mt-2 text-secondary-400">
                    All matches scheduled for today with predictions
                  </p>
                </div>
                <Button variant="outline" asChild>
                  <Link to="/predictions/today">View All Today</Link>
                </Button>
              </div>

              {loading ? (
                <div className="text-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
                  <div className="text-secondary-400">Loading today's matches...</div>
                </div>
              ) : todayMatches.length > 0 ? (
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
                  {todayMatches.slice(0, 6).map((match, index) => (
                    <motion.div
                      key={match.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.5, delay: 0.1 * index }}
                    >
                      <MatchCard match={match} />
                    </motion.div>
                  ))}
                </div>
              ) : (
                <Card>
                  <Card.Body>
                    <div className="text-center py-12">
                      <p className="text-secondary-400">No matches scheduled for today.</p>
                      <Button className="mt-4" asChild>
                        <Link to="/predictions/tomorrow">View Tomorrow's Matches</Link>
                      </Button>
                    </div>
                  </Card.Body>
                </Card>
              )}
            </motion.div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-16 bg-gradient-to-r from-primary-900 to-primary-800">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.8 }}
              className="text-center"
            >
              <h2 className="text-3xl font-bold text-white">
                Ready to Start Winning?
              </h2>
              <p className="mx-auto mt-4 max-w-2xl text-lg text-primary-100">
                Join our community of successful bettors and get access to premium predictions, 
                detailed analysis, and expert insights.
              </p>
              <div className="mt-8 flex items-center justify-center gap-x-6">
                <Button size="lg" variant="secondary" asChild>
                  <Link to="/register">Get Started Free</Link>
                </Button>
                <Button size="lg" variant="outline" asChild>
                  <Link to="/predictions/today">Browse Predictions</Link>
                </Button>
              </div>
            </motion.div>
          </div>
        </section>
      </div>
    </>
  )
}

export default HomePage
