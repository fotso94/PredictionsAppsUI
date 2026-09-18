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
 */

const TeamDetailPage: React.FC = () => {
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
              title={error ? 'This team could not be loaded.' : 'Team not found.'}
              description={error ?? 'There is no team with that identifier in the data we hold.'}
              action={
                <Link
                  to="/"
                  className="focus-ring inline-block rounded-lg bg-primary-600 px-6 py-3 text-white transition-colors hover:bg-primary-700"
                >
                  Go to Home
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
        <title>{team.name} - Soccer Predictions</title>
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
            <p className="mb-4 text-xs text-warning-200">
              We could not load your saved matches, so the save control cannot show which of these
              you have already saved.
            </p>
          )}

          <section className="mb-8" aria-labelledby="team-upcoming">
            <h2 id="team-upcoming" className="mb-4 text-2xl font-bold text-white">
              Upcoming matches
              <span className="num ml-2 text-base font-normal text-secondary-400">{upcoming.length}</span>
            </h2>
            {upcoming.length === 0 ? (
              <EmptyState
                tone="empty"
                title="No upcoming matches are stored for this team."
                description="Nothing is scheduled for them in the competitions this site covers."
              />
            ) : fixtureList(upcoming, 'team-upcoming-list')}
          </section>

          <section className="mb-8" aria-labelledby="team-recent">
            <h2 id="team-recent" className="mb-4 text-2xl font-bold text-white">
              Recent matches
              <span className="num ml-2 text-base font-normal text-secondary-400">{recent.length}</span>
            </h2>
            {recent.length === 0 ? (
              <EmptyState
                tone="empty"
                title="No results are recorded for this team yet."
                description="Nothing they have played is stored here."
              />
            ) : (
              <>
                {/* Said where a reader might otherwise read the expanded rows as a scorecard. */}
                <p className="mb-2 text-xs text-secondary-400">
                  Final scores, with what each source published beforehand. Nothing on this site has
                  been scored against a result yet, so no forecast here is marked right or wrong.
                </p>
                {fixtureList(recent, 'team-recent-list')}
              </>
            )}
          </section>

          <div className="mt-8">
            <Link to="/" className="focus-ring inline-block rounded-lg bg-dark-800 px-6 py-3 text-white transition-colors hover:bg-dark-700">
              ← Back to Home
            </Link>
          </div>
        </div>
      </div>
    </>
  );
};

export default TeamDetailPage;
