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
import Disclosure from '@/components/match-detail/Disclosure'
import MeasuredRecord from '@/components/ui/MeasuredRecord'
import MatchdayWorkspace from '@/components/matches/MatchdayWorkspace'
import { footballDataService } from '@/services/football-data.service'
import { CoverageSummary, localDateString } from '@/services/match-data-source'
import { performanceService, PerformanceResult } from '@/services/performance.service'
import { formatDateTime, formatNumber } from '@/i18n'
import { useT } from '@/i18n/react'

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
 * forecasts are worth trusting. The only judgement of that kind this site can make is the measured
 * record's, counted from scored results and published with its sample — never inferred from the
 * shape of a probability. Today's fixtures are listed in kickoff order instead, each one naming
 * its own sources.
 *
 * NO FIGURE ON THIS PAGE IS INVENTED. The coverage counts are counted from the rows this
 * installation holds, and the only accuracy figures are the ones the measured record publishes
 * from scored predictions, each with the sample and window it was counted over. There is no user
 * count, no streak and no site-wide success claim, because there is nothing to count them from.
 * Nothing here states how much has been scored either: that answer changes as results come in, and
 * the measured record reads it from the endpoint on every load.
 *
 * WHAT IS NOW BEHIND A DISCLOSURE, AND WHY THAT IS NOT HIDING IT. The page ran to about 5,500px on
 * a phone, and two of its five blocks were explanation rather than football: three paragraphs of
 * methodology, and four stat cards that stack into a column half a screen tall each. Neither is
 * wrong and neither has been cut. Each now leads with the one sentence that carries its point —
 * for the counts, a sentence built from the very same numbers, denominators included — and keeps
 * the rest a tap away. A returning reader scrolls past two lines instead of two screens; a reader
 * who wants the detail opens it and finds all of it.
 *
 * THE HEADINGS ARE WRITTEN FOR SOMEBODY WHO CAME FOR FOOTBALL. "What this installation holds" is
 * how an operator describes a database. A reader wants to know what is on and how much of it has
 * a forecast, so that is what the heading asks.
 */

const HomePage: React.FC = () => {
  const t = useT()
  const [coverage, setCoverage] = useState<CoverageSummary | null>(null)
  const [coverageLoaded, setCoverageLoaded] = useState(false)
  /**
   * The measured record, from the settlement endpoint.
   *
   * Public on purpose. A visitor who has not signed in is exactly the person entitled to ask how
   * often these sources have been right, and the honest answer — whatever it is on the day they
   * ask, from "nothing has been scored yet" to a published rate with its sample — is only worth
   * anything if they can actually see it. The endpoint reads stored score rows and calls no
   * provider, so this costs nothing.
   */
  const [performance, setPerformance] = useState<PerformanceResult | null>(null)
  const [performanceLoading, setPerformanceLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    footballDataService.getCoverage()
      .then(summary => { if (!cancelled) setCoverage(summary) })
      .finally(() => { if (!cancelled) setCoverageLoaded(true) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    performanceService.getMeasuredPerformance()
      .then(result => { if (!cancelled) setPerformance(result) })
      .finally(() => { if (!cancelled) setPerformanceLoading(false) })
    return () => { cancelled = true }
  }, [])

  /*
   * `toLocaleString()` on a number is the DEVICE's convention. `formatNumber` is the reader's —
   * 1,234 in English and 1 234 in French — which is the same rule every other figure on the
   * page now follows.
   */
  const stats = [
    {
      name: t('home.stat.competitions'),
      value: coverage ? formatNumber(coverage.competitions_covered) : null,
      icon: TrophyIcon,
      detail: t('home.stat.competitionsDetail'),
    },
    {
      name: t('home.stat.fixtures'),
      value: coverage ? formatNumber(coverage.upcoming_matches) : null,
      icon: CalendarDaysIcon,
      detail: t('home.stat.fixturesDetail'),
    },
    {
      name: t('home.stat.forecasts'),
      value: coverage ? formatNumber(coverage.upcoming_matches_with_forecast) : null,
      icon: CpuChipIcon,
      // A share needs its denominator on the same card. "34 model forecasts" beside "43 upcoming
      // fixtures" leaves the reader to notice that the first is a subset of the second, and a
      // reader who does not notice reads full coverage where nine fixtures have none.
      detail: coverage
        ? t('home.stat.forecastsDetailOf', { total: formatNumber(coverage.upcoming_matches) })
        : t('home.stat.forecastsDetail'),
    },
    {
      name: t('home.stat.expertPredictions'),
      value: coverage ? formatNumber(coverage.expert_predictions_published) : null,
      icon: ChartBarIcon,
      detail: t('home.stat.expertPredictionsDetail'),
    },
  ]

  return (
    <>
      <Helmet>
        <title>{t('home.documentTitle')}</title>
        <meta name="description" content={t('home.documentDescription')} />
      </Helmet>

      <div className="min-h-screen bg-dark-950">
        {/* Matches first. Nothing above this on the page but the site header. */}
        <section className="mx-auto max-w-5xl px-3 py-4 sm:px-6 sm:py-6 lg:px-8">
          <MatchdayWorkspace
            defaultDate={localDateString(0)}
            headingLevel={1}
            title={t('matchday.title.today')}
            variant="panel"
            limit={8}
            moreHref="/predictions/today"
            listId="home-fixtures"
          />
        </section>

        {/*
          HOW MUCH FOOTBALL IS HERE — the counts, led by the sentence they add up to.

          The four cards below stack into roughly half a screen each on a phone, and a reader
          scrolling for fixtures met all four before anything else. The summary line above them
          carries the same numbers, from the same payload, with the denominator attached — which
          is the part that actually answers the question. The cards keep the icons, the labels and
          the per-figure notes for anyone who opens them.
        */}
        <section className="border-t border-dark-800 bg-dark-900 py-8" aria-labelledby="home-coverage">
          <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
            <h2 id="home-coverage" className="text-xl font-bold text-white sm:text-2xl">
              {t('home.coverageHeading')}
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary-300" data-testid="coverage-summary">
              {!coverageLoaded
                ? t('home.coverageCounting')
                : coverage
                  ? <>
                    {/* Every figure with what it is a figure OF: a bare "34 forecasts" beside
                        "43 fixtures" leaves the reader to notice the second is the denominator
                        of the first, and a reader who does not notice reads full coverage.
                        Three whole sentences rather than fragments around <span>s: the numbers
                        do not sit in the same places in French, and the `.num` styling is not
                        worth an ungrammatical sentence. */}
                    {t('home.coverageStored', {
                      fixtures: formatNumber(coverage.upcoming_matches),
                      competitions: formatNumber(coverage.competitions_covered),
                    })}{' '}
                    {t('home.coverageForecasts', {
                      withForecast: formatNumber(coverage.upcoming_matches_with_forecast),
                      without: formatNumber(coverage.upcoming_matches - coverage.upcoming_matches_with_forecast),
                    })}{' '}
                    {coverage.expert_predictions_published > 0
                      ? t('home.coverageExperts', { count: formatNumber(coverage.expert_predictions_published) })
                      : t('home.coverageNoExperts')}
                  </>
                  : t('home.coverageFailed')}
            </p>

            <Disclosure summary={t('home.coverageDisclosure')} className="mt-3" testId="coverage-detail">
              <p className="mb-3 text-secondary-500">
                {(() => {
                  const when = formatDateTime(coverage?.measured_at)
                  return when
                    ? t('home.coverageCountedFromWhen', { when })
                    : t('home.coverageCountedFrom')
                })()}
                {/*
                  This used to append the coverage endpoint's own "no accuracy figure is shown"
                  clause. The measured record below now answers that question properly — per
                  source, with the sample, the definition and the window — so repeating a
                  one-line version of it here would put two statements about the same thing on one
                  screen, and the weaker one first.
                */}
              </p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
                            // A shape, not the word "loading": a skeleton that says nothing cannot
                            // be mistaken for a figure.
                            <span className="inline-block h-7 w-16 animate-pulse rounded bg-dark-700" aria-hidden="true" />
                          ) : stat.value ?? (
                            <span className="text-base font-medium text-secondary-500">{t('home.statUnavailable')}</span>
                          )}
                        </div>
                        <div className="text-sm text-secondary-400">{stat.name}</div>
                        <div className="mt-2 text-xs text-secondary-500">{stat.detail}</div>
                      </div>
                    </Card.Body>
                  </Card>
                ))}
              </div>
            </Disclosure>
          </div>
        </section>

        {/*
          WHAT THIS SITE IS — one paragraph, with the method behind it.

          Three paragraphs of methodology used to sit here in full. They are the paragraphs that
          make this site trustworthy rather than just another tipster page, and not one word of
          them has gone: what changed is that the reader is told the shape of the thing first and
          decides whether to read the rules. The rules are still one tap away, on the page, before
          any of the numbers they govern.
        */}
        <section className="py-8" aria-labelledby="home-about">
          <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
            <h2 id="home-about" className="text-xl font-bold text-white sm:text-2xl">
              {t('home.aboutHeading')}
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary-300">{t('home.aboutBody')}</p>

            <Disclosure summary={t('home.methodDisclosure')} className="mt-3" testId="home-method">
              <div className="max-w-3xl space-y-2 leading-6 text-secondary-300">
                <p>{t('home.method1')}</p>
                <p>{t('home.method2')}</p>
                <p>{t('home.method3')}</p>
              </div>
            </Disclosure>

            <div className="mt-5 flex flex-wrap gap-3">
              <Button asChild>
                <Link to="/matches">{t('home.browseByDate')}</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link to="/leagues">{t('home.competitions')}</Link>
              </Button>
            </div>
          </div>
        </section>

        {/*
          The measured record, in public.
          It sits after the coverage counts because it answers the next question a reader asks —
          "and how often were they right?" — and it must answer it with whatever is true at the
          moment they ask. That answer is read from /performance/sources on every load and is never
          written down here: when nothing has been scored it says so with the reason and the
          window, and when something has, it publishes the figure with the sample it came from.
          Either way it is a real answer rather than an empty chart or a hopeful zero.
        */}
        {/*
          No heading is added here. MeasuredRecord renders its own h2 — "How the sources have
          actually done" — in the same size and weight, so a second one above it put two headings
          that ask the same question back to back, which is the exact duplication this section of
          the page was being shortened to remove. The section takes its accessible name from the
          heading the component already publishes.
        */}
        <section className="border-t border-dark-800 py-8">
          <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
            <MeasuredRecord result={performance} loading={performanceLoading} />
          </div>
        </section>

        <section className="bg-gradient-to-r from-primary-900 to-primary-800 py-10">
          <div className="mx-auto max-w-5xl px-4 text-center sm:px-6 lg:px-8">
            <h2 className="text-2xl font-bold text-white">{t('home.followHeading')}</h2>
            <p className="mx-auto mt-3 max-w-2xl text-base text-primary-100">
              {/*
                This used to offer expert reasoning as something an account unlocks. It is not:
                every forecast and every expert analysis on this site is public, and a fixture only
                carries an expert's reasoning when an expert has published one for it. An account
                changes what is remembered for you, not what you are allowed to read.
              */}
              {t('home.followBody')}
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <Button size="lg" variant="secondary" asChild>
                <Link to="/register">{t('home.createAccount')}</Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link to="/predictions/tomorrow">{t('home.tomorrowsMatches')}</Link>
              </Button>
            </div>
          </div>
        </section>
      </div>
    </>
  )
}

export default HomePage
