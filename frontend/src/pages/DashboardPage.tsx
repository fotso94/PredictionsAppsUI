import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { ChartBarIcon, CpuChipIcon, CalendarDaysIcon, TrophyIcon } from '@heroicons/react/24/outline'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import SavedMatchesPanel from '@/components/favourites/SavedMatchesPanel'
import FollowingPanel from '@/components/favourites/FollowingPanel'
import { useAuth } from '@/hooks/useAuth'
import useFavourites from '@/hooks/useFavourites'
import { footballDataService } from '@/services/football-data.service'
import { CoverageSummary } from '@/services/match-data-source'

/**
 * The signed-in user's own page: the matches they saved, and the teams and competitions they follow.
 *
 * WHAT THIS PAGE USED TO BE, AND WHY IT CHANGED
 * Before this, it was three paragraphs explaining that results settlement is not implemented and
 * that no per-user history endpoint exists. Every word of that was true — and it had replaced a
 * fabricated record (247 predictions, 73% accuracy, a 5-match streak), which was the right thing to
 * do. But a page of explanation is a changelog, not somewhere to work: there was nothing on it the
 * reader could do or come back to. Saved matches and followed teams are real per-user facts this
 * build does hold, so they are the page now, and the honest sentence about settlement stays as the
 * footnote it always should have been.
 *
 * WHAT IS STILL NOT CLAIMED
 * There is no accuracy, hit rate, return, profit or streak anywhere here, because nothing has ever
 * been scored against a final result. A saved match is a bookmark, not a bet: no stake, no odds to
 * accept, no urgency, and no suggestion that anything is certain.
 *
 * ONE NOTE ON THE HEADING. The h1 stays "Dashboard": it is the route, the navigation entry and the
 * anchor e2e/mocked/dashboard-truthfulness.spec.ts uses to prove it is looking at this page rather
 * than the login form it redirects an anonymous visitor to. "My matches" is the first and largest
 * section, which is what the page is actually for. Renaming the h1 needs that spec updated by its
 * owner first — see the note in the package report.
 */
const DashboardPage: React.FC = () => {
  const { user } = useAuth()
  const { savedMatches, loaded, failed } = useFavourites()
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
        <title>My matches - Soccer Predictions</title>
        <meta name="description" content="The matches you saved and the teams and competitions you follow." />
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

          {/* The page proper: this user's own saved fixtures. */}
          <Card className="mb-8" data-testid="dashboard-my-matches">
            <Card.Header>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-lg font-semibold text-white">My matches</h2>
                {/* A count is only reported once a snapshot has really arrived: on a failed load the
                    buckets are empty because we do not know, not because there is nothing. */}
                {loaded && !failed && (
                  <p className="text-xs text-secondary-400">
                    <span className="num">{savedMatches.counts.total}</span> saved
                    {savedMatches.counts.live > 0 && (
                      <> · <span className="num">{savedMatches.counts.live}</span> in play now</>
                    )}
                  </p>
                )}
              </div>
            </Card.Header>
            <Card.Body>
              <SavedMatchesPanel />
            </Card.Body>
          </Card>

          <Card className="mb-8" data-testid="dashboard-following">
            <Card.Header>
              <div>
                <h2 className="text-lg font-semibold text-white">Teams and competitions you follow</h2>
                <p className="text-xs text-secondary-500">
                  Following keeps them one tap away; it does not change what any source publishes.
                </p>
              </div>
            </Card.Header>
            <Card.Body>
              <FollowingPanel />
            </Card.Body>
          </Card>

          {/*
            The footnote. It used to be the whole page; it is still true, so it stays — short, plain,
            and out of the way of the part of the page that is actually usable.
          */}
          <Card className="mb-8" data-testid="dashboard-no-record">
            <Card.Header>
              <h2 className="text-lg font-semibold text-white">Your prediction record</h2>
            </Card.Header>
            <Card.Body className="space-y-3 text-sm text-secondary-300">
              <p>
                Predictions on this site are not settled against final results yet, so no accuracy
                rate, streak or profit figure has ever been calculated — for you or for anyone. Saving
                a match records that you want to come back to it; it is not a wager and nothing about
                it is scored.
              </p>
              <div className="flex flex-wrap gap-3 pt-1">
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
