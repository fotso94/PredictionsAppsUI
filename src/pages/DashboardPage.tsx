import React, { useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { 
  ChartBarIcon, 
  TrophyIcon, 
  CurrencyDollarIcon, 
  CalendarDaysIcon,
  StarIcon,
  ClockIcon
} from '@heroicons/react/24/outline';
import Container from '../components/layout/Container';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import PredictionCard from '../components/ui/PredictionCard';
import Tabs, { TabsList, TabsTrigger, TabsContent } from '../components/ui/Tabs';
import { mockPredictions } from '../data/mockPredictions';
import { mockUsers } from '../data/mockUsers';

const DashboardPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const currentUser = mockUsers[0]; // Mock current user
  
  // Mock user's predictions (filtered from mock data)
  const userPredictions = mockPredictions.slice(0, 6);
  const favoritePredictions = mockPredictions.filter(p => p.confidence >= 80).slice(0, 4);

  // Calculate user stats
  const totalPredictions = 45;
  const wonPredictions = 31;
  const winRate = (wonPredictions / totalPredictions * 100).toFixed(1);
  const totalProfit = 1250.75;
  const roi = 18.5;

  const recentActivity = [
    { id: 1, type: 'prediction', description: 'Followed Manchester United vs Chelsea prediction', time: '2 hours ago' },
    { id: 2, type: 'win', description: 'Won Liverpool vs Arsenal prediction (+$45)', time: '1 day ago' },
    { id: 3, type: 'favorite', description: 'Added Real Madrid to favorites', time: '2 days ago' },
    { id: 4, type: 'prediction', description: 'Followed Barcelona vs PSG prediction', time: '3 days ago' },
  ];

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'prediction': return <ClockIcon className="w-4 h-4 text-primary-400" />;
      case 'win': return <TrophyIcon className="w-4 h-4 text-success-400" />;
      case 'favorite': return <StarIcon className="w-4 h-4 text-warning-400" />;
      default: return <CalendarDaysIcon className="w-4 h-4 text-dark-400" />;
    }
  };

  return (
    <>
      <Helmet>
        <title>Dashboard - PredictionsApp</title>
        <meta name="description" content="Your personal dashboard with betting statistics, favorite predictions, and performance tracking." />
        <meta name="robots" content="noindex, nofollow" />
      </Helmet>

      <div className="min-h-screen bg-dark-900 py-8">
        <Container>
          {/* Welcome Header */}
          <div className="mb-8">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl md:text-4xl font-bold text-white mb-2">
                  Welcome back, <span className="gradient-text">{currentUser.firstName}</span>
                </h1>
                <p className="text-lg text-dark-300">
                  Track your predictions, analyze your performance, and discover new opportunities.
                </p>
              </div>
              <div className="hidden md:block">
                <div className="flex items-center space-x-2 bg-dark-800 border border-dark-700 rounded-lg px-4 py-2">
                  <div className="w-10 h-10 bg-gradient-to-r from-primary-600 to-success-600 rounded-full flex items-center justify-center">
                    <span className="text-white font-bold">{currentUser.firstName[0]}</span>
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white">{currentUser.firstName} {currentUser.lastName}</div>
                    <div className="text-xs text-dark-400">Premium Member</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <Card className="bg-dark-800 border-dark-700">
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 bg-primary-600/20 rounded-lg flex items-center justify-center">
                  <TrophyIcon className="w-6 h-6 text-primary-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-white">{winRate}%</div>
                  <div className="text-sm text-dark-400">Win Rate</div>
                  <div className="text-xs text-success-400">↗ +2.3%</div>
                </div>
              </div>
            </Card>

            <Card className="bg-dark-800 border-dark-700">
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 bg-success-600/20 rounded-lg flex items-center justify-center">
                  <CurrencyDollarIcon className="w-6 h-6 text-success-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-white">${totalProfit}</div>
                  <div className="text-sm text-dark-400">Total Profit</div>
                  <div className="text-xs text-success-400">↗ +$125</div>
                </div>
              </div>
            </Card>

            <Card className="bg-dark-800 border-dark-700">
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 bg-warning-600/20 rounded-lg flex items-center justify-center">
                  <ChartBarIcon className="w-6 h-6 text-warning-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-white">{roi}%</div>
                  <div className="text-sm text-dark-400">ROI</div>
                  <div className="text-xs text-success-400">↗ +1.2%</div>
                </div>
              </div>
            </Card>

            <Card className="bg-dark-800 border-dark-700">
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 bg-info-600/20 rounded-lg flex items-center justify-center">
                  <CalendarDaysIcon className="w-6 h-6 text-info-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-white">{totalPredictions}</div>
                  <div className="text-sm text-dark-400">Total Bets</div>
                  <div className="text-xs text-primary-400">+3 this week</div>
                </div>
              </div>
            </Card>
          </div>

          {/* Tabs */}
          <div className="mb-6">
            <Tabs value={activeTab} onChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="predictions">My Predictions</TabsTrigger>
                <TabsTrigger value="favorites">Favorites</TabsTrigger>
                <TabsTrigger value="activity">Activity</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Tab Content */}
          <Tabs value={activeTab} onChange={setActiveTab}>
            {/* Overview Tab */}
            <TabsContent value="overview">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Performance Chart Placeholder */}
                <div className="lg:col-span-2">
                  <Card className="bg-dark-800 border-dark-700 h-80">
                    <Card.Header>
                      <h3 className="text-lg font-semibold text-white">Performance Overview</h3>
                    </Card.Header>
                    <Card.Content>
                      <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                          <ChartBarIcon className="w-16 h-16 text-dark-600 mx-auto mb-4" />
                          <p className="text-dark-400">Performance chart will be displayed here</p>
                          <p className="text-sm text-dark-500 mt-2">Chart.js integration ready</p>
                        </div>
                      </div>
                    </Card.Content>
                  </Card>
                </div>

                {/* Recent Activity */}
                <div>
                  <Card className="bg-dark-800 border-dark-700">
                    <Card.Header>
                      <h3 className="text-lg font-semibold text-white">Recent Activity</h3>
                    </Card.Header>
                    <Card.Content>
                      <div className="space-y-4">
                        {recentActivity.map((activity) => (
                          <div key={activity.id} className="flex items-start space-x-3">
                            <div className="flex-shrink-0 mt-1">
                              {getActivityIcon(activity.type)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-white">{activity.description}</p>
                              <p className="text-xs text-dark-400 mt-1">{activity.time}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </Card.Content>
                    <Card.Footer>
                      <Button variant="ghost" size="sm" fullWidth>
                        View All Activity
                      </Button>
                    </Card.Footer>
                  </Card>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="mt-6">
                <Card className="bg-dark-800 border-dark-700">
                  <Card.Header>
                    <h3 className="text-lg font-semibold text-white">Quick Actions</h3>
                  </Card.Header>
                  <Card.Content>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <Button variant="primary" fullWidth>
                        View Today's Predictions
                      </Button>
                      <Button variant="outline" fullWidth>
                        Browse Leagues
                      </Button>
                      <Button variant="outline" fullWidth>
                        Account Settings
                      </Button>
                    </div>
                  </Card.Content>
                </Card>
              </div>
            </TabsContent>

            {/* My Predictions Tab */}
            <TabsContent value="predictions">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {userPredictions.map((prediction) => (
                  <PredictionCard
                    key={prediction.id}
                    prediction={prediction}
                    onViewDetails={() => {
                      // Navigate to prediction details
                    }}
                  />
                ))}
              </div>
              
              <div className="text-center mt-8">
                <Button variant="outline" size="lg">
                  Load More Predictions
                </Button>
              </div>
            </TabsContent>

            {/* Favorites Tab */}
            <TabsContent value="favorites">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {favoritePredictions.map((prediction) => (
                  <PredictionCard
                    key={prediction.id}
                    prediction={prediction}
                    onViewDetails={() => {
                      // Navigate to prediction details
                    }}
                  />
                ))}
              </div>
              
              {favoritePredictions.length === 0 && (
                <div className="text-center py-12">
                  <StarIcon className="w-16 h-16 text-dark-600 mx-auto mb-4" />
                  <h3 className="text-xl font-semibold text-white mb-2">No Favorites Yet</h3>
                  <p className="text-dark-400 mb-6">
                    Start adding predictions to your favorites to track them easily.
                  </p>
                  <Button variant="primary">
                    Browse Predictions
                  </Button>
                </div>
              )}
            </TabsContent>

            {/* Activity Tab */}
            <TabsContent value="activity">
              <Card className="bg-dark-800 border-dark-700">
                <Card.Header>
                  <h3 className="text-lg font-semibold text-white">Activity History</h3>
                </Card.Header>
                <Card.Content>
                  <div className="space-y-6">
                    {recentActivity.concat([
                      { id: 5, type: 'win', description: 'Won Bayern Munich vs Dortmund prediction (+$75)', time: '4 days ago' },
                      { id: 6, type: 'prediction', description: 'Followed Juventus vs AC Milan prediction', time: '5 days ago' },
                      { id: 7, type: 'favorite', description: 'Added Premier League to favorites', time: '1 week ago' },
                    ]).map((activity) => (
                      <div key={activity.id} className="flex items-start space-x-4 pb-4 border-b border-dark-700 last:border-b-0">
                        <div className="flex-shrink-0 mt-1">
                          {getActivityIcon(activity.type)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-white">{activity.description}</p>
                          <p className="text-xs text-dark-400 mt-1">{activity.time}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card.Content>
              </Card>
            </TabsContent>
          </Tabs>
        </Container>
      </div>
    </>
  );
};

export default DashboardPage;
