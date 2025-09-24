import React from 'react';
import { 
  TrophyIcon, 
  ChartBarIcon, 
  CurrencyDollarIcon,
  CalendarDaysIcon,
  UserGroupIcon,
  FireIcon 
} from '@heroicons/react/24/outline';
import Container, { Section } from '../layout/Container';
import Card from '../ui/Card';

const StatisticsShowcase: React.FC = () => {
  const mainStats = [
    {
      icon: TrophyIcon,
      value: '68.5%',
      label: 'Overall Accuracy',
      description: 'Win rate across all predictions',
      trend: '+2.3%',
      trendUp: true,
    },
    {
      icon: CurrencyDollarIcon,
      value: '$15,420',
      label: 'Total Profit',
      description: 'Generated for our users',
      trend: '+$2,850',
      trendUp: true,
    },
    {
      icon: ChartBarIcon,
      value: '18.2%',
      label: 'ROI',
      description: 'Return on investment',
      trend: '+1.5%',
      trendUp: true,
    },
    {
      icon: UserGroupIcon,
      value: '12,450',
      label: 'Active Users',
      description: 'Trusted community members',
      trend: '+450',
      trendUp: true,
    },
  ];

  const additionalStats = [
    {
      label: 'Predictions This Month',
      value: '1,247',
      icon: CalendarDaysIcon,
    },
    {
      label: 'Hot Streak',
      value: '12 Days',
      icon: FireIcon,
    },
    {
      label: 'Best League',
      value: 'Premier League',
      icon: TrophyIcon,
    },
    {
      label: 'Avg. Confidence',
      value: '76.8%',
      icon: ChartBarIcon,
    },
  ];

  const recentPerformance = [
    { period: 'Last 7 Days', accuracy: 72.3, predictions: 45 },
    { period: 'Last 30 Days', accuracy: 69.8, predictions: 186 },
    { period: 'This Season', accuracy: 68.5, predictions: 1247 },
  ];

  return (
    <Section padding="lg">
      <Container>
        {/* Section Header */}
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Our <span className="gradient-text">Track Record</span>
          </h2>
          <p className="text-lg text-dark-300 max-w-2xl mx-auto">
            Transparent statistics that showcase our commitment to accuracy and profitability.
            See why thousands trust our predictions.
          </p>
        </div>

        {/* Main Statistics Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
          {mainStats.map((stat, index) => {
            const Icon = stat.icon;
            return (
              <Card
                key={index}
                className="text-center hover:shadow-xl transition-all duration-300 group"
                hover
              >
                <div className="flex flex-col items-center">
                  <div className="w-16 h-16 bg-gradient-to-r from-primary-600 to-success-600 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                    <Icon className="w-8 h-8 text-white" />
                  </div>
                  
                  <div className="text-3xl font-bold text-white mb-2">
                    {stat.value}
                  </div>
                  
                  <div className="text-lg font-semibold text-primary-400 mb-2">
                    {stat.label}
                  </div>
                  
                  <div className="text-sm text-dark-400 mb-3">
                    {stat.description}
                  </div>
                  
                  <div className={`text-sm font-medium ${
                    stat.trendUp ? 'text-success-400' : 'text-danger-400'
                  }`}>
                    {stat.trendUp ? '↗' : '↘'} {stat.trend}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>

        {/* Additional Stats and Performance */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Additional Statistics */}
          <Card>
            <h3 className="text-xl font-semibold text-white mb-6">Quick Stats</h3>
            <div className="space-y-4">
              {additionalStats.map((stat, index) => {
                const Icon = stat.icon;
                return (
                  <div key={index} className="flex items-center justify-between p-3 bg-dark-700 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <Icon className="w-5 h-5 text-primary-400" />
                      <span className="text-dark-300">{stat.label}</span>
                    </div>
                    <span className="text-white font-semibold">{stat.value}</span>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Recent Performance */}
          <Card>
            <h3 className="text-xl font-semibold text-white mb-6">Recent Performance</h3>
            <div className="space-y-4">
              {recentPerformance.map((period, index) => (
                <div key={index} className="p-4 bg-dark-700 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-white font-medium">{period.period}</span>
                    <span className="text-success-400 font-semibold">{period.accuracy}%</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-dark-400">Predictions</span>
                    <span className="text-dark-300">{period.predictions}</span>
                  </div>
                  <div className="mt-2 bg-dark-600 rounded-full h-2">
                    <div
                      className="bg-gradient-to-r from-primary-600 to-success-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${period.accuracy}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Trust Indicators */}
        <div className="mt-12 text-center">
          <div className="bg-gradient-to-r from-primary-600/10 to-success-600/10 border border-primary-600/20 rounded-xl p-8">
            <h3 className="text-2xl font-bold text-white mb-4">
              Why Choose Our Predictions?
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-center">
              <div>
                <div className="text-3xl font-bold text-primary-400 mb-2">5+</div>
                <div className="text-white font-medium mb-1">Years Experience</div>
                <div className="text-sm text-dark-400">In sports analytics</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-success-400 mb-2">24/7</div>
                <div className="text-white font-medium mb-1">Live Updates</div>
                <div className="text-sm text-dark-400">Real-time predictions</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-yellow-400 mb-2">100%</div>
                <div className="text-white font-medium mb-1">Transparent</div>
                <div className="text-sm text-dark-400">All results tracked</div>
              </div>
            </div>
          </div>
        </div>
      </Container>
    </Section>
  );
};

export default StatisticsShowcase;
