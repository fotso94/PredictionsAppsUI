import React from 'react';
import { mockDashboardStats } from '../data/mockData';

const DashboardPage: React.FC = () => {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Dashboard</h1>
        <p className="text-gray-600">Track your betting performance and statistics</p>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="card text-center">
          <div className="text-3xl font-bold text-purple-600 mb-2">{mockDashboardStats.totalPredictions}</div>
          <h3 className="font-semibold text-gray-900">Total Predictions</h3>
        </div>
        <div className="card text-center">
          <div className="text-3xl font-bold text-green-600 mb-2">{mockDashboardStats.correctPredictions}</div>
          <h3 className="font-semibold text-gray-900">Correct Predictions</h3>
        </div>
        <div className="card text-center">
          <div className="text-3xl font-bold text-blue-600 mb-2">${mockDashboardStats.profit}</div>
          <h3 className="font-semibold text-gray-900">Total Profit</h3>
        </div>
        <div className="card text-center">
          <div className="text-3xl font-bold text-indigo-600 mb-2">{mockDashboardStats.roi}%</div>
          <h3 className="font-semibold text-gray-900">ROI</h3>
        </div>
      </div>

      <div className="text-center py-12">
        <p className="text-gray-600">User dashboard features coming soon...</p>
      </div>
    </div>
  );
};

export default DashboardPage;