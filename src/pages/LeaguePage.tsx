import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { TrophyIcon, CalendarDaysIcon, ChartBarIcon } from '@heroicons/react/24/outline';
import Container from '../components/layout/Container';
import PredictionCard from '../components/ui/PredictionCard';
import MatchCard from '../components/ui/MatchCard';
import Tabs, { TabsList, TabsTrigger, TabsContent } from '../components/ui/Tabs';
import { LoadingOverlay } from '../components/ui/LoadingSpinner';
import { mockLeagues } from '../data/mockLeagues';
import { mockMatches } from '../data/mockMatches';
import { mockPredictions } from '../data/mockPredictions';
import type { League, Match, Prediction } from '../types';

const LeaguePage: React.FC = () => {
  const { leagueId } = useParams<{ leagueId: string }>();
  const [league, setLeague] = useState<League | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('predictions');

  useEffect(() => {
    const loadLeagueData = async () => {
      setIsLoading(true);
      
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Find league by ID
      const foundLeague = mockLeagues.find(l => l.id === leagueId);
      if (foundLeague) {
        setLeague(foundLeague);
        
        // Filter matches and predictions for this league
        const leagueMatches = mockMatches.filter(m => m.league.id === leagueId);
        const leaguePredictions = mockPredictions.filter(p => p.match.league.id === leagueId);
        
        setMatches(leagueMatches);
        setPredictions(leaguePredictions);
      }
      
      setIsLoading(false);
    };

    if (leagueId) {
      loadLeagueData();
    }
  }, [leagueId]);

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

  if (!league) {
    return (
      <div className="min-h-screen bg-dark-900 py-8">
        <Container>
          <div className="text-center py-12">
            <div className="text-6xl mb-4">🏆</div>
            <h2 className="text-2xl font-bold text-white mb-2">League Not Found</h2>
            <p className="text-dark-400">The league you're looking for doesn't exist.</p>
          </div>
        </Container>
      </div>
    );
  }

  // Mock league table data
  const leagueTable = [
    { position: 1, team: 'Manchester City', played: 15, won: 12, drawn: 2, lost: 1, gf: 35, ga: 8, gd: 27, points: 38 },
    { position: 2, team: 'Arsenal', played: 15, won: 11, drawn: 3, lost: 1, gf: 32, ga: 12, gd: 20, points: 36 },
    { position: 3, team: 'Liverpool', played: 15, won: 10, drawn: 4, lost: 1, gf: 30, ga: 15, gd: 15, points: 34 },
    { position: 4, team: 'Chelsea', played: 15, won: 9, drawn: 3, lost: 3, gf: 28, ga: 18, gd: 10, points: 30 },
    { position: 5, team: 'Manchester United', played: 15, won: 8, drawn: 4, lost: 3, gf: 25, ga: 20, gd: 5, points: 28 },
  ];

  return (
    <>
      <Helmet>
        <title>{league.name} - Predictions & Analysis - PredictionsApp</title>
        <meta name="description" content={`Expert predictions and analysis for ${league.name}. View fixtures, league table, and betting tips.`} />
        <meta name="keywords" content={`${league.name}, soccer predictions, football betting, league table`} />
      </Helmet>

      <div className="min-h-screen bg-dark-900 py-8">
        <Container>
          {/* League Header */}
          <div className="bg-dark-800 border border-dark-700 rounded-lg p-6 mb-8">
            <div className="flex items-center space-x-4 mb-4">
              <img 
                src={league.logo} 
                alt={league.name}
                className="w-16 h-16"
                onError={(e) => {
                  e.currentTarget.src = '/images/placeholder-league.png';
                }}
              />
              <div>
                <h1 className="text-3xl md:text-4xl font-bold text-white mb-2">{league.name}</h1>
                <p className="text-lg text-dark-300">{league.country} • Season 2024/25</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center">
                <div className="text-2xl font-bold text-primary-400 mb-1">{predictions.length}</div>
                <div className="text-sm text-dark-400">Active Predictions</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-success-400 mb-1">{matches.length}</div>
                <div className="text-sm text-dark-400">Upcoming Matches</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-warning-400 mb-1">20</div>
                <div className="text-sm text-dark-400">Teams</div>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className="mb-6">
            <Tabs value={activeTab} onChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="predictions">
                  <TrophyIcon className="w-4 h-4 mr-2" />
                  Predictions
                </TabsTrigger>
                <TabsTrigger value="fixtures">
                  <CalendarDaysIcon className="w-4 h-4 mr-2" />
                  Fixtures
                </TabsTrigger>
                <TabsTrigger value="table">
                  <ChartBarIcon className="w-4 h-4 mr-2" />
                  League Table
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Tab Content */}
          <Tabs value={activeTab} onChange={setActiveTab}>
            {/* Predictions Tab */}
            <TabsContent value="predictions">
              {predictions.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {predictions.map((prediction) => (
                    <PredictionCard
                      key={prediction.id}
                      prediction={prediction}
                      onViewDetails={() => {
                        // Navigate to prediction details
                      }}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <div className="text-6xl mb-4">🎯</div>
                  <h3 className="text-xl font-semibold text-white mb-2">No Predictions Available</h3>
                  <p className="text-dark-400">
                    Predictions for {league.name} matches will appear here when available.
                  </p>
                </div>
              )}
            </TabsContent>

            {/* Fixtures Tab */}
            <TabsContent value="fixtures">
              {matches.length > 0 ? (
                <div className="space-y-4">
                  {matches.map((match) => (
                    <MatchCard
                      key={match.id}
                      match={match}
                      onViewDetails={() => {
                        // Navigate to match details
                      }}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <div className="text-6xl mb-4">📅</div>
                  <h3 className="text-xl font-semibold text-white mb-2">No Fixtures Available</h3>
                  <p className="text-dark-400">
                    Upcoming fixtures for {league.name} will appear here.
                  </p>
                </div>
              )}
            </TabsContent>

            {/* League Table Tab */}
            <TabsContent value="table">
              <div className="bg-dark-800 border border-dark-700 rounded-lg overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-dark-700">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-dark-300 uppercase tracking-wider">Pos</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-dark-300 uppercase tracking-wider">Team</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-dark-300 uppercase tracking-wider">P</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-dark-300 uppercase tracking-wider">W</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-dark-300 uppercase tracking-wider">D</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-dark-300 uppercase tracking-wider">L</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-dark-300 uppercase tracking-wider">GF</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-dark-300 uppercase tracking-wider">GA</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-dark-300 uppercase tracking-wider">GD</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-dark-300 uppercase tracking-wider">Pts</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-dark-700">
                      {leagueTable.map((team, index) => (
                        <tr key={index} className="hover:bg-dark-700/50 transition-colors duration-200">
                          <td className="px-4 py-3 text-sm font-medium text-white">{team.position}</td>
                          <td className="px-4 py-3 text-sm text-white">{team.team}</td>
                          <td className="px-4 py-3 text-sm text-center text-dark-300">{team.played}</td>
                          <td className="px-4 py-3 text-sm text-center text-success-400">{team.won}</td>
                          <td className="px-4 py-3 text-sm text-center text-warning-400">{team.drawn}</td>
                          <td className="px-4 py-3 text-sm text-center text-danger-400">{team.lost}</td>
                          <td className="px-4 py-3 text-sm text-center text-dark-300">{team.gf}</td>
                          <td className="px-4 py-3 text-sm text-center text-dark-300">{team.ga}</td>
                          <td className="px-4 py-3 text-sm text-center text-dark-300">
                            <span className={team.gd >= 0 ? 'text-success-400' : 'text-danger-400'}>
                              {team.gd > 0 ? '+' : ''}{team.gd}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-center font-bold text-white">{team.points}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </Container>
      </div>
    </>
  );
};

export default LeaguePage;
