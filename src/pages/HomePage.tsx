import React from 'react';
import { Link } from 'react-router-dom';
import { mockDashboardStats, mockPredictions, mockLeagues } from '../data/mockData';
import { PredictionMarket, ConfidenceLevel } from '../types';

const HomePage: React.FC = () => {
  const stats = mockDashboardStats;
  const todaysPredictions = mockPredictions.slice(0, 3);
  const topLeagues = mockLeagues.slice(0, 6);

  const getConfidenceColor = (confidence: ConfidenceLevel) => {
    switch (confidence) {
      case ConfidenceLevel.VERY_HIGH:
        return 'text-green-600 bg-green-50 border-green-200';
      case ConfidenceLevel.HIGH:
        return 'text-blue-600 bg-blue-50 border-blue-200';
      case ConfidenceLevel.MEDIUM:
        return 'text-yellow-600 bg-yellow-50 border-yellow-200';
      case ConfidenceLevel.LOW:
        return 'text-gray-600 bg-gray-50 border-gray-200';
      default:
        return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const formatTime = (dateTime: string) => {
    return new Date(dateTime).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <section className="relative bg-gradient-to-br from-purple-900 via-purple-800 to-purple-700 text-white overflow-hidden">
        <div className="absolute inset-0 bg-black opacity-20"></div>
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <h1 className="text-4xl lg:text-6xl font-bold mb-6 leading-tight">
                Professional
                <span className="block text-transparent bg-clip-text bg-gradient-to-r from-green-400 to-green-300">
                  Soccer Predictions
                </span>
              </h1>
              <p className="text-xl lg:text-2xl mb-8 text-purple-100">
                Join thousands of successful bettors with our industry-leading{' '}
                <span className="font-bold text-green-300">89.9% accuracy rate</span>
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <Link
                  to="/predictions/today"
                  className="btn bg-green-500 hover:bg-green-600 text-white font-semibold px-8 py-4 text-lg"
                >
                  View Today's Predictions
                </Link>
                <Link
                  to="/academy"
                  className="btn bg-white bg-opacity-20 backdrop-blur-sm hover:bg-opacity-30 text-white font-semibold px-8 py-4 text-lg border border-white border-opacity-30"
                >
                  Learn to Bet
                </Link>
              </div>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white bg-opacity-10 backdrop-blur-sm rounded-xl p-6 border border-white border-opacity-20">
                <div className="text-3xl font-bold text-green-300 mb-2">
                  {stats.accuracy.overall}%
                </div>
                <div className="text-sm text-purple-100">Overall Accuracy</div>
              </div>
              <div className="bg-white bg-opacity-10 backdrop-blur-sm rounded-xl p-6 border border-white border-opacity-20">
                <div className="text-3xl font-bold text-green-300 mb-2">
                  {stats.totalPredictions.toLocaleString()}+
                </div>
                <div className="text-sm text-purple-100">Verified Predictions</div>
              </div>
              <div className="bg-white bg-opacity-10 backdrop-blur-sm rounded-xl p-6 border border-white border-opacity-20">
                <div className="text-3xl font-bold text-green-300 mb-2">
                  300+
                </div>
                <div className="text-sm text-purple-100">Global Leagues</div>
              </div>
              <div className="bg-white bg-opacity-10 backdrop-blur-sm rounded-xl p-6 border border-white border-opacity-20">
                <div className="text-3xl font-bold text-green-300 mb-2">
                  {stats.roi}%
                </div>
                <div className="text-sm text-purple-100">Average ROI</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Today's Top Predictions */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-3xl font-bold text-gray-900">Today's Top Predictions</h2>
          <Link
            to="/predictions/today"
            className="text-purple-600 hover:text-purple-700 font-medium flex items-center"
          >
            View All
            <svg className="ml-2 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {todaysPredictions.map((prediction) => (
            <div key={prediction.id} className="prediction-card">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                  <img
                    src={prediction.match.league.logo}
                    alt={prediction.match.league.name}
                    className="w-6 h-6"
                    onError={(e) => {
                      e.currentTarget.src = '/placeholder-league.png';
                    }}
                  />
                  <span className="text-sm font-medium text-gray-600">
                    {prediction.match.league.name}
                  </span>
                </div>
                <span className="text-sm text-gray-500">
                  {formatTime(prediction.match.dateTime)}
                </span>
              </div>

              <div className="mb-4">
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center space-x-2">
                    <img
                      src={prediction.match.homeTeam.logo}
                      alt={prediction.match.homeTeam.name}
                      className="w-5 h-5"
                      onError={(e) => {
                        e.currentTarget.src = '/placeholder-team.png';
                      }}
                    />
                    <span className="font-medium">{prediction.match.homeTeam.name}</span>
                  </div>
                  <span className="text-gray-400">vs</span>
                  <div className="flex items-center space-x-2">
                    <span className="font-medium">{prediction.match.awayTeam.name}</span>
                    <img
                      src={prediction.match.awayTeam.logo}
                      alt={prediction.match.awayTeam.name}
                      className="w-5 h-5"
                      onError={(e) => {
                        e.currentTarget.src = '/placeholder-team.png';
                      }}
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">{prediction.market}</span>
                  <span
                    className={`text-xs px-2 py-1 rounded-full border ${getConfidenceColor(prediction.confidence)}`}
                  >
                    {prediction.confidence.replace('_', ' ').toUpperCase()}
                  </span>
                </div>
                <div className="font-semibold text-gray-900">{prediction.prediction}</div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Accuracy</span>
                  <span className="font-semibold text-green-600">{prediction.accuracy}%</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Featured Leagues */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-8">Featured Leagues</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {topLeagues.map((league) => (
            <Link
              key={league.id}
              to={`/leagues/${league.name.toLowerCase().replace(/\s+/g, '-')}`}
              className="card text-center hover:shadow-lg transition-shadow duration-200"
            >
              <img
                src={league.logo}
                alt={league.name}
                className="w-12 h-12 mx-auto mb-3"
                onError={(e) => {
                  e.currentTarget.src = '/placeholder-league.png';
                }}
              />
              <h3 className="font-medium text-gray-900 text-sm">{league.name}</h3>
              <p className="text-xs text-gray-500 mt-1">{league.country}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* Accuracy Breakdown */}
      <section className="bg-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Proven Track Record
            </h2>
            <p className="text-xl text-gray-600 max-w-3xl mx-auto">
              Our predictions are backed by advanced algorithms, expert analysis, and years of proven results
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="card text-center">
              <div className="text-4xl font-bold text-purple-600 mb-2">
                {stats.accuracy.byMarket[PredictionMarket.OVER_UNDER_25]}%
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Over/Under 2.5</h3>
              <p className="text-sm text-gray-600">Goal market predictions</p>
            </div>

            <div className="card text-center">
              <div className="text-4xl font-bold text-purple-600 mb-2">
                {stats.accuracy.byMarket[PredictionMarket.BOTH_TEAMS_TO_SCORE]}%
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Both Teams to Score</h3>
              <p className="text-sm text-gray-600">BTTS market accuracy</p>
            </div>

            <div className="card text-center">
              <div className="text-4xl font-bold text-purple-600 mb-2">
                {stats.accuracy.byMarket[PredictionMarket.MATCH_RESULT]}%
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Match Result</h3>
              <p className="text-sm text-gray-600">1X2 market predictions</p>
            </div>

            <div className="card text-center">
              <div className="text-4xl font-bold text-purple-600 mb-2">
                {stats.accuracy.last7Days}%
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Last 7 Days</h3>
              <p className="text-sm text-gray-600">Recent performance</p>
            </div>
          </div>
        </div>
      </section>

      {/* Call to Action */}
      <section className="bg-gradient-to-r from-purple-600 to-purple-700 text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
          <h2 className="text-3xl lg:text-4xl font-bold mb-4">
            Ready to Start Winning?
          </h2>
          <p className="text-xl mb-8 text-purple-100 max-w-2xl mx-auto">
            Join our community of successful bettors and start making informed decisions with our expert predictions.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/register"
              className="btn bg-green-500 hover:bg-green-600 text-white font-semibold px-8 py-4 text-lg"
            >
              Get Started Free
            </Link>
            <Link
              to="/predictions/today"
              className="btn bg-white bg-opacity-20 backdrop-blur-sm hover:bg-opacity-30 text-white font-semibold px-8 py-4 text-lg border border-white border-opacity-30"
            >
              View Predictions
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default HomePage;