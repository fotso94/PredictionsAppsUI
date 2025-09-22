import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { ArrowLeftIcon, ChartBarIcon, ClockIcon, TrophyIcon } from '@heroicons/react/24/outline';
import Container from '../components/layout/Container';
import MatchHeader from '../components/match/MatchHeader';
import TeamStats from '../components/match/TeamStats';
import PredictionCard from '../components/ui/PredictionCard';
import Button from '../components/ui/Button';
import Tabs, { TabsList, TabsTrigger, TabsContent } from '../components/ui/Tabs';
import { LoadingOverlay } from '../components/ui/LoadingSpinner';
import { mockMatches } from '../data/mockMatches';
import { mockPredictions } from '../data/mockPredictions';
import type { Match, Prediction } from '../types';

const MatchDetailsPage: React.FC = () => {
  const { matchId } = useParams<{ matchId: string }>();
  const [match, setMatch] = useState<Match | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    const loadMatchData = async () => {
      setIsLoading(true);
      
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Find match by ID
      const foundMatch = mockMatches.find(m => m.id === matchId);
      if (foundMatch) {
        setMatch(foundMatch);
        
        // Find predictions for this match
        const matchPredictions = mockPredictions.filter(p => p.match.id === matchId);
        setPredictions(matchPredictions);
      }
      
      setIsLoading(false);
    };

    if (matchId) {
      loadMatchData();
    }
  }, [matchId]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-dark-900 py-8">
        <Container>
          <LoadingOverlay isLoading={true}>
            <div className="h-96" />
          </LoadingOverlay>
        </Container>
      </div>
    );
  }

  if (!match) {
    return (
      <div className="min-h-screen bg-dark-900 py-8">
        <Container>
          <div className="text-center py-12">
            <div className="text-6xl mb-4">⚽</div>
            <h2 className="text-2xl font-bold text-white mb-2">Match Not Found</h2>
            <p className="text-dark-400 mb-6">
              The match you're looking for doesn't exist or has been removed.
            </p>
            <Button variant="primary" onClick={() => window.history.back()}>
              Go Back
            </Button>
          </div>
        </Container>
      </div>
    );
  }

  const headToHeadData = [
    { label: 'Total Matches', home: 15, away: 12 },
    { label: 'Home Wins', home: 8, away: 4 },
    { label: 'Away Wins', home: 4, away: 8 },
    { label: 'Draws', home: 3, away: 3 },
    { label: 'Goals Scored', home: 24, away: 18 },
    { label: 'Avg Goals/Game', home: 1.6, away: 1.2 },
  ];

  const recentForm = {
    home: ['W', 'W', 'D', 'L', 'W'], // Last 5 matches
    away: ['L', 'W', 'W', 'D', 'W'],
  };

  const getFormColor = (result: string) => {
    switch (result) {
      case 'W': return 'bg-success-500';
      case 'D': return 'bg-yellow-500';
      case 'L': return 'bg-danger-500';
      default: return 'bg-dark-600';
    }
  };

  return (
    <>
      <Helmet>
        <title>{match.homeTeam.name} vs {match.awayTeam.name} - Match Analysis - PredictionsApp</title>
        <meta 
          name="description" 
          content={`Detailed analysis and predictions for ${match.homeTeam.name} vs ${match.awayTeam.name} in ${match.league.name}. Expert insights, team statistics, and betting tips.`} 
        />
        <meta name="keywords" content={`${match.homeTeam.name}, ${match.awayTeam.name}, ${match.league.name}, match prediction, soccer analysis`} />
      </Helmet>

      <div className="min-h-screen bg-dark-900 py-8">
        <Container>
          {/* Back Button */}
          <div className="mb-6">
            <Button
              variant="ghost"
              onClick={() => window.history.back()}
              icon={<ArrowLeftIcon className="w-4 h-4" />}
            >
              Back to Predictions
            </Button>
          </div>

          {/* Match Header */}
          <MatchHeader match={match} />

          {/* Tabs */}
          <div className="mb-6">
            <Tabs value={activeTab} onChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="overview">
                  <ChartBarIcon className="w-4 h-4 mr-2" />
                  Overview
                </TabsTrigger>
                <TabsTrigger value="predictions">
                  <TrophyIcon className="w-4 h-4 mr-2" />
                  Predictions
                </TabsTrigger>
                <TabsTrigger value="h2h">
                  <ClockIcon className="w-4 h-4 mr-2" />
                  Head to Head
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Tab Content */}
          <Tabs value={activeTab} onChange={setActiveTab}>
            {/* Overview Tab */}
            <TabsContent value="overview">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Team Statistics */}
                <TeamStats homeTeam={match.homeTeam} awayTeam={match.awayTeam} />

                {/* Recent Form */}
                <div className="bg-dark-800 border border-dark-700 rounded-lg p-6">
                  <h3 className="text-xl font-bold text-white mb-6 text-center">Recent Form</h3>
                  
                  <div className="space-y-6">
                    {/* Home Team Form */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <img 
                          src={match.homeTeam.logo} 
                          alt={match.homeTeam.name}
                          className="w-8 h-8"
                        />
                        <span className="font-medium text-white">{match.homeTeam.shortName}</span>
                      </div>
                      <div className="flex space-x-1">
                        {recentForm.home.map((result, index) => (
                          <div
                            key={index}
                            className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold ${getFormColor(result)}`}
                          >
                            {result}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Away Team Form */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <img 
                          src={match.awayTeam.logo} 
                          alt={match.awayTeam.name}
                          className="w-8 h-8"
                        />
                        <span className="font-medium text-white">{match.awayTeam.shortName}</span>
                      </div>
                      <div className="flex space-x-1">
                        {recentForm.away.map((result, index) => (
                          <div
                            key={index}
                            className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold ${getFormColor(result)}`}
                          >
                            {result}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="mt-6 pt-4 border-t border-dark-700 text-center">
                    <p className="text-sm text-dark-400">
                      Last 5 matches: <span className="text-success-400">W</span>in, 
                      <span className="text-yellow-400"> D</span>raw, 
                      <span className="text-danger-400"> L</span>oss
                    </p>
                  </div>
                </div>
              </div>

              {/* Key Stats */}
              <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-dark-800 border border-dark-700 rounded-lg p-6 text-center">
                  <div className="text-3xl font-bold text-primary-400 mb-2">
                    {((match.homeTeam.wins || 0) / (match.homeTeam.matchesPlayed || 1) * 100).toFixed(1)}%
                  </div>
                  <div className="text-sm text-dark-300">Home Win Rate</div>
                </div>

                <div className="bg-dark-800 border border-dark-700 rounded-lg p-6 text-center">
                  <div className="text-3xl font-bold text-success-400 mb-2">
                    {(((match.homeTeam.goalsFor || 0) + (match.awayTeam.goalsFor || 0)) / 
                      ((match.homeTeam.matchesPlayed || 1) + (match.awayTeam.matchesPlayed || 1)) * 2).toFixed(1)}
                  </div>
                  <div className="text-sm text-dark-300">Expected Goals</div>
                </div>

                <div className="bg-dark-800 border border-dark-700 rounded-lg p-6 text-center">
                  <div className="text-3xl font-bold text-warning-400 mb-2">
                    {((match.awayTeam.wins || 0) / (match.awayTeam.matchesPlayed || 1) * 100).toFixed(1)}%
                  </div>
                  <div className="text-sm text-dark-300">Away Win Rate</div>
                </div>
              </div>
            </TabsContent>

            {/* Predictions Tab */}
            <TabsContent value="predictions">
              {predictions.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {predictions.map((prediction) => (
                    <PredictionCard
                      key={prediction.id}
                      prediction={prediction}
                      onViewDetails={() => {
                        // Handle prediction details
                      }}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <div className="text-6xl mb-4">🎯</div>
                  <h3 className="text-xl font-semibold text-white mb-2">No Predictions Available</h3>
                  <p className="text-dark-400">
                    Predictions for this match are not available yet. Check back later!
                  </p>
                </div>
              )}
            </TabsContent>

            {/* Head to Head Tab */}
            <TabsContent value="h2h">
              <div className="bg-dark-800 border border-dark-700 rounded-lg p-6">
                <h3 className="text-xl font-bold text-white mb-6 text-center">Head to Head Statistics</h3>
                
                <div className="space-y-4">
                  {headToHeadData.map((stat, index) => (
                    <div key={index} className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="text-sm font-medium text-white">
                          {typeof stat.home === 'number' ? stat.home.toFixed(stat.label.includes('Avg') ? 1 : 0) : stat.home}
                        </div>
                        <div className="text-sm font-medium text-dark-300 text-center flex-1 px-4">
                          {stat.label}
                        </div>
                        <div className="text-sm font-medium text-white">
                          {typeof stat.away === 'number' ? stat.away.toFixed(stat.label.includes('Avg') ? 1 : 0) : stat.away}
                        </div>
                      </div>
                      
                      {typeof stat.home === 'number' && typeof stat.away === 'number' && (
                        <div className="flex items-center space-x-2">
                          <div className="flex-1 h-2 bg-dark-700 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-primary-500 transition-all duration-300"
                              style={{ width: `${(stat.home / (stat.home + stat.away)) * 100}%` }}
                            />
                          </div>
                          <div className="w-px h-4 bg-dark-600" />
                          <div className="flex-1 h-2 bg-dark-700 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-success-500 transition-all duration-300 ml-auto"
                              style={{ width: `${(stat.away / (stat.home + stat.away)) * 100}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div className="flex items-center justify-between mt-6 pt-4 border-t border-dark-700">
                  <div className="flex items-center space-x-2">
                    <img 
                      src={match.homeTeam.logo} 
                      alt={match.homeTeam.name}
                      className="w-6 h-6"
                    />
                    <span className="text-sm font-medium text-white">{match.homeTeam.shortName}</span>
                  </div>
                  
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-medium text-white">{match.awayTeam.shortName}</span>
                    <img 
                      src={match.awayTeam.logo} 
                      alt={match.awayTeam.name}
                      className="w-6 h-6"
                    />
                  </div>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </Container>
      </div>
    </>
  );
};

export default MatchDetailsPage;
