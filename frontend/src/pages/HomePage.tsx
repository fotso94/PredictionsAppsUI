import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import {
  ChartBarIcon,
  TrophyIcon,
  CalendarDaysIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import MatchdayWorkspace from '@/components/matches/MatchdayWorkspace'
import { footballDataService } from '@/services/football-data.service'
import { CoverageSummary, localDateString } from '@/services/match-data-source'

/**
 * The home page.
 *
 * WHAT CHANGED AND WHY. The research measured where the first fixture heading sat on this page:
 * about y=1002 on a desktop and y=1874 on a phone, behind a hero, an explanatory paragraph and four
 * site-wide totals. A returning reader came to look at matches, so the matches are now the first
 * thing on the page and everything that explains the site sits underneath them. The words did not
 * have to be deleted to do that — they had to be put after the thing they describe.
 *
 * WHAT IS NOT HERE ANY MORE. The old "Featured Predictions" section picked matches whose prediction
 * was "rated high or very high". That rating is not something any source published: the mapper
 * derives it from how large the biggest probability happens to be (`levelFromProbability`). Ranking
 * fixtures by it, on the front page, presents an arithmetic side effect as a judgement about which
 * forecasts are worth trusting — and nothing in this application has ever been scored against a
 * result, so no such judgement exists to present. Today's fixtures are listed in kickoff order
 * instead, each one naming its own sources.
 *
 * The coverage figures below are counted from the rows this installation actually holds. There is
 * still no accuracy, success rate or user count anywhere on this page, for the same reason: they
 * would have to be invented.
 */

const HomePage: React.FC = () => {
  const [coverage, setCoverage] = useState<CoverageSummary | null>(null)
  const [coverageLoaded, setCoverageLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    footballDataService.getCoverage()
      .then(summary => { if (!cancelled) setCoverage(summary) })
      .finally(() => { if (!cancelled) setCoverageLoaded(true) })
    return () => { cancelled = true }
  }, [])

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

  return (
    <>
      <Helmet>
        <title>Soccer Predictions - Fixtures, Model Forecasts and Expert Analysis</title>
        <meta name="description" content="Fixtures and results for the top five European leagues and the Champions League, with GameForecastAPI model forecasts and predictions published by registered experts." />
      </Helmet>

      <div className="min-h-screen bg-dark-950">
        {/* Matches first. Nothing above this on the page but the site header. */}
        <section className="mx-auto max-w-5xl px-3 py-4 sm:px-6 sm:py-6 lg:px-8">
          <MatchdayWorkspace
            defaultDate={localDateString(0)}
            headingLevel={1}
            title="Today's matches"
            variant="panel"
            limit={8}
            moreHref="/predictions/today"
            listId="home-fixtures"
          />
        </section>

        {/* Everything that explains the site, below the thing it explains. */}
        <section className="border-t border-dark-800 bg-dark-900 py-10" aria-labelledby="home-about">
          <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
            <h2 id="home-about" className="text-xl font-bold text-white sm:text-2xl">
              What you are looking at
            </h2>
            <div className="mt-3 max-w-3xl space-y-3 text-sm leading-6 text-secondary-300">
              <p>
                Fixtures and results from Europe&rsquo;s top five leagues and the Champions League,
                with model forecasts from GameForecastAPI and predictions published by registered
                experts. Every probability shown comes from a named source and is reproduced as that
                source published it.
              </p>
              <p>
                Nothing here is computed on your behalf. When a source did not publish a market, the
                match says so in the source&rsquo;s own words instead of showing a zero, and when a
                forecast is older than it should be, the fixture says that too. No prediction on this
                site has been scored against a result yet, so no accuracy figure is claimed anywhere.
              </p>
              <p>
                None of this is betting advice, and a probability is not a forecast of what will
                happen.
              </p>
            </div>

            <div className="mt-6 flex flex-wrap gap-3">
              <Button asChild>
                <Link to="/matches">Browse matches by date</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link to="/leagues">Competitions</Link>
              </Button>
            </div>
          </div>
        </section>

        {/* Measured from the rows this installation holds. */}
        <section className="py-10" aria-labelledby="home-coverage">
          <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
            <h2 id="home-coverage" className="text-xl font-bold text-white sm:text-2xl">
              What this installation holds
            </h2>
            <p className="mt-2 max-w-3xl text-sm text-secondary-400">
              Counted from the stored data
              {coverage?.measured_at ? ` on ${new Date(coverage.measured_at).toLocaleString()}` : ''}.
              {/* The backend's own reason, word for word, after a colon so its lower-case first
                  word reads as the clause it is. Only a trailing full stop is normalised, so the
                  sentence ends once however the backend punctuated it. */}
              {coverage && !coverage.accuracy_available
                && ` No accuracy figure is shown: ${coverage.accuracy_unavailable_reason.replace(/\.\s*$/, '')}.`}
            </p>

            <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {stats.map(stat => (
                <Card key={stat.name} className="text-center" data-testid="coverage-stat">
                  <Card.Body>
                    <div className="flex items-center justify-center">
                      <div className="rounded-lg bg-primary-900 p-3">
                        <stat.icon className="h-6 w-6 text-primary-300" aria-hidden="true" />
                      </div>
                    </div>
                    <div className="mt-4">
                      <div className="num text-2xl font-bold text-white">
                        {!coverageLoaded ? (
                          // A shape, not the word "loading": a skeleton that says nothing cannot be
                          // mistaken for a figure.
                          <span className="inline-block h-7 w-16 animate-pulse rounded bg-dark-700" aria-hidden="true" />
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
            </div>
          </div>
        </section>

        <section className="bg-gradient-to-r from-primary-900 to-primary-800 py-12">
          <div className="mx-auto max-w-5xl px-4 text-center sm:px-6 lg:px-8">
            <h2 className="text-2xl font-bold text-white">Follow the fixtures that matter</h2>
            <p className="mx-auto mt-3 max-w-2xl text-base text-primary-100">
              Create an account to save matches and follow the teams and competitions you care
              about, and to read expert reasoning alongside each model forecast.
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <Button size="lg" variant="secondary" asChild>
                <Link to="/register">Create an account</Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link to="/predictions/tomorrow">Tomorrow&rsquo;s matches</Link>
              </Button>
            </div>
          </div>
        </section>
      </div>
    </>
  )
}

export default HomePage
