import React, { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { League, Team, Match, LeagueStanding } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import EmptyState from '@/components/ui/EmptyState'
import FixtureRow from '@/components/ui/FixtureRow'
import FollowButton from '@/components/favourites/FollowButton'
import useMatchSaving from '@/components/favourites/useMatchSaving'
import { footballDataService } from '@/services/football-data.service'
import apiClient from '@/services/api-client'
import { ApiMatch, describeError, mapApiMatch } from '@/services/backend-match-data.service'
import { configuredDataSource, localDateString, timezoneOffsetMinutes } from '@/services/match-data-source'
import { onTeamLogoError, onLeagueLogoError } from '@/components/ui/imageFallback'
import { useT } from '@/i18n/react'
import { formatNumber, type MessageKey } from '@/i18n'

/**
 * One competition: standings, its teams, and its next fixtures.
 *
 * TWO THINGS ARE DELIBERATE HERE.
 *
 * 1. THE FIXTURE READ ASKS FOR STORED DATA ONLY.
 *    `GET /api/v1/leagues/{id}/matches` defaults to `refresh=true`, and the backend then calls the
 *    fixture provider (`MatchDataService.sync_upcoming`). `footballDataService.getFixturesByLeague()`
 *    sends no refresh parameter, so every visit to a league page spent provider allowance on a read
 *    that only needed the rows we already hold. The signature on `MatchDataSource` takes no
 *    `MatchReadOptions` for this call, and src/services/** belongs to another package, so the read
 *    is issued here with `refresh=false` until it does. Reported for that owner.
 *    The legacy browser-side API-Football source keeps its own path unchanged.
 *
 * 2. THE TEAM LIST IS DERIVED FROM WHAT WE ALREADY FETCHED.
 *    `getTeamsByLeague()` falls back to `getFixturesByLeague()` when a competition has no standings,
 *    which would reintroduce exactly the refreshing read point 1 avoids. The same teams are already
 *    present in the standings and the fixtures we have in hand, so they are collected from those.
 *
 * A partial failure no longer replaces the page. Standings, teams and fixtures degrade
 * independently; losing one of them is a note above the sections that did load, not an error screen
 * standing in front of data we actually have.
 *
 * 3. THE DAY WINDOW IS THE READER'S ZONE, NOT THE DEVICE'S.
 *    This file carried a private `timezoneOffsetMinutes = () => -new Date().getTimezoneOffset()`,
 *    which is the DEVICE's offset. Every other fixture read on this site asks the backend for a
 *    window bounded by the zone the reader CHOSE (`localDayOffsets` in match-data-source.ts, which
 *    delegates to src/i18n/zones.ts and takes the offset at the local midnight rather than at this
 *    moment, so a daylight-saving day is still 23 or 25 hours long). A reader in Douala with a
 *    laptop still set to Paris was therefore shown a competition's fortnight cut on Paris
 *    boundaries, while the same fixtures on the matchday workspace were cut on Douala's. The
 *    shared function is now used, so the two cannot disagree — and `localDateString` below, which
 *    decides which of those fixtures count as upcoming, has always read the chosen zone.
 */

/** League fixtures without asking the backend to refresh from a provider. See note 1 above. */
async function storedLeagueFixtures(leagueId: string): Promise<Match[]> {
  if (configuredDataSource() !== 'backend') {
    return footballDataService.getFixturesByLeague(leagueId)
  }
  const { data } = await apiClient.get<{ matches: ApiMatch[] }>(
    `/api/v1/leagues/${encodeURIComponent(leagueId)}/matches`,
    { params: { days_ahead: 14, days_back: 7, refresh: false, tz_offset: timezoneOffsetMinutes() } },
  )
  return (data.matches ?? []).map(mapApiMatch)
}

/** The teams of a competition, taken from the rows already loaded rather than a second request. */
function teamsFrom(standings: LeagueStanding[], matches: Match[]): Team[] {
  const teams = new Map<string, Team>()
  standings.forEach(row => { if (row.team.id) teams.set(row.team.id, row.team) })
  if (teams.size === 0) {
    matches.forEach(match => {
      if (match.homeTeam.id) teams.set(match.homeTeam.id, match.homeTeam)
      if (match.awayTeam.id) teams.set(match.awayTeam.id, match.awayTeam)
    })
  }
  return Array.from(teams.values()).sort((a, b) => a.name.localeCompare(b.name))
}

/**
 * The standings columns: what is drawn in the header, and the full name behind it.
 *
 * The visible cell stays an abbreviation — ten full words will not fit on a phone — but an
 * abbreviation alone is unreadable, and in French it is worse than unreadable: « P » is Perdus,
 * lost, where the English "P" is Played. So every column also carries its full name as the
 * header's accessible name, which is what a screen reader announces for every cell in the
 * column beneath it.
 *
 * ── ONE COLUMN IS NOT IN THE CATALOGUE, DELIBERATELY ────────────────────────────────────────
 *
 * French writes the points column "Pts" and the word "Points" exactly as English does. A
 * catalogue pair whose two sides are the identical string is indistinguishable from a
 * translation nobody did, and `the two catalogues hold the same keys, and no French entry is
 * still its English` in e2e/mocked/localisation.spec.ts fails on precisely that — rightly, since
 * that is the shape a missed key hides in. That spec keeps a short list of words French spells
 * as English does ("leaving them alone is the translation"), and it belongs to another package.
 * So rather than adding an entry to somebody else's list, the two identical labels are stated
 * here, once, where the claim can be read and checked: `sameInBoth` means "this is the French
 * too". `reader-localisation.spec.ts` asserts both languages render them.
 */
type ColumnLabel = MessageKey | { sameInBoth: string }

const STANDINGS_COLUMNS: Array<{ short: ColumnLabel; full: ColumnLabel; align: string }> = [
  { short: 'reader.standings.position', full: 'reader.standings.positionFull', align: 'text-left' },
  { short: 'reader.standings.team', full: 'reader.standings.teamFull', align: 'text-left' },
  { short: 'reader.standings.played', full: 'reader.standings.playedFull', align: 'text-center' },
  { short: 'reader.standings.won', full: 'reader.standings.wonFull', align: 'text-center' },
  { short: 'reader.standings.drawn', full: 'reader.standings.drawnFull', align: 'text-center' },
  { short: 'reader.standings.lost', full: 'reader.standings.lostFull', align: 'text-center' },
  { short: 'reader.standings.goalsFor', full: 'reader.standings.goalsForFull', align: 'text-center' },
  { short: 'reader.standings.goalsAgainst', full: 'reader.standings.goalsAgainstFull', align: 'text-center' },
  { short: 'reader.standings.goalDifference', full: 'reader.standings.goalDifferenceFull', align: 'text-center' },
  { short: { sameInBoth: 'Pts' }, full: { sameInBoth: 'Points' }, align: 'text-center' },
]

const LeagueDetailPage: React.FC = () => {
  const t = useT()
  /** A column header, from the catalogue or from the short list of words French shares. */
  const columnLabel = (label: ColumnLabel): string => (typeof label === 'string' ? t(label) : label.sameInBoth)
  // Support both route patterns: /league/:id and /leagues/:leagueId
  const { id, leagueId } = useParams<{ id?: string; leagueId?: string }>()
  const leagueIdParam = id || leagueId

  const [league, setLeague] = useState<League | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [matches, setMatches] = useState<Match[]>([])
  const [standings, setStandings] = useState<LeagueStanding[]>([])
  const [loading, setLoading] = useState(true)
  /** The competition itself could not be loaded: there is no page to show. */
  const [fatalError, setFatalError] = useState<string | null>(null)
  /**
   * Some sections are missing. The rest of the page is still real and still shown.
   *
   * A KEY rather than a sentence: this is one of our own statements, and storing the rendered
   * English in state would have frozen it at the language the fetch happened to fail in — the
   * sentence would then have stayed English after a switch to French, on a page otherwise
   * entirely in French. The fatal error below is the opposite case and stays a string: it is the
   * backend's own words, which are not ours to re-render in another language.
   */
  const [partialError, setPartialError] = useState<MessageKey | null>(null)

  const saving = useMatchSaving()

  useEffect(() => {
    let cancelled = false
    async function fetchLeagueData() {
      if (!leagueIdParam) return

      try {
        setLoading(true)
        setFatalError(null)
        setPartialError(null)
        const foundLeague = await footballDataService.getLeague(leagueIdParam)

        if (cancelled) return
        if (!foundLeague) {
          // No fatal error is set: `league` stays null, which renders the not-found block below.
          // Setting one as well printed "League not found" underneath a heading already reading
          // "League Not Found" and a line already saying the competition could not be found.
          setLoading(false)
          return
        }

        setLeague(foundLeague)

        // Standings and calendar in parallel; each degrades independently.
        const [standingsResult, matchesResult] = await Promise.allSettled([
          footballDataService.getStandings(foundLeague.id),
          storedLeagueFixtures(foundLeague.id),
        ])
        if (cancelled) return

        const standingsData = standingsResult.status === 'fulfilled' ? standingsResult.value : []
        const matchesData = matchesResult.status === 'fulfilled' ? matchesResult.value : []
        if (standingsResult.status === 'rejected' && matchesResult.status === 'rejected') {
          throw standingsResult.reason
        }
        if (standingsResult.status === 'rejected') {
          setPartialError('reader.league.partialStandings')
        } else if (matchesResult.status === 'rejected') {
          setPartialError('reader.league.partialFixtures')
        }

        // Upcoming matches first (today onwards), earliest first
        const today = localDateString(0)
        const upcomingMatches = matchesData
          .filter(match => match.date >= today && match.status !== 'finished')
          .sort((a, b) => (a.kickoffUtc || a.date).localeCompare(b.kickoffUtc || b.date))

        setStandings(standingsData)
        setMatches(upcomingMatches)
        setTeams(teamsFrom(standingsData, matchesData))
      } catch (err) {
        console.error('Error fetching league data:', err)
        if (cancelled) return
        setFatalError(describeError(err))
        setTeams([])
        setStandings([])
        setMatches([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchLeagueData()
    return () => { cancelled = true }
  }, [leagueIdParam])

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="py-12 text-center">
            <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-b-2 border-primary-500"></div>
            <div className="text-secondary-400">{t('reader.league.loading')}</div>
          </div>
        </div>
      </div>
    )
  }

  if (!league) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="py-12 text-center">
            <h1 className="mb-4 text-2xl font-bold text-white">{t('reader.league.notFoundHeading')}</h1>
            <p className="text-secondary-400">{t('reader.league.notFoundBody')}</p>
            {fatalError && <p className="mt-2 text-danger-300">{fatalError}</p>}
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      <Helmet>
        {/* The competition's own name is the provider's and is never translated. */}
        <title>{t('reader.league.documentTitle', { league: league.name, app: t('app.name') })}</title>
        <meta
          name="description"
          content={t('reader.league.documentDescription', { league: league.name, season: league.season })}
        />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* League header, with the follow control for the competition itself. */}
          <div className="mb-8 flex flex-wrap items-center gap-4">
            <img
              src={league.logo}
              alt=""
              aria-hidden="true"
              className="h-16 w-16 object-contain"
              onError={onLeagueLogoError}
            />
            <div className="min-w-0 flex-1">
              <h1 className="text-3xl font-bold text-white">{league.name}</h1>
              <p className="text-secondary-400">{league.country}{league.season ? ` • ${league.season}` : ''}</p>
            </div>
            <FollowButton kind="league" id={league.id} name={league.name} showCount />
          </div>

          {fatalError ? (
            <Card>
              <Card.Body>
                <EmptyState
                  variant="inline"
                  tone="failed"
                  title={t('reader.league.loadFailedTitle')}
                  /* The backend's own words, shown as they arrived. */
                  description={fatalError}
                  action={<Button onClick={() => window.location.reload()}>{t('reader.league.tryAgain')}</Button>}
                />
              </Card.Body>
            </Card>
          ) : (
            <div className="space-y-8">
              {partialError && (
                <p role="status" className="rounded-lg border border-dark-700 bg-dark-900/60 px-4 py-3 text-sm text-warning-200">
                  {t(partialError)}
                </p>
              )}

              {/* Fixtures come first: the matches are what the page is for. */}
              <section aria-labelledby="league-fixtures">
                <h2 id="league-fixtures" className="mb-4 text-xl font-semibold text-white">
                  {t('reader.upcomingMatches')}
                  {matches.length > 0 && (
                    <span className="num ml-2 text-sm font-normal text-secondary-400">
                      {formatNumber(matches.length)}
                    </span>
                  )}
                </h2>
                {matches.length === 0 ? (
                  <EmptyState
                    tone="empty"
                    title={t('reader.league.noFixturesTitle')}
                    description={t('reader.league.noFixturesBody')}
                    data-testid="league-no-fixtures"
                  />
                ) : (
                  <div className="overflow-hidden rounded-xl border border-dark-800 bg-dark-900/40">
                    {matches.map(match => (
                      <FixtureRow
                        key={match.id}
                        match={match}
                        // Inside a page already headed by the competition, repeating its name on
                        // every row is noise.
                        showCompetition={false}
                        saved={saving.isSaved(match.id)}
                        savePending={saving.isPending(match.id)}
                        onToggleSave={(matchId, next) => saving.toggleSave(matchId, next, match)}
                        signedIn={saving.signedIn}
                        onRequireSignIn={saving.requireSignIn}
                      />
                    ))}
                  </div>
                )}
                {saving.signedIn && saving.failed && (
                  <p className="mt-2 text-xs text-warning-200">{t('reader.saveStateUnknown')}</p>
                )}
              </section>

              {standings.length > 0 && (
                <Card>
                  <Card.Header>
                    <h2 className="text-xl font-semibold text-white">{t('reader.league.standings')}</h2>
                  </Card.Header>
                  <Card.Body>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-dark-700">
                            {STANDINGS_COLUMNS.map(column => (
                              <th
                                key={columnLabel(column.full)}
                                scope="col"
                                aria-label={columnLabel(column.full)}
                                className={`px-2 py-3 font-medium text-secondary-400 ${column.align}`}
                              >
                                {columnLabel(column.short)}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {standings.map((standing) => (
                            <tr key={standing.team.id} className="border-b border-dark-800 transition-colors hover:bg-dark-800">
                              <td className="num px-2 py-3 font-medium text-white">{standing.position}</td>
                              <td className="px-2 py-3">
                                <div className="flex items-center space-x-2">
                                  <img
                                    src={standing.team.logo}
                                    alt=""
                                    aria-hidden="true"
                                    className="h-6 w-6 object-contain"
                                    onError={onTeamLogoError}
                                  />
                                  <span className="text-white">{standing.team.name}</span>
                                </div>
                              </td>
                              <td className="num px-2 py-3 text-center text-secondary-300">{standing.matchesPlayed}</td>
                              <td className="num px-2 py-3 text-center text-success-300">{standing.wins}</td>
                              <td className="num px-2 py-3 text-center text-warning-200">{standing.draws}</td>
                              <td className="num px-2 py-3 text-center text-danger-300">{standing.losses}</td>
                              <td className="num px-2 py-3 text-center text-secondary-300">{standing.goalsFor}</td>
                              <td className="num px-2 py-3 text-center text-secondary-300">{standing.goalsAgainst}</td>
                              <td className="num px-2 py-3 text-center text-secondary-300">{standing.goalDifference > 0 ? '+' : ''}{standing.goalDifference}</td>
                              <td className="num px-2 py-3 text-center font-bold text-white">{standing.points}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card.Body>
                </Card>
              )}

              {teams.length > 0 && (
                <Card>
                  <Card.Header>
                    {/* The count is a numeral of its own beside a label that does not inflect. */}
                    <h2 className="text-xl font-semibold text-white">
                      {t('reader.league.teams')} (<span className="num">{formatNumber(teams.length)}</span>)
                    </h2>
                  </Card.Header>
                  <Card.Body>
                    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {teams.map(team => (
                        <li key={team.id} className="flex items-center gap-3 rounded-lg bg-dark-800 px-3 py-2 transition-colors hover:bg-dark-700">
                          <img
                            src={team.logo}
                            alt=""
                            aria-hidden="true"
                            className="h-8 w-8 flex-shrink-0 object-contain"
                            onError={onTeamLogoError}
                          />
                          <Link to={`/teams/${team.id}`} className="focus-ring min-w-0 flex-1 truncate rounded text-sm text-white hover:underline">
                            {team.name}
                          </Link>
                          <FollowButton kind="team" id={team.id} name={team.name} variant="icon" size="sm" />
                        </li>
                      ))}
                    </ul>
                  </Card.Body>
                </Card>
              )}

              {teams.length === 0 && matches.length === 0 && !partialError && (
                <EmptyState
                  tone="empty"
                  title={t('reader.league.nothingTitle')}
                  description={t('reader.league.nothingBody')}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

export default LeagueDetailPage
