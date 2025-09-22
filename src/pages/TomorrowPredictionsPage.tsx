import React from 'react';
import TodayPredictionsPage from './TodayPredictionsPage';

const TomorrowPredictionsPage: React.FC = () => {
  // This would typically fetch tomorrow's predictions
  // For demo purposes, we'll reuse the TodayPredictionsPage component with different header
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Tomorrow's Predictions</h1>
        <p className="text-gray-600">
          Get ahead with tomorrow's expert football predictions and start planning your bets
        </p>
      </div>

      {/* Coming Soon Banner */}
      <div className="bg-gradient-to-r from-purple-500 to-purple-600 rounded-xl p-8 mb-8 text-white text-center">
        <h2 className="text-2xl font-bold mb-4">Tomorrow's Predictions Coming Soon</h2>
        <p className="text-purple-100 mb-6">
          Our expert analysts are working on tomorrow's predictions. Check back later or explore today's picks.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <a href="/predictions/today" className="btn bg-white text-purple-600 hover:bg-gray-100 font-semibold px-6 py-3">
            View Today's Predictions
          </a>
          <button className="btn bg-purple-400 hover:bg-purple-300 text-white font-semibold px-6 py-3">
            Get Notified
          </button>
        </div>
      </div>

      {/* Placeholder Content */}
      <div className="grid md:grid-cols-3 gap-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="animate-pulse">
              <div className="flex items-center space-x-2 mb-4">
                <div className="w-6 h-6 bg-gray-200 rounded"></div>
                <div className="h-4 bg-gray-200 rounded w-24"></div>
              </div>
              <div className="space-y-3">
                <div className="h-4 bg-gray-200 rounded w-full"></div>
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                <div className="h-6 bg-gray-200 rounded w-1/2"></div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TomorrowPredictionsPage;