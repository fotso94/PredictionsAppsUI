import React from 'react';
import { mockAccuracyStats } from '../data/mockData';

const StatisticsPage: React.FC = () => {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Performance Statistics</h1>
        <p className="text-gray-600">
          Comprehensive breakdown of our prediction accuracy across all markets and leagues
        </p>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="card text-center">
          <div className="text-3xl font-bold text-green-600 mb-2">{mockAccuracyStats.overall}%</div>
          <h3 className="font-semibold text-gray-900">Overall Accuracy</h3>
        </div>
        <div className="card text-center">
          <div className="text-3xl font-bold text-blue-600 mb-2">{mockAccuracyStats.last30Days}%</div>
          <h3 className="font-semibold text-gray-900">Last 30 Days</h3>
        </div>
        <div className="card text-center">
          <div className="text-3xl font-bold text-purple-600 mb-2">{mockAccuracyStats.last7Days}%</div>
          <h3 className="font-semibold text-gray-900">Last 7 Days</h3>
        </div>
        <div className="card text-center">
          <div className="text-3xl font-bold text-indigo-600 mb-2">↗</div>
          <h3 className="font-semibold text-gray-900">Trend: {mockAccuracyStats.trend}</h3>
        </div>
      </div>

      <div className="text-center py-12">
        <p className="text-gray-600">Detailed statistics dashboard coming soon...</p>
      </div>
    </div>
  );
};

export default StatisticsPage;