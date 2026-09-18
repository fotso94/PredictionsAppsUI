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
import { configuredDataSource, localDateString } from '@/services/match-data-source'
import { onTeamLogoError, onLeagueLogoError } from '@/components/ui/imageFallback'

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
 */

/** Minutes east of UTC, the sign the backend's `tz_offset` expects (`-getTimezoneOffset()`). */
const timezoneOffsetMinutes = (): number => -new Date().getTimezoneOffset()

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

const LeagueDetailPage: React.FC = () => {
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
  /** Some sections are missing. The rest of the page is still real and still shown. */
  const [partialError, setPartialError] = useState<string | null>(null)

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
          setFatalError('League not found')
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
          setPartialError('The standings table could not be loaded, so it is not shown.')
        } else if (matchesResult.status === 'rejected') {
          setPartialError('The fixture list could not be loaded, so it is not shown.')
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
            <div className="text-secondary-400">Loading league details...</div>
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
            <h1 className="mb-4 text-2xl font-bold text-white">League Not Found</h1>
            <p className="text-secondary-400">The requested league could not be found.</p>
            {fatalError && <p className="mt-2 text-danger-300">{fatalError}</p>}
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      <Helmet>
        <title>{league.name} - Soccer Predictions</title>
        <meta name="description" content={`${league.name} standings, fixtures and published forecasts for the ${league.season} season.`} />
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
                  title="This competition could not be loaded."
                  description={fatalError}
                  action={<Button onClick={() => window.location.reload()}>Try again</Button>}
                />
              </Card.Body>
            </Card>
          ) : (
            <div className="space-y-8">
              {partialError && (
                <p role="status" className="rounded-lg border border-dark-700 bg-dark-900/60 px-4 py-3 text-sm text-warning-200">
                  {partialError}
                </p>
              )}

              {/* Fixtures come first: the matches are what the page is for. */}
              <section aria-labelledby="league-fixtures">
                <h2 id="league-fixtures" className="mb-4 text-xl font-semibold text-white">
                  Upcoming matches
                  {matches.length > 0 && <span className="num ml-2 text-sm font-normal text-secondary-400">{matches.length}</span>}
                </h2>
                {matches.length === 0 ? (
                  <EmptyState
                    tone="empty"
                    title="No upcoming fixtures are stored for this competition."
                    description="Nothing is scheduled in the next two weeks in the data we hold."
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
                  <p className="mt-2 text-xs text-warning-200">
                    We could not load your saved matches, so the save control cannot show which of
                    these you have already saved.
                  </p>
                )}
              </section>

              {standings.length > 0 && (
                <Card>
                  <Card.Header>
                    <h2 className="text-xl font-semibold text-white">Standings</h2>
                  </Card.Header>
                  <Card.Body>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-dark-700">
                            <th className="px-2 py-3 text-left font-medium text-secondary-400">#</th>
                            <th className="px-2 py-3 text-left font-medium text-secondary-400">Team</th>
                            <th className="px-2 py-3 text-center font-medium text-secondary-400">P</th>
                            <th className="px-2 py-3 text-center font-medium text-secondary-400">W</th>
                            <th className="px-2 py-3 text-center font-medium text-secondary-400">D</th>
                            <th className="px-2 py-3 text-center font-medium text-secondary-400">L</th>
                            <th className="px-2 py-3 text-center font-medium text-secondary-400">GF</th>
                            <th className="px-2 py-3 text-center font-medium text-secondary-400">GA</th>
                            <th className="px-2 py-3 text-center font-medium text-secondary-400">GD</th>
                            <th className="px-2 py-3 text-center font-medium text-secondary-400">Pts</th>
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
                    <h2 className="text-xl font-semibold text-white">Teams ({teams.length})</h2>
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
                  title="No teams or fixtures are stored for this competition."
                  description="Nothing has been loaded for it yet."
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
