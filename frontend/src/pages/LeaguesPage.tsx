import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { League } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import { footballDataService } from '@/services/football-data.service'
import { getErrorMessage } from '@/utils/errors'
import { onLeagueLogoError } from '@/components/ui/imageFallback'
import { useT } from '@/i18n/react'

/**
 * Every competition this installation covers.
 *
 * TWO THINGS CHANGED HERE BESIDES THE LANGUAGE, both because the page was saying something about
 * the data that was not true of it.
 *
 * 1. THE FAILURE NO LONGER NAMES A PROVIDER. It read "Failed to fetch leagues from API-Football".
 *    This read goes to our own backend, which answers it from stored rows; when it does reach a
 *    provider at all it reaches whichever one is active, and API-Football is retained only as a
 *    fallback behind Live Score. A provider named in a generic client-side failure is a claim
 *    about where the data came from, written down as a constant. `getErrorMessage` produces the
 *    server's own message where the failure carried one — untranslated, in every language — and
 *    the catalogue supplies a neutral sentence where it did not.
 *
 * 2. THE MOCK-DATA BADGE IS GONE. `usingMockData` was initialised false and set to false on both
 *    the success and the failure path, so the badge it guarded could never render: it was a
 *    warning about sample data that no longer had any way of firing. Translating it would have
 *    put a sentence in the catalogue that nothing can ever show. Nothing references it — no
 *    spec, no other module — and the honest statement about sample data still reaches a reader,
 *    from the provider banner, where it is driven by the provider status rather than by a flag
 *    nothing sets.
 */
const LeaguesPage: React.FC = () => {
  const t = useT()
  const [leagues, setLeagues] = useState<League[]>([])
  const [loading, setLoading] = useState(true)
  /**
   * A read that failed, and the server's own words for it where the failure carried any.
   *
   * THE CATALOGUE SENTENCE IS LOOKED UP DURING RENDER, NOT STORED. Storing the rendered
   * fallback froze it at whichever language the fetch happened to fail in: a reader who then
   * switched to French kept an English failure on a page that was otherwise entirely French.
   * That is the same distinction LeagueDetailPage.tsx makes for `partialError` — our own
   * sentences are a key until the moment they are drawn; the server's are a string, because
   * they are not ours to re-render in another language.
   */
  const [failure, setFailure] = useState<{ serverMessage: string | null } | null>(null)

  useEffect(() => {
    let cancelled = false
    async function fetchLeagues() {
      try {
        setLoading(true)
        setFailure(null)
        const data = await footballDataService.getTopLeagues()
        if (cancelled) return
        setLeagues(data)
      } catch (err) {
        console.error('LeaguesPage: Error fetching leagues:', err)
        if (cancelled) return
        // The backend's own message where there is one — passed through untranslated, because a
        // paraphrase of somebody else's error is a different error — and otherwise a sentence
        // that does not pretend to know which provider was involved. See note 1 above.
        setFailure({ serverMessage: getErrorMessage(err, '') || null })
        setLeagues([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchLeagues()
    return () => { cancelled = true }
    // Nothing reactive is read in here any more: the failure is stored as what the SERVER said,
    // and our own sentence is looked up where it is drawn. So a language change repaints the
    // message without re-fetching rows that have not changed.
  }, [])

  return (
    <>
      <Helmet>
        <title>{t('reader.leagues.documentTitle')}</title>
        <meta name="description" content={t('reader.leagues.documentDescription')} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">{t('reader.leagues.heading')}</h1>
            <p className="text-secondary-400">{t('reader.leagues.subheading')}</p>
          </div>

          {/* Loading State */}
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
              <div className="text-secondary-400">{t('reader.leagues.loading')}</div>
            </div>
          ) : failure ? (
            /* Error State. The server's own words where it gave any, shown as they arrived; our
               own neutral sentence where it did not, in the language on screen right now. */
            <div className="text-center py-12">
              <div className="text-red-400 mb-4">❌ {failure.serverMessage ?? t('reader.leagues.loadFailed')}</div>
              <Button onClick={() => window.location.reload()}>{t('matchday.retry')}</Button>
            </div>
          ) : leagues.length === 0 ? (
            /* No Leagues State */
            <div className="text-center py-12">
              <div className="text-secondary-400 mb-4">
                {t('reader.leagues.emptyTitle')}
              </div>
              <div className="text-secondary-500 text-sm mb-4">
                {t('reader.leagues.emptyHint')}
              </div>
              <Button onClick={() => window.location.reload()}>{t('matchday.retry')}</Button>
            </div>
          ) : (
            /* Leagues Grid. Competition, country and season are the provider's own names. */
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {leagues.map(league => (
                <Link key={league.id} to={`/league/${league.id}`}>
                  <Card hover>
                    <Card.Body>
                      <div className="flex items-center space-x-4">
                        <img
                          src={league.logo}
                          alt={league.name}
                          className="h-12 w-12 object-contain"
                          onError={onLeagueLogoError}
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
          )}
        </div>
      </div>
    </>
  )
}

export default LeaguesPage
