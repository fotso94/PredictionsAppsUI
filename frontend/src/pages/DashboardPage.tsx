import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { ChartBarIcon, CpuChipIcon, CalendarDaysIcon, TrophyIcon } from '@heroicons/react/24/outline'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import { useAuth } from '@/hooks/useAuth'
import { footballDataService } from '@/services/football-data.service'
import { CoverageSummary } from '@/services/match-data-source'

/**
 * Signed-in user's dashboard.
 *
 * It previously rendered a fixed mock profile — 247 predictions, a 73% accuracy rate, a 5-match
 * streak and a list of settled bets — as though it were the reader's own record. None of it was
 * real, and none of it could be: results settlement is not implemented, so nothing has ever been
 * scored. There is therefore no accuracy, streak or profit figure to show, and inventing a
 * replacement number would repeat the original problem. The page says so instead, and shows the
 * only per-user fact this build actually has: who is signed in.
 */
const DashboardPage: React.FC = () => {
  const { user } = useAuth()
  const [coverage, setCoverage] = useState<CoverageSummary | null>(null)
  const [coverageLoading, setCoverageLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    footballDataService.getCoverage()
      .then(summary => { if (!cancelled) setCoverage(summary) })
      .finally(() => { if (!cancelled) setCoverageLoading(false) })
    return () => { cancelled = true }
  }, [])

  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim()
    || user?.username
    || user?.email
    || 'there'

  /** Measured from what this installation holds — site-wide, not per user, and labelled as such. */
  const siteStats = [
    {
      name: 'Competitions covered',
      value: coverage ? String(coverage.competitions_covered) : null,
      icon: TrophyIcon,
    },
    {
      name: 'Upcoming fixtures loaded',
      value: coverage ? coverage.upcoming_matches.toLocaleString() : null,
      icon: CalendarDaysIcon,
    },
    {
      name: 'Model forecasts available',
      value: coverage ? coverage.upcoming_matches_with_forecast.toLocaleString() : null,
      icon: CpuChipIcon,
    },
    {
      name: 'Expert predictions published',
      value: coverage ? coverage.expert_predictions_published.toLocaleString() : null,
      icon: ChartBarIcon,
    },
  ]

  return (
    <>
      <Helmet>
        <title>Dashboard - Soccer Predictions</title>
        <meta name="description" content="Your account dashboard." />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">Dashboard</h1>
            <p className="text-secondary-400">Welcome back, {displayName}!</p>
            {user?.email && (
              <p className="mt-1 text-sm text-secondary-500">
                Signed in as {user.email}
                {user.user_type && user.user_type !== 'REGULAR' ? ` · ${user.user_type.toLowerCase()} account` : ''}
              </p>
            )}
          </div>

          {/* Honest empty state: there is no scored per-user record to show. */}
          <Card className="mb-8" data-testid="dashboard-no-record">
            <Card.Header>
              <h2 className="text-lg font-semibold text-white">Your prediction record</h2>
            </Card.Header>
            <Card.Body className="space-y-3 text-sm text-secondary-300">
              <p>
                There is nothing to show here yet, and we are not going to make a number up.
              </p>
              <p className="text-secondary-400">
                Predictions on this site are not settled against final results yet — no accuracy rate,
                streak, hit rate or profit figure has ever been calculated, for you or for anyone. There is
                also no per-user prediction history endpoint in this build, so we cannot list predictions
                you have followed.
              </p>
              <p className="text-secondary-400">
                When results settlement ships, this page will show your measured record and say exactly
                how it was calculated.
              </p>
              <div className="flex flex-wrap gap-3 pt-2">
                <Button asChild>
                  <Link to="/predictions/today">Browse today&rsquo;s predictions</Link>
                </Button>
                <Button variant="outline" asChild>
                  <Link to="/profile">Account settings</Link>
                </Button>
              </div>
            </Card.Body>
          </Card>

          {/* Site-wide coverage, clearly not presented as the reader's own activity. */}
          <Card>
            <Card.Header>
              <div>
                <h2 className="text-lg font-semibold text-white">What this site currently holds</h2>
                <p className="text-xs text-secondary-500">
                  Site-wide counts measured from stored data — not your personal statistics.
                </p>
              </div>
            </Card.Header>
            <Card.Body>
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
                {siteStats.map(stat => (
                  <div key={stat.name} className="text-center" data-testid="dashboard-site-stat">
                    <div className="flex items-center justify-center">
                      <div className="rounded-lg bg-primary-900 p-3">
                        <stat.icon className="h-6 w-6 text-primary-300" />
                      </div>
                    </div>
                    <div className="mt-3 text-2xl font-bold text-white">
                      {coverageLoading ? (
                        <span className="inline-block h-7 w-16 animate-pulse rounded bg-dark-700" aria-label="Loading" />
                      ) : stat.value ?? (
                        <span className="text-base font-medium text-secondary-500">Unavailable</span>
                      )}
                    </div>
                    <div className="text-sm text-secondary-400">{stat.name}</div>
                  </div>
                ))}
              </div>
              {!coverageLoading && !coverage && (
                <p className="mt-4 text-center text-xs text-secondary-500">
                  The coverage endpoint could not be reached, so these counts are unavailable.
                </p>
              )}
              {coverage && !coverage.accuracy_available && (
                <p className="mt-4 text-center text-xs text-secondary-500">
                  No accuracy figure is shown: {coverage.accuracy_unavailable_reason}
                </p>
              )}
            </Card.Body>
          </Card>
        </div>
      </div>
    </>
  )
}

export default DashboardPage
