import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { ChartBarIcon, CpuChipIcon, CalendarDaysIcon, TrophyIcon } from '@heroicons/react/24/outline'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import SavedMatchesPanel from '@/components/favourites/SavedMatchesPanel'
import FollowingPanel from '@/components/favourites/FollowingPanel'
import PersonalControls from '@/components/favourites/PersonalControls'
import { useAuth } from '@/hooks/useAuth'
import useFavourites from '@/hooks/useFavourites'
import { usePersonalPreferences } from '@/services/favourites.service'
import { footballDataService } from '@/services/football-data.service'
import { CoverageSummary } from '@/services/match-data-source'
import { formatNumber, type MessageKey } from '@/i18n'
import { useT } from '@/i18n/react'
import Emphasised from '@/i18n/Emphasised'

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
 * There is no accuracy, hit rate, return, profit or streak anywhere here. Not because nothing on
 * this installation has ever been scored — model forecasts are settled against final results, and
 * the home page publishes how they have done with the sample behind each figure — but because
 * none of that is THIS READER's record. A saved match is a bookmark, not a bet: no stake, no odds
 * to accept, no urgency, and nothing the reader did is being marked right or wrong.
 *
 * THE FEED IS THE PAGE. The first card is one ordered list of what is in play, what has just been
 * played and what is coming up, built from the matches this reader saved and the teams and
 * competitions they follow (src/components/favourites/SavedMatchesPanel.tsx). It is first because
 * it is the only part of this page that changes between two visits.
 *
 * ONE NOTE ON THE HEADING. The h1 stays "Dashboard": it is the route, the navigation entry and the
 * anchor e2e/mocked/dashboard-truthfulness.spec.ts uses to prove it is looking at this page rather
 * than the login form it redirects an anonymous visitor to. "My matches" is the first and largest
 * section, which is what the page is actually for. Renaming the h1 needs that spec updated by its
 * owner first — see the note in the package report. In French it reads « Tableau de bord », which
 * is `nav.dashboard` — the same key the navigation entry uses, so the heading and the link a
 * reader followed to reach it cannot say different things.
 *
 * ── THE THREE `toLocaleString()` CALLS HERE WERE NOT DATES ──────────────────────────────────
 *
 * The catalogue survey counted three raw `toLocaleString` calls on this page and they turned out
 * to be `Number.prototype.toLocaleString`, not `Date`'s: the three coverage figures. They were
 * still wrong for the same underlying reason — `(1234).toLocaleString()` uses the DEVICE's
 * locale, so a French reader on an American laptop was shown "1,234" where their own convention
 * is "1 234" — and the fourth figure beside them used `String()`, so it was not grouped at all
 * and the row disagreed with itself past a thousand. All four now go through `formatNumber`,
 * which reads the language the reader CHOSE. There is no date on this page.
 */
const DashboardPage: React.FC = () => {
  const t = useT()
  const { user } = useAuth()
  const { savedMatches, loaded, failed } = useFavourites()
  const prefs = usePersonalPreferences(user?.id ?? null)
  const [coverage, setCoverage] = useState<CoverageSummary | null>(null)
  const [coverageLoading, setCoverageLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    footballDataService.getCoverage()
      .then(summary => { if (!cancelled) setCoverage(summary) })
      .finally(() => { if (!cancelled) setCoverageLoading(false) })
    return () => { cancelled = true }
  }, [])

  /**
   * The reader's own name, which is theirs and is never translated.
   *
   * Null when the account carries nothing to greet them by. The greeting is then a different
   * sentence rather than this one with the word "there" dropped into the hole: French has no
   * word that stands in for a name that way, and « Bon retour, vous ! » is not a sentence
   * anybody says.
   */
  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim()
    || user?.username
    || user?.email
    || null

  /**
   * Measured from what this installation holds — site-wide, not per user, and labelled as such.
   *
   * The four labels are `home.stat.*`: the home page shows the same four counts under the same
   * four names, and two keys for one label is how the two pages start disagreeing about what a
   * figure means. Every figure goes through `formatNumber`, in the reader's own convention.
   */
  const siteStats: Array<{ name: MessageKey; value: string | null; icon: typeof TrophyIcon }> = [
    {
      name: 'home.stat.competitions',
      value: coverage ? formatNumber(coverage.competitions_covered) : null,
      icon: TrophyIcon,
    },
    {
      name: 'home.stat.fixtures',
      value: coverage ? formatNumber(coverage.upcoming_matches) : null,
      icon: CalendarDaysIcon,
    },
    {
      name: 'home.stat.forecasts',
      value: coverage ? formatNumber(coverage.upcoming_matches_with_forecast) : null,
      icon: CpuChipIcon,
    },
    {
      name: 'home.stat.expertPredictions',
      value: coverage ? formatNumber(coverage.expert_predictions_published) : null,
      icon: ChartBarIcon,
    },
  ]

  return (
    <>
      <Helmet>
        <title>{t('reader.dashboard.documentTitle')}</title>
        <meta name="description" content={t('reader.dashboard.documentDescription')} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">{t('nav.dashboard')}</h1>
            <p className="text-secondary-400">
              {displayName
                ? t('reader.dashboard.welcome', { name: displayName })
                : t('reader.dashboard.welcomeNoName')}
            </p>
            {user?.email && (
              <p className="mt-1 text-sm text-secondary-500">
                {t('reader.dashboard.signedInAs', { email: user.email })}
                {/* The account type is the backend's own word and is rendered as it sent it. */}
                {user.user_type && user.user_type !== 'REGULAR'
                  ? t('reader.dashboard.accountKind', { type: user.user_type.toLowerCase() })
                  : ''}
              </p>
            )}
          </div>

          {/* The page proper: one feed built from this reader's own saves and follows. */}
          <Card className="mb-8" data-testid="dashboard-my-matches">
            <Card.Header>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <h2 className="text-lg font-semibold text-white">{t('reader.dashboard.feedHeading')}</h2>
                  <p className="text-xs text-secondary-500">{t('reader.dashboard.feedHint')}</p>
                </div>
                {/* A count is only reported once a snapshot has really arrived: on a failed load the
                    buckets are empty because we do not know, not because there is nothing. */}
                {/*
                  THE COUNT IS A HOLE IN A WHOLE SENTENCE, NOT A <span> GLUED TO A WORD.
                  It used to be `<span>{n}</span> saved`, which freezes the numeral before the
                  label; `Emphasised` finds the numeral inside the rendered sentence instead, so
                  the catalogue decides where in the phrase it goes and keeps the `num` class
                  (tabular figures) on exactly that run. Neither label inflects with the count in
                  either language — see the header of src/i18n/messages/reader.fr.ts.
                */}
                {loaded && !failed && (
                  <p className="text-xs text-secondary-400">
                    <Emphasised
                      sentence={t('reader.dashboard.savedCount', { count: formatNumber(savedMatches.counts.total) })}
                      value={formatNumber(savedMatches.counts.total)}
                      className="num"
                    />
                    {savedMatches.counts.live > 0 && (
                      <>
                        {' · '}
                        <Emphasised
                          sentence={t('reader.dashboard.liveCount', { count: formatNumber(savedMatches.counts.live) })}
                          value={formatNumber(savedMatches.counts.live)}
                          className="num"
                        />
                      </>
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
                <h2 className="text-lg font-semibold text-white">{t('reader.dashboard.followingHeading')}</h2>
                <p className="text-xs text-secondary-500">{t('reader.dashboard.followingHint')}</p>
              </div>
            </Card.Header>
            <Card.Body>
              <FollowingPanel />
            </Card.Body>
          </Card>

          {/*
            THE CONTROLS SIT HERE, AND NOT ON A SETTINGS ROUTE.

            Directly under the follow list, because that is the card a reader is already on when
            they are deciding what their own pages contain — and because a preference filed behind
            /profile is a preference most people never find. It is the last of the three cards
            about THIS reader, before the page turns to site-wide facts.
          */}
          <Card className="mb-8" data-testid="dashboard-personal-controls">
            <Card.Header>
              <div>
                <h2 className="text-lg font-semibold text-white">{t('reader.dashboard.controlsHeading')}</h2>
                <p className="text-xs text-secondary-500">{t('reader.dashboard.controlsHint')}</p>
              </div>
            </Card.Header>
            <Card.Body>
              <PersonalControls />
            </Card.Body>
          </Card>

          {/*
            The footnote. It used to be the whole page; it is still true, so it stays — short, plain,
            and out of the way of the part of the page that is actually usable.
          */}
          <Card className="mb-8" data-testid="dashboard-no-record">
            <Card.Header>
              <h2 className="text-lg font-semibold text-white">{t('reader.dashboard.recordHeading')}</h2>
            </Card.Header>
            <Card.Body className="space-y-3 text-sm text-secondary-300">
              {/*
                This used to end "— for you or for anyone", which was true when nothing on the
                installation could be scored at all. Settlement exists now: sources can be scored,
                so that clause would become false the first time it runs, and a sentence that goes
                stale silently is worse than no sentence. What stays true either way is the claim
                this card is actually about — your own account has no scored record — so that is
                all it claims, and the site-wide measured record is named as a separate thing.
              */}
              <p>{t('reader.dashboard.recordBody1')}</p>
              <p>{t('reader.dashboard.recordBody2')}</p>
              {/*
                The first of these is an invitation to go and read something else, so it answers
                to the prompts switch; and with forecasts off it points at the fixtures rather
                than at the predictions page, because sending a reader who asked for scores only
                to a page of tips would make the switch a lie. The second is not an invitation —
                it is how somebody reaches their own account — and nothing hides it.
              */}
              <div className="flex flex-wrap gap-3 pt-1">
                {prefs.isOn('prompts') && (
                  <Button asChild>
                    {prefs.isOn('forecasts')
                      ? <Link to="/predictions/today">{t('reader.dashboard.browsePredictions')}</Link>
                      : <Link to="/matches">{t('reader.dashboard.browseFixtures')}</Link>}
                  </Button>
                )}
                <Button variant="outline" asChild>
                  <Link to="/profile">{t('reader.dashboard.accountSettings')}</Link>
                </Button>
              </div>
            </Card.Body>
          </Card>

          {/* Site-wide coverage, clearly not presented as the reader's own activity. */}
          <Card>
            <Card.Header>
              <div>
                <h2 className="text-lg font-semibold text-white">{t('reader.dashboard.coverageHeading')}</h2>
                <p className="text-xs text-secondary-500">{t('reader.dashboard.coverageHint')}</p>
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
                        <span
                          className="inline-block h-7 w-16 animate-pulse rounded bg-dark-700"
                          aria-label={t('reader.dashboard.loadingFigure')}
                        />
                      ) : stat.value ?? (
                        <span className="text-base font-medium text-secondary-500">{t('home.statUnavailable')}</span>
                      )}
                    </div>
                    <div className="text-sm text-secondary-400">{t(stat.name)}</div>
                  </div>
                ))}
              </div>
              {!coverageLoading && !coverage && (
                <p className="mt-4 text-center text-xs text-secondary-500">
                  {t('reader.dashboard.coverageFailed')}
                </p>
              )}
              {/* The reason is the backend's own sentence and is not translated. */}
              {coverage && !coverage.accuracy_available && (
                <p className="mt-4 text-center text-xs text-secondary-500">
                  {t('reader.dashboard.noAccuracy', { reason: coverage.accuracy_unavailable_reason })}
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
