import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import apiFootballService, { APITeam } from '@/services/api-football.service';

const TeamDetailPage: React.FC = () => {
  const { teamId } = useParams<{ teamId: string }>();
  const [team, setTeam] = useState<APITeam | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTeamDetails = async () => {
      if (!teamId) return;

      try {
        setLoading(true);
        setError(null);

        // Fetch team details from Premier League (you can adjust this)
        const response = await apiFootballService.getTeams({
          league: 39, // Premier League
          season: 2024,
          id: parseInt(teamId),
        });

        if (response.response && response.response.length > 0) {
          setTeam(response.response[0]);
        } else {
          setError('Team not found');
        }
      } catch (err) {
        console.error('Error fetching team details:', err);
        setError('Failed to load team details');
      } finally {
        setLoading(false);
      }
    };

    fetchTeamDetails();
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

  if (error || !team) {
    return (
      <div className="min-h-screen bg-dark-950 pt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-dark-900 rounded-lg shadow-xl p-8 text-center">
            <h1 className="text-2xl font-bold text-white mb-4">Team Not Found</h1>
            <p className="text-secondary-400 mb-6">{error || 'The team you are looking for does not exist.'}</p>
            <Link
              to="/"
              className="inline-block px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              Go to Home
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dark-950 pt-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Team Header */}
        <div className="bg-dark-900 rounded-lg shadow-xl p-8 mb-8">
          <div className="flex items-center space-x-6">
            <img
              src={team.team.logo}
              alt={team.team.name}
              className="h-24 w-24 rounded-full object-cover bg-white"
              onError={(e) => {
                (e.target as HTMLImageElement).src = 'https://via.placeholder.com/96?text=Team';
              }}
            />
            <div className="flex-1">
              <h1 className="text-3xl font-bold text-white mb-2">{team.team.name}</h1>
              <div className="flex flex-wrap gap-4 text-sm text-secondary-400">
                <span>🌍 {team.team.country}</span>
                {team.team.founded && <span>📅 Founded: {team.team.founded}</span>}
                {team.team.code && <span>🔤 Code: {team.team.code}</span>}
                {team.team.national && <span>🏆 National Team</span>}
              </div>
            </div>
          </div>
        </div>

        {/* Venue Information */}
        {team.venue && (
          <div className="bg-dark-900 rounded-lg shadow-xl p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-4">Venue Information</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-2">{team.venue.name}</h3>
                <div className="space-y-2 text-sm text-secondary-400">
                  {team.venue.city && <p>📍 {team.venue.city}</p>}
                  {team.venue.address && <p>🏠 {team.venue.address}</p>}
                  {team.venue.capacity && <p>👥 Capacity: {team.venue.capacity.toLocaleString()}</p>}
                  {team.venue.surface && <p>🌱 Surface: {team.venue.surface}</p>}
                </div>
              </div>
              {team.venue.image && (
                <div>
                  <img
                    src={team.venue.image}
                    alt={team.venue.name}
                    className="w-full h-48 object-cover rounded-lg"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                    }}
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Placeholder for Future Features */}
        <div className="bg-dark-900 rounded-lg shadow-xl p-8">
          <h2 className="text-2xl font-bold text-white mb-4">Coming Soon</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-dark-800 rounded-lg p-6 text-center">
              <p className="text-4xl mb-2">📊</p>
              <h3 className="text-lg font-semibold text-white mb-2">Team Statistics</h3>
              <p className="text-sm text-secondary-400">View detailed team performance stats</p>
            </div>
            <div className="bg-dark-800 rounded-lg p-6 text-center">
              <p className="text-4xl mb-2">⚽</p>
              <h3 className="text-lg font-semibold text-white mb-2">Upcoming Matches</h3>
              <p className="text-sm text-secondary-400">See all scheduled fixtures</p>
            </div>
            <div className="bg-dark-800 rounded-lg p-6 text-center">
              <p className="text-4xl mb-2">👥</p>
              <h3 className="text-lg font-semibold text-white mb-2">Squad</h3>
              <p className="text-sm text-secondary-400">Browse team players and staff</p>
            </div>
          </div>
        </div>

        {/* Back Button */}
        <div className="mt-8">
          <Link
            to="/"
            className="inline-block px-6 py-3 bg-dark-800 text-white rounded-lg hover:bg-dark-700 transition-colors"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    </div>
  );
};

export default TeamDetailPage;

