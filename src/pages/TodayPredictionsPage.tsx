import React, { useState } from 'react';
import { mockPredictions, mockLeagues } from '../data/mockData';
import { PredictionMarket, ConfidenceLevel, Prediction } from '../types';

const TodayPredictionsPage: React.FC = () => {
  const [selectedLeague, setSelectedLeague] = useState<string>('all');
  const [selectedMarket, setSelectedMarket] = useState<string>('all');
  const [selectedConfidence, setSelectedConfidence] = useState<string>('all');

  // Filter predictions based on selected filters
  const filteredPredictions = mockPredictions.filter((prediction) => {
    const leagueMatch = selectedLeague === 'all' || prediction.match.league.id === selectedLeague;
    const marketMatch = selectedMarket === 'all' || prediction.market === selectedMarket;
    const confidenceMatch = selectedConfidence === 'all' || prediction.confidence === selectedConfidence;

    return leagueMatch && marketMatch && confidenceMatch;
  });

  const getConfidenceColor = (confidence: ConfidenceLevel) => {
    switch (confidence) {
      case ConfidenceLevel.VERY_HIGH:
        return 'text-green-700 bg-green-100 border-green-200';
      case ConfidenceLevel.HIGH:
        return 'text-blue-700 bg-blue-100 border-blue-200';
      case ConfidenceLevel.MEDIUM:
        return 'text-yellow-700 bg-yellow-100 border-yellow-200';
      case ConfidenceLevel.LOW:
        return 'text-gray-700 bg-gray-100 border-gray-200';
      default:
        return 'text-gray-700 bg-gray-100 border-gray-200';
    }
  };

  const formatTime = (dateTime: string) => {
    return new Date(dateTime).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  const formatDate = (dateTime: string) => {
    return new Date(dateTime).toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric'
    });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Today's Predictions</h1>
        <p className="text-gray-600">
          Expert football predictions with {filteredPredictions.length} matches available today
        </p>
      </div>

      {/* Accuracy Banner */}
      <div className="bg-gradient-to-r from-green-500 to-green-600 rounded-xl p-6 mb-8 text-white">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold mb-2">89.9% Accuracy Rate</h2>
            <p className="text-green-100">Based on 1,800+ verified predictions across all markets</p>
          </div>
          <div className="hidden md:flex items-center space-x-8">
            <div className="text-center">
              <div className="text-2xl font-bold">92.3%</div>
              <div className="text-sm text-green-100">Over/Under</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold">88.7%</div>
              <div className="text-sm text-green-100">BTTS</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold">87.5%</div>
              <div className="text-sm text-green-100">1X2</div>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-8">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Filter Predictions</h3>
        <div className="grid md:grid-cols-3 gap-4">
          {/* League Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">League</label>
            <select
              value={selectedLeague}
              onChange={(e) => setSelectedLeague(e.target.value)}
              className="w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500"
            >
              <option value="all">All Leagues</option>
              {mockLeagues.map((league) => (
                <option key={league.id} value={league.id}>
                  {league.name}
                </option>
              ))}
            </select>
          </div>

          {/* Market Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Market</label>
            <select
              value={selectedMarket}
              onChange={(e) => setSelectedMarket(e.target.value)}
              className="w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500"
            >
              <option value="all">All Markets</option>
              {Object.values(PredictionMarket).map((market) => (
                <option key={market} value={market}>
                  {market}
                </option>
              ))}
            </select>
          </div>

          {/* Confidence Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Confidence</label>
            <select
              value={selectedConfidence}
              onChange={(e) => setSelectedConfidence(e.target.value)}
              className="w-full rounded-md border-gray-300 shadow-sm focus:border-purple-500 focus:ring-purple-500"
            >
              <option value="all">All Confidence Levels</option>
              {Object.values(ConfidenceLevel).map((confidence) => (
                <option key={confidence} value={confidence}>
                  {confidence.replace('_', ' ').toUpperCase()}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Predictions Grid */}
      <div className="space-y-6">
        {filteredPredictions.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-gray-500 mb-4">
              <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">No predictions found</h3>
            <p className="text-gray-500">Try adjusting your filters to see more results.</p>
          </div>
        ) : (
          filteredPredictions.map((prediction) => (
            <div key={prediction.id} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow duration-200">
              <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between">
                {/* Match Info */}
                <div className="flex-1">
                  <div className="flex items-center space-x-4 mb-4">
                    <div className="flex items-center space-x-2">
                      <img
                        src={prediction.match.league.logo}
                        alt={prediction.match.league.name}
                        className="w-6 h-6"
                        onError={(e) => {
                          e.currentTarget.src = '/placeholder-league.png';
                        }}
                      />
                      <span className="font-medium text-gray-900">{prediction.match.league.name}</span>
                    </div>
                    <div className="text-sm text-gray-500">
                      {formatDate(prediction.match.dateTime)} • {formatTime(prediction.match.dateTime)}
                    </div>
                  </div>

                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-3">
                      <img
                        src={prediction.match.homeTeam.logo}
                        alt={prediction.match.homeTeam.name}
                        className="w-8 h-8"
                        onError={(e) => {
                          e.currentTarget.src = '/placeholder-team.png';
                        }}
                      />
                      <span className="font-semibold text-gray-900 text-lg">
                        {prediction.match.homeTeam.name}
                      </span>
                    </div>
                    <span className="text-gray-400 font-medium">VS</span>
                    <div className="flex items-center space-x-3">
                      <span className="font-semibold text-gray-900 text-lg">
                        {prediction.match.awayTeam.name}
                      </span>
                      <img
                        src={prediction.match.awayTeam.logo}
                        alt={prediction.match.awayTeam.name}
                        className="w-8 h-8"
                        onError={(e) => {
                          e.currentTarget.src = '/placeholder-team.png';
                        }}
                      />
                    </div>
                  </div>
                </div>

                {/* Prediction Info */}
                <div className="lg:ml-8 lg:flex-shrink-0 lg:w-80">
                  <div className="bg-gray-50 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-medium text-gray-600">{prediction.market}</span>
                      <span
                        className={`text-xs px-2 py-1 rounded-full border font-medium ${getConfidenceColor(prediction.confidence)}`}
                      >
                        {prediction.confidence.replace('_', ' ').toUpperCase()}
                      </span>
                    </div>
                    <div className="font-bold text-lg text-gray-900 mb-3">
                      {prediction.prediction}
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-600">Accuracy Rate</span>
                      <span className="font-bold text-green-600 text-lg">{prediction.accuracy}%</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Quick Analysis */}
              {prediction.analysis.keyFactors.length > 0 && (
                <div className="mt-6 pt-6 border-t border-gray-100">
                  <h4 className="font-medium text-gray-900 mb-3">Key Factors</h4>
                  <div className="grid md:grid-cols-2 gap-2">
                    {prediction.analysis.keyFactors.slice(0, 4).map((factor, index) => (
                      <div key={index} className="flex items-center space-x-2 text-sm text-gray-600">
                        <div className="w-1.5 h-1.5 bg-purple-500 rounded-full"></div>
                        <span>{factor}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Call to Action */}
      {filteredPredictions.length > 0 && (
        <div className="mt-12 bg-purple-50 rounded-xl p-8 text-center">
          <h3 className="text-2xl font-bold text-gray-900 mb-4">Want More Detailed Analysis?</h3>
          <p className="text-gray-600 mb-6 max-w-2xl mx-auto">
            Get access to comprehensive match analysis, injury reports, team form guides, and expert commentary for every prediction.
          </p>
          <button className="btn btn-primary px-8 py-3 text-lg">
            Upgrade to Premium
          </button>
        </div>
      )}
    </div>
  );
};

export default TodayPredictionsPage;