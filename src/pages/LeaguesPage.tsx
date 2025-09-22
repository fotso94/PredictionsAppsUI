import React from 'react';
import { Link } from 'react-router-dom';
import { mockLeagues } from '../data/mockData';

const LeaguesPage: React.FC = () => {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">All Leagues</h1>
        <p className="text-gray-600">
          Explore predictions across 300+ football leagues worldwide
        </p>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        {mockLeagues.map((league) => (
          <Link
            key={league.id}
            to={`/leagues/${league.name.toLowerCase().replace(/\s+/g, '-')}`}
            className="card hover:shadow-lg transition-shadow duration-200"
          >
            <div className="flex items-center space-x-4">
              <img
                src={league.logo}
                alt={league.name}
                className="w-12 h-12"
                onError={(e) => {
                  e.currentTarget.src = '/placeholder-league.png';
                }}
              />
              <div>
                <h3 className="font-semibold text-gray-900">{league.name}</h3>
                <p className="text-sm text-gray-500">{league.country}</p>
                <p className="text-xs text-gray-400">Season {league.season}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
};

export default LeaguesPage;