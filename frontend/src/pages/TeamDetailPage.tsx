import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import type { Match } from '@/types';
import EmptyState from '@/components/ui/EmptyState';
import FixtureRow from '@/components/ui/FixtureRow';
import FollowButton from '@/components/favourites/FollowButton';
import useMatchSaving from '@/components/favourites/useMatchSaving';
import { footballDataService } from '@/services/football-data.service';
import { TeamPage } from '@/services/match-data-source';
import { describeError } from '@/services/backend-match-data.service';
import { onTeamLogoError } from '@/components/ui/imageFallback'
import { formatNumber } from '@/i18n';
import { useT } from '@/i18n/react';

/**
 * One team: who they are, what is coming up, and what has been played.
 *
 * `GET /api/v1/teams/{id}` is a stored-data read — it queries the fixtures we hold and serialises
 * the forecasts already attached to them, and issues no provider request — so nothing on this page
 * spends request allowance.
 *
 * Both lists are fixture ROWS rather than the tall cards that were here before. A card repeats the
 * venue, both team labels, every market and a confidence badge per market; ten of them is a scroll
 * rather than a scan, and on a phone the card hides which source produced a number behind a
 * `title` a touch user can never open. The row keeps kickoff, teams, what each source made most
 * likely and the save control, and puts the rest behind one expand control.
 *
 * Following a team is a bookmark, not a subscription to anything, and certainly not a bet: it puts
 * the team on the personal dashboard and changes nothing about what any source publishes.
 *
 * ── ONE SENTENCE ON THIS PAGE HAD GONE FALSE ────────────────────────────────────────────────
 *
 * The note above the played fixtures ended: "Nothing on this site has been scored against a
 * result yet, so no forecast here is marked right or wrong." That was true when it was written.
 * Settlement runs on this installation now and model forecasts have been scored against final
 * results, so the sentence had become the opposite of what the home page's measured record tells
 * the same reader — a claim about the DATA frozen into a constant, which is exactly what
 * DashboardPage.tsx records having already removed from its own footnote for the same reason.
 * It now says only what stays true however much has been settled, in the words core.ts already
 * uses for the same fact on the matchday list. See `reader.team.recentNote`.
 */

const TeamDetailPage: React.FC = () => {
  const t = useT();
  const { teamId } = useParams<{ teamId: string }>();
  const [page, setPage] = useState<TeamPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const saving = useMatchSaving();

  useEffect(() => {
    let cancelled = false;
    const fetchTeam = async () => {
      if (!teamId) return;
      try {
        setLoading(true);
        setError(null);
        const result = await footballDataService.getTeam(teamId);
        if (!cancelled) setPage(result);
      } catch (err) {
        console.error('Error fetching team details:', err);
        if (!cancelled) setError(describeError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchTeam();
    return () => { cancelled = true; };
  }, [teamId]);

  const fixtureList = (matches: Match[], testId: string) => (
    <div className="overflow-hidden rounded-xl border border-dark-800 bg-dark-900/40" data-testid={testId}>
      {matches.map(match => (
        <FixtureRow
          key={match.id}
          match={match}
          saved={saving.isSaved(match.id)}
          savePending={saving.isPending(match.id)}
          onToggleSave={(id, next) => saving.toggleSave(id, next, match)}
          signedIn={saving.signedIn}
          onRequireSignIn={saving.requireSignIn}
        />
      ))}
    </div>
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-950 pt-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-center py-12">
            <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-primary-500 border-r-transparent"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !page) {
    return (
      <div className="min-h-screen bg-dark-950 pt-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="rounded-lg bg-dark-900 p-8 shadow-xl">
            <EmptyState
              variant="inline"
              // A request that failed and a team that does not exist are different facts.
              tone={error ? 'failed' : 'empty'}
              title={error ? t('reader.team.loadFailedTitle') : t('reader.team.notFoundTitle')}
              /* `error` is the backend's own words, shown as they arrived. */
              description={error ?? t('reader.team.notFoundBody')}
              action={
                <Link
                  to="/"
                  className="focus-ring inline-block rounded-lg bg-primary-600 px-6 py-3 text-white transition-colors hover:bg-primary-700"
                >
                  {t('reader.team.goHome')}
                </Link>
              }
            />
          </div>
        </div>
      </div>
    );
  }

  const { team, upcoming, recent } = page;

  return (
    <>
      <Helmet>
        {/* The club's own name is the provider's and is never translated. */}
        <title>{t('reader.team.documentTitle', { team: team.name, app: t('app.name') })}</title>
      </Helmet>
      <div className="min-h-screen bg-dark-950 pt-20">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          {/* Team header, with the follow control. */}
          <div className="mb-8 rounded-lg bg-dark-900 p-6 shadow-xl sm:p-8">
            <div className="flex flex-wrap items-center gap-6">
              <img
                src={team.logo}
                alt=""
                aria-hidden="true"
                className="h-24 w-24 rounded-full bg-white object-contain p-2"
                onError={onTeamLogoError}
              />
              <div className="min-w-0 flex-1">
                <h1 className="mb-2 text-3xl font-bold text-white">{team.name}</h1>
                <div className="flex flex-wrap gap-4 text-sm text-secondary-400">
                  {team.country && <span>{team.country}</span>}
                  {team.shortName && <span>{team.shortName}</span>}
                </div>
              </div>
              <FollowButton kind="team" id={team.id} name={team.name} showCount />
            </div>
          </div>

          {saving.signedIn && saving.failed && (
            <p className="mb-4 text-xs text-warning-200">{t('reader.saveStateUnknown')}</p>
          )}

          <section className="mb-8" aria-labelledby="team-upcoming">
            <h2 id="team-upcoming" className="mb-4 text-2xl font-bold text-white">
              {t('reader.upcomingMatches')}
              <span className="num ml-2 text-base font-normal text-secondary-400">{formatNumber(upcoming.length)}</span>
            </h2>
            {upcoming.length === 0 ? (
              <EmptyState
                tone="empty"
                title={t('reader.team.noUpcomingTitle')}
                description={t('reader.team.noUpcomingBody')}
              />
            ) : fixtureList(upcoming, 'team-upcoming-list')}
          </section>

          <section className="mb-8" aria-labelledby="team-recent">
            <h2 id="team-recent" className="mb-4 text-2xl font-bold text-white">
              {t('reader.team.recentMatches')}
              <span className="num ml-2 text-base font-normal text-secondary-400">{formatNumber(recent.length)}</span>
            </h2>
            {recent.length === 0 ? (
              <EmptyState
                tone="empty"
                title={t('reader.team.noRecentTitle')}
                description={t('reader.team.noRecentBody')}
              />
            ) : (
              <>
                {/* Said where a reader might otherwise read the expanded rows as a scorecard. */}
                <p className="mb-2 text-xs text-secondary-400">{t('reader.team.recentNote')}</p>
                {fixtureList(recent, 'team-recent-list')}
              </>
            )}
          </section>

          <div className="mt-8">
            <Link to="/" className="focus-ring inline-block rounded-lg bg-dark-800 px-6 py-3 text-white transition-colors hover:bg-dark-700">
              ← {t('reader.backToHome')}
            </Link>
          </div>
        </div>
      </div>
    </>
  );
};

export default TeamDetailPage;
