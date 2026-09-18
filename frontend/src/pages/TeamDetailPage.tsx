import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import MatchCard from '@/components/ui/MatchCard';
import { footballDataService } from '@/services/football-data.service';
import { TeamPage } from '@/services/match-data-source';
import { describeError } from '@/services/backend-match-data.service';

const TeamDetailPage: React.FC = () => {
  const { teamId } = useParams<{ teamId: string }>();
  const [page, setPage] = useState<TeamPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-950 pt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
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
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-dark-900 rounded-lg shadow-xl p-8 text-center">
            <h1 className="text-2xl font-bold text-white mb-4">{error ? 'Team data unavailable' : 'Team Not Found'}</h1>
            <p className="text-secondary-400 mb-6">{error || 'The team you are looking for does not exist.'}</p>
            <Link to="/" className="inline-block px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors">
              Go to Home
            </Link>
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
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Team Header */}
          <div className="bg-dark-900 rounded-lg shadow-xl p-8 mb-8">
            <div className="flex items-center space-x-6">
              <img
                src={team.logo}
                alt={team.name}
                className="h-24 w-24 rounded-full object-contain bg-white p-2"
                onError={(e) => { (e.target as HTMLImageElement).src = '/teams/default.svg'; }}
              />
              <div className="flex-1">
                <h1 className="text-3xl font-bold text-white mb-2">{team.name}</h1>
                <div className="flex flex-wrap gap-4 text-sm text-secondary-400">
                  {team.country && <span>🌍 {team.country}</span>}
                  {team.shortName && <span>🔤 {team.shortName}</span>}
                </div>
              </div>
            </div>
          </div>

          {/* Upcoming */}
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-white mb-4">Upcoming Matches ({upcoming.length})</h2>
            {upcoming.length === 0 ? (
              <div className="bg-dark-900 rounded-lg p-8 text-center text-secondary-400">
                No upcoming matches in the covered competitions.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {upcoming.map(match => <MatchCard key={match.id} match={match} />)}
              </div>
            )}
          </div>

          {/* Recent */}
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-white mb-4">Recent Matches ({recent.length})</h2>
            {recent.length === 0 ? (
              <div className="bg-dark-900 rounded-lg p-8 text-center text-secondary-400">
                No recent results recorded yet.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {recent.map(match => <MatchCard key={match.id} match={match} showPredictions={false} />)}
              </div>
            )}
          </div>

          <div className="mt-8">
            <Link to="/" className="inline-block px-6 py-3 bg-dark-800 text-white rounded-lg hover:bg-dark-700 transition-colors">
              ← Back to Home
            </Link>
          </div>
        </div>
      </div>
    </>
  );
};

export default TeamDetailPage;
