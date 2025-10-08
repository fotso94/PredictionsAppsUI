/**
 * API Test Page
 * 
 * This page allows you to test the API-Football integration
 * Use this to verify the API is working before integrating into main components
 */

import { useState } from 'react';
import { footballDataService, POPULAR_LEAGUES } from '@/services/football-data.service';
import { League, Team, Match } from '@/types';

export default function APITestPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [leagues, setLeagues] = useState<League[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [activeTab, setActiveTab] = useState<'leagues' | 'teams' | 'matches'>('leagues');

  const handleError = (err: unknown) => {
    const message = err instanceof Error ? err.message : 'An unknown error occurred';
    setError(message);
    console.error('API Error:', err);
  };

  const testTopLeagues = async () => {
    setLoading(true);
    setError(null);
    console.log('Testing top leagues...');
    try {
      const data = await footballDataService.getTopLeagues();
      console.log('Top leagues received:', data.length, 'leagues');
      setLeagues(data);
      setActiveTab('leagues');
      if (data.length === 0) {
        setError('No leagues found. This might be a season data issue.');
      }
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  };

  const testPremierLeagueTeams = async () => {
    setLoading(true);
    setError(null);
    console.log('Testing Premier League teams...');
    try {
      const data = await footballDataService.getTeamsByLeague(POPULAR_LEAGUES.PREMIER_LEAGUE);
      console.log('Teams received:', data.length, 'teams');
      setTeams(data);
      setActiveTab('teams');
      if (data.length === 0) {
        setError('No teams found. This might be a season data issue.');
      }
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  };

  const testTodayMatches = async () => {
    setLoading(true);
    setError(null);
    const today = new Date().toISOString().split('T')[0];
    console.log('Testing today\'s matches for:', today);
    try {
      const data = await footballDataService.getTodayFixtures();
      console.log('Matches received:', data.length, 'matches');
      setMatches(data);
      setActiveTab('matches');
      if (data.length === 0) {
        setError(`No matches found for today (${today}). Try tomorrow's matches or a different date.`);
      }
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  };

  const testTomorrowMatches = async () => {
    setLoading(true);
    setError(null);
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];
    console.log('Testing tomorrow\'s matches for:', tomorrowStr);
    try {
      const data = await footballDataService.getTomorrowFixtures();
      console.log('Matches received:', data.length, 'matches');
      setMatches(data);
      setActiveTab('matches');
      if (data.length === 0) {
        setError(`No matches found for tomorrow (${tomorrowStr}).`);
      }
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  };

  const clearCache = () => {
    footballDataService.clearCache();
    alert('Cache cleared successfully!');
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">🧪 API-Football Integration Test</h1>
          <p className="mt-2 text-gray-600">
            Test the API-Football integration to verify everything is working correctly
          </p>
        </div>

        {/* Action Buttons */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Test Actions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <button
              onClick={testTopLeagues}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-3 px-4 rounded-lg transition-colors"
            >
              Get Top Leagues
            </button>
            <button
              onClick={testPremierLeagueTeams}
              disabled={loading}
              className="bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-medium py-3 px-4 rounded-lg transition-colors"
            >
              Get Premier League Teams
            </button>
            <button
              onClick={testTodayMatches}
              disabled={loading}
              className="bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white font-medium py-3 px-4 rounded-lg transition-colors"
            >
              Get Today's Matches
            </button>
            <button
              onClick={testTomorrowMatches}
              disabled={loading}
              className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white font-medium py-3 px-4 rounded-lg transition-colors"
            >
              Get Tomorrow's Matches
            </button>
            <button
              onClick={clearCache}
              disabled={loading}
              className="bg-yellow-600 hover:bg-yellow-700 disabled:bg-gray-400 text-white font-medium py-3 px-4 rounded-lg transition-colors"
            >
              Clear Cache
            </button>
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-6">
            <div className="flex items-center">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mr-3"></div>
              <p className="text-blue-800 font-medium">Loading data from API...</p>
            </div>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
            <h3 className="text-red-800 font-semibold mb-2">❌ Error</h3>
            <p className="text-red-700">{error}</p>
            <p className="text-red-600 text-sm mt-2">Check the browser console for more details.</p>
          </div>
        )}

        {/* Results */}
        <div className="bg-white rounded-lg shadow">
          {/* Tabs */}
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              <button
                onClick={() => setActiveTab('leagues')}
                className={`py-4 px-6 font-medium text-sm border-b-2 transition-colors ${
                  activeTab === 'leagues'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Leagues ({leagues.length})
              </button>
              <button
                onClick={() => setActiveTab('teams')}
                className={`py-4 px-6 font-medium text-sm border-b-2 transition-colors ${
                  activeTab === 'teams'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Teams ({teams.length})
              </button>
              <button
                onClick={() => setActiveTab('matches')}
                className={`py-4 px-6 font-medium text-sm border-b-2 transition-colors ${
                  activeTab === 'matches'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Matches ({matches.length})
              </button>
            </nav>
          </div>

          {/* Tab Content */}
          <div className="p-6">
            {/* Leagues Tab */}
            {activeTab === 'leagues' && (
              <div>
                {leagues.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">
                    No leagues loaded. Click "Get Top Leagues" to fetch data.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {leagues.map((league) => (
                      <div key={league.id} className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                        <div className="flex items-center gap-3">
                          <img src={league.logo} alt={league.name} className="w-12 h-12 object-contain" />
                          <div className="flex-1">
                            <h3 className="font-semibold text-gray-900">{league.name}</h3>
                            <p className="text-sm text-gray-600">{league.country}</p>
                            <p className="text-xs text-gray-500">Season: {league.season}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Teams Tab */}
            {activeTab === 'teams' && (
              <div>
                {teams.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">
                    No teams loaded. Click "Get Premier League Teams" to fetch data.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {teams.map((team) => (
                      <div key={team.id} className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                        <div className="flex items-center gap-3">
                          <img src={team.logo} alt={team.name} className="w-12 h-12 object-contain" />
                          <div className="flex-1">
                            <h3 className="font-semibold text-gray-900">{team.name}</h3>
                            <p className="text-sm text-gray-600">{team.venue}</p>
                            <p className="text-xs text-gray-500">Founded: {team.founded}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Matches Tab */}
            {activeTab === 'matches' && (
              <div>
                {matches.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">
                    No matches loaded. Click "Get Today's Matches" or "Get Tomorrow's Matches" to fetch data.
                  </p>
                ) : (
                  <div className="space-y-4">
                    {matches.map((match) => (
                      <div key={match.id} className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4 flex-1">
                            {/* Home Team */}
                            <div className="flex items-center gap-2 flex-1">
                              <img src={match.homeTeam.logo} alt={match.homeTeam.name} className="w-8 h-8 object-contain" />
                              <span className="font-medium text-gray-900">{match.homeTeam.name}</span>
                            </div>

                            {/* Score/Time */}
                            <div className="text-center px-4">
                              {match.result ? (
                                <div className="text-xl font-bold text-gray-900">
                                  {match.result.homeScore} - {match.result.awayScore}
                                </div>
                              ) : (
                                <div className="text-sm text-gray-600">{match.time}</div>
                              )}
                              <div className="text-xs text-gray-500 mt-1">{match.status}</div>
                            </div>

                            {/* Away Team */}
                            <div className="flex items-center gap-2 flex-1 justify-end">
                              <span className="font-medium text-gray-900">{match.awayTeam.name}</span>
                              <img src={match.awayTeam.logo} alt={match.awayTeam.name} className="w-8 h-8 object-contain" />
                            </div>
                          </div>
                        </div>
                        <div className="mt-2 pt-2 border-t border-gray-100">
                          <div className="flex items-center justify-between text-xs text-gray-500">
                            <span>{match.league.name}</span>
                            <span>{match.date}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Debug Info */}
        <div className="mt-6 bg-gray-100 rounded-lg p-4">
          <h3 className="font-semibold text-gray-700 mb-2">Debug Info</h3>
          <div className="text-sm text-gray-600 space-y-1">
            <p>• Leagues loaded: {leagues.length}</p>
            <p>• Teams loaded: {teams.length}</p>
            <p>• Matches loaded: {matches.length}</p>
            <p>• Cache: 5-minute duration</p>
            <p>• API: API-Football v3 (RapidAPI)</p>
          </div>
        </div>
      </div>
    </div>
  );
}

