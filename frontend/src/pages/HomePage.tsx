import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import {
  ChartBarIcon,
  TrophyIcon,
  CalendarDaysIcon,
  CpuChipIcon,
  ArrowRightIcon,
  FireIcon
} from '@heroicons/react/24/outline'
import { Match } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import MatchCard from '@/components/ui/MatchCard'
import ForecastSyncNotice from '@/components/ui/ForecastSyncNotice'
import { isHighConfidence } from '@/components/ui/predictionMarkets'
import { motion } from 'framer-motion'
import { footballDataService } from '@/services/football-data.service'
import { describeError } from '@/services/backend-match-data.service'
import { CoverageSummary, DataSourceMeta, localDateString } from '@/services/match-data-source'
import { filterLiveAndScheduledMatches, filterLiveAndUpcomingMatches } from '@/utils/matchFilters'

const HomePage: React.FC = () => {
  const [todayMatches, setTodayMatches] = useState<Match[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [meta, setMeta] = useState<DataSourceMeta | null>(null)
  const [coverage, setCoverage] = useState<CoverageSummary | null>(null)
  const [coverageLoading, setCoverageLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let cancelled = false

    async function fetchTodayMatches() {
      try {
        setLoading(true)
        setError(null)
        // With meta: the forecast-refresh report is what tells a paused refresh apart from "none exist".
        const result = await footballDataService.getFixturesByDateWithMeta(localDateString(0))
        if (!cancelled) {
          setTodayMatches(result.matches)
          setMeta(result.meta)
        }
      } catch (err) {
        console.error('Error fetching today\'s matches:', err)
        if (!cancelled) {
          // A failed request is NOT "no matches today"; say the request failed and offer a retry.
          setError(describeError(err))
          setTodayMatches([])
          setMeta(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    async function fetchCoverage() {
      try {
        const summary = await footballDataService.getCoverage()
        if (!cancelled) setCoverage(summary)
      } finally {
        if (!cancelled) setCoverageLoading(false)
      }
    }

    fetchTodayMatches()
    fetchCoverage()
    return () => { cancelled = true }
  }, [reloadToken])

  const retry = () => setReloadToken(token => token + 1)

  /**
   * Measured from the data this installation actually holds. There is deliberately no accuracy,
   * success-rate or user-count figure here: scoring a forecast needs settled results, and none have
   * been scored yet, so any such number would be invented.
   */
  const stats = [
    {
      name: 'Competitions covered',
      value: coverage ? String(coverage.competitions_covered) : null,
      icon: TrophyIcon,
      detail: 'Top five European leagues and the Champions League',
    },
    {
      name: 'Upcoming fixtures loaded',
      value: coverage ? coverage.upcoming_matches.toLocaleString() : null,
      icon: CalendarDaysIcon,
      detail: 'Scheduled and in-play matches currently stored',
    },
    {
      name: 'Model forecasts available',
      value: coverage ? coverage.upcoming_matches_with_forecast.toLocaleString() : null,
      icon: CpuChipIcon,
      detail: 'Upcoming matches with a GameForecast model prediction attached',
    },
    {
      name: 'Expert predictions published',
      value: coverage ? coverage.expert_predictions_published.toLocaleString() : null,
      icon: ChartBarIcon,
      detail: 'Published by experts registered on this site',
    },
  ]

  // Featured: live/upcoming matches where a published market is rated high or very high. A match
  // whose source published no 1X2 market can still qualify on BTTS or totals — and one with no
  // published market at all never qualifies.
  const featuredMatches = filterLiveAndUpcomingMatches(todayMatches, true)
    .filter(m => isHighConfidence(m.predictions))
    .slice(0, 3)

  const scheduledToday = filterLiveAndScheduledMatches(todayMatches)

  return (
    <>
      <Helmet>
        <title>Soccer Predictions - Fixtures, Model Forecasts and Expert Analysis</title>
        <meta name="description" content="Fixtures and results for the top five European leagues and the Champions League, with GameForecastAPI model forecasts and predictions published by registered experts." />
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
                Fixtures and results from Europe&rsquo;s top five leagues and the Champions League,
                with model forecasts from GameForecastAPI and predictions published by registered experts.
                Every probability shown comes from a named source, and markets without one are marked unavailable.
              </p>
              <div className="mt-10 flex items-center justify-center gap-x-6">
                <Button size="lg" asChild>
                  <Link to="/predictions/today">
                    View Today's Predictions
                    <ArrowRightIcon className="ml-2 h-5 w-5" />
                  </Link>
                </Button>
                <Button variant="outline" size="lg" asChild>
                  <Link to="/register">Create an account</Link>
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
                <Card key={stat.name} className="text-center" data-testid="coverage-stat">
                  <Card.Body>
                    <div className="flex items-center justify-center">
                      <div className="rounded-lg bg-primary-900 p-3">
                        <stat.icon className="h-6 w-6 text-primary-300" />
                      </div>
                    </div>
                    <div className="mt-4">
                      <div className="text-2xl font-bold text-white">
                        {coverageLoading ? (
                          <span className="inline-block h-7 w-16 animate-pulse rounded bg-dark-700" aria-label="Loading" />
                        ) : stat.value ?? (
                          <span className="text-base font-medium text-secondary-500">Unavailable</span>
                        )}
                      </div>
                      <div className="text-sm text-secondary-400">{stat.name}</div>
                      <div className="mt-2 text-xs text-secondary-500">{stat.detail}</div>
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
                    Today&rsquo;s matches where the published prediction, expert or model, is rated
                    high or very high. Each card names its own source.
                  </p>
                </div>
                <Button variant="outline" asChild>
                  <Link to="/predictions/today">View All</Link>
                </Button>
              </div>

              <ForecastSyncNotice sync={meta?.forecastSync} className="mb-6" />

              {loading ? (
                <div className="text-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
                  <div className="text-secondary-400">Loading featured predictions...</div>
                </div>
              ) : error ? (
                <Card data-testid="home-matches-error">
                  <Card.Body>
                    <div className="text-center py-12">
                      <p className="text-lg font-medium text-red-400">Today&rsquo;s matches could not be loaded.</p>
                      <p className="mt-2 text-sm text-secondary-400">{error}</p>
                      <p className="mt-1 text-xs text-secondary-500">
                        This is a problem reaching our own service — it does not mean there are no matches today.
                      </p>
                      <Button className="mt-4" onClick={retry}>Try again</Button>
                    </div>
                  </Card.Body>
                </Card>
              ) : featuredMatches.length > 0 ? (
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                  {featuredMatches.map((match, index) => (
                    <motion.div
                      key={match.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.5, delay: 0.1 * index }}
                    >
                      <MatchCard match={match} forecastSync={meta?.forecastSync} />
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
              ) : error ? (
                <Card>
                  <Card.Body>
                    <div className="text-center py-12">
                      <p className="text-lg font-medium text-red-400">Today&rsquo;s matches could not be loaded.</p>
                      <p className="mt-2 text-sm text-secondary-400">{error}</p>
                      <Button className="mt-4" onClick={retry}>Try again</Button>
                    </div>
                  </Card.Body>
                </Card>
              ) : scheduledToday.length > 0 ? (
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
                  {scheduledToday.slice(0, 6).map((match, index) => (
                    <motion.div
                      key={match.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.5, delay: 0.1 * index }}
                    >
                      <MatchCard match={match} forecastSync={meta?.forecastSync} />
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
                Follow the fixtures that matter
              </h2>
              <p className="mx-auto mt-4 max-w-2xl text-lg text-primary-100">
                Create an account to save the competitions you follow and to read expert reasoning
                alongside each model forecast. Nothing here is betting advice.
              </p>
              <div className="mt-8 flex items-center justify-center gap-x-6">
                <Button size="lg" variant="secondary" asChild>
                  <Link to="/register">Create an account</Link>
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
