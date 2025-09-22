import React from 'react';
import { useParams } from 'react-router-dom';

const MatchDetailPage: React.FC = () => {
  const { matchId } = useParams();

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="text-center py-12">
        <h1 className="text-3xl font-bold text-gray-900 mb-4">Match Analysis</h1>
        <p className="text-gray-600 mb-8">Match ID: {matchId}</p>
        <p className="text-gray-600">Detailed match analysis coming soon...</p>
      </div>
    </div>
  );
};

export default MatchDetailPage;