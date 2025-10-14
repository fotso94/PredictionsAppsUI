/**
 * Expert Match Selection Page
 * Page for experts to browse available matches and create predictions
 */

import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { footballDataService } from '../services/football-data.service';
import { Match } from '../types';

const ExpertMatchSelectionPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [todayMatches, setTodayMatches] = useState<Match[]>([]);
  const [tomorrowMatches, setTomorrowMatches] = useState<Match[]>([]);
  const [selectedMatchId, setSelectedMatchId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');

  useEffect(() => {
    loadMatches();
  }, []);

  const loadMatches = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [today, tomorrow] = await Promise.all([
        footballDataService.getTodayFixtures(),
        footballDataService.getTomorrowFixtures(),
      ]);
      
      setTodayMatches(today);
      setTomorrowMatches(tomorrow);
    } catch (err: any) {
      console.error('Failed to load matches:', err);
      setError(err.message || 'Failed to load matches');
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePrediction = (matchId: string) => {
    // Navigate to create prediction page with match ID pre-filled
    navigate(`/expert/predictions/create?matchId=${matchId}`);
  };

  // Filter matches based on search query
  const filterMatches = (matches: Match[]) => {
    if (!searchQuery.trim()) return matches;

    const query = searchQuery.toLowerCase();
    return matches.filter(match =>
      match.homeTeam.name.toLowerCase().includes(query) ||
      match.awayTeam.name.toLowerCase().includes(query)
    );
  };

  const filteredTodayMatches = filterMatches(todayMatches);
  const filteredTomorrowMatches = filterMatches(tomorrowMatches);

  const renderMatchCard = (match: Match) => (
    <div
      key={match.id}
      className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
    >
      {/* Match Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            {match.league.name}
          </span>
          <span className="text-xs text-gray-400">•</span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {match.date} {match.time}
          </span>
        </div>
        <span className={`text-xs px-2 py-1 rounded ${
          match.status === 'live'
            ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
            : 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200'
        }`}>
          {match.status}
        </span>
      </div>

      {/* Teams */}
      <div className="grid grid-cols-3 gap-4 items-center mb-4">
        {/* Home Team */}
        <div className="text-center">
          <img
            src={match.homeTeam.logo}
            alt={match.homeTeam.name}
            className="w-12 h-12 mx-auto mb-2"
            onError={(e) => {
              e.currentTarget.src = 'https://via.placeholder.com/48?text=Team';
            }}
          />
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {match.homeTeam.name}
          </p>
        </div>

        {/* VS or Live Score */}
        <div className="text-center">
          {match.result && (match.status === 'live' || match.status === 'halftime') ? (
            <div>
              <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                {match.result.homeScore} - {match.result.awayScore}
              </p>
              {match.status === 'halftime' && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">HT</p>
              )}
            </div>
          ) : (
            <p className="text-lg font-bold text-gray-500 dark:text-gray-400">VS</p>
          )}
        </div>

        {/* Away Team */}
        <div className="text-center">
          <img
            src={match.awayTeam.logo}
            alt={match.awayTeam.name}
            className="w-12 h-12 mx-auto mb-2"
            onError={(e) => {
              e.currentTarget.src = 'https://via.placeholder.com/48?text=Team';
            }}
          />
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {match.awayTeam.name}
          </p>
        </div>
      </div>

      {/* Match Details */}
      <div className="mb-4 text-xs text-gray-600 dark:text-gray-400">
        <p>Venue: {match.venue}</p>
        <p>Round: {match.round}</p>
        <p className="font-mono text-xs text-gray-500 mt-2">ID: {match.id}</p>
      </div>

      {/* Action Button */}
      <button
        onClick={() => handleCreatePrediction(match.id)}
        className="w-full px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
      >
        Create Prediction for This Match
      </button>
    </div>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading matches...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <Link
          to="/expert/dashboard"
          className="text-blue-600 hover:text-blue-700 mb-4 inline-block"
        >
          ← Back to Dashboard
        </Link>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          Select Match for Prediction
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Choose a match from today's or tomorrow's fixtures to create your expert prediction
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg">
          ⚠️ {error}
        </div>
      )}

      {/* Search Filter */}
      <div className="mb-8 bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
          🔍 Search Matches by Team Name
        </h2>
        <div className="flex gap-4">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Enter team name (e.g., Arsenal, Barcelona, etc.)"
            className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="px-6 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
        {searchQuery && (
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Showing {filteredTodayMatches.length + filteredTomorrowMatches.length} matches for "{searchQuery}"
          </p>
        )}
      </div>

      {/* Manual Match ID Input */}
      <div className="mb-8 bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
          Or Enter Match ID Manually
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          If you already have a match ID from API-Football, you can enter it here to create a prediction directly.
        </p>
        <div className="flex gap-4">
          <input
            type="text"
            value={selectedMatchId}
            onChange={(e) => setSelectedMatchId(e.target.value)}
            placeholder="Enter API-Football match ID (e.g., 1445646)"
            className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-purple-500 dark:bg-gray-700 dark:text-white"
          />
          <button
            onClick={() => selectedMatchId && handleCreatePrediction(selectedMatchId)}
            disabled={!selectedMatchId}
            className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Create Prediction
          </button>
        </div>
      </div>

      {/* Today's Matches */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
          Today's Matches ({filteredTodayMatches.length})
        </h2>
        {filteredTodayMatches.length === 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-8 text-center">
            <p className="text-gray-600 dark:text-gray-400">
              {searchQuery ? `No matches found for "${searchQuery}"` : 'No matches scheduled for today'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredTodayMatches.map(renderMatchCard)}
          </div>
        )}
      </div>

      {/* Tomorrow's Matches */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
          Tomorrow's Matches ({filteredTomorrowMatches.length})
        </h2>
        {filteredTomorrowMatches.length === 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-8 text-center">
            <p className="text-gray-600 dark:text-gray-400">
              {searchQuery ? `No matches found for "${searchQuery}"` : 'No matches scheduled for tomorrow'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredTomorrowMatches.map(renderMatchCard)}
          </div>
        )}
      </div>

      {/* Help Section */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-200 mb-2">
          💡 How to Create Predictions
        </h3>
        <ol className="list-decimal list-inside space-y-2 text-sm text-blue-800 dark:text-blue-300">
          <li>Use the search box to filter matches by team name</li>
          <li>Browse today's or tomorrow's matches below</li>
          <li>Click "Create Prediction for This Match" on any match card</li>
          <li>The match ID will be automatically filled in the prediction form</li>
          <li>Enter your probabilities, confidence score, and reasoning</li>
          <li>Submit your prediction for review</li>
        </ol>
        <p className="mt-4 text-sm text-blue-700 dark:text-blue-400">
          <strong>Note:</strong> Match IDs from API-Football are numeric (e.g., 1445646).
          You can also manually enter a match ID if you have one from the API.
        </p>
      </div>
    </div>
  );
};

export default ExpertMatchSelectionPage;

