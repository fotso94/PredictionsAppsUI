import React from 'react';
import { 
  ChartBarIcon, 
  ClockIcon, 
  ShieldCheckIcon,
  BoltIcon,
  TrophyIcon,
  UserGroupIcon 
} from '@heroicons/react/24/outline';
import Container, { Section } from '../layout/Container';
import Card from '../ui/Card';

const FeaturesSection: React.FC = () => {
  const features = [
    {
      icon: ChartBarIcon,
      title: 'Advanced Analytics',
      description: 'AI-powered analysis of team performance, player statistics, and historical data to generate accurate predictions.',
      color: 'from-blue-600 to-blue-400',
    },
    {
      icon: ClockIcon,
      title: 'Real-Time Updates',
      description: 'Get instant notifications about lineup changes, weather conditions, and other factors that affect match outcomes.',
      color: 'from-green-600 to-green-400',
    },
    {
      icon: ShieldCheckIcon,
      title: 'Verified Results',
      description: 'All predictions are tracked and verified. We maintain complete transparency with our win rates and performance.',
      color: 'from-purple-600 to-purple-400',
    },
    {
      icon: BoltIcon,
      title: 'Lightning Fast',
      description: 'Access predictions instantly with our optimized platform. No delays when you need information quickly.',
      color: 'from-yellow-600 to-yellow-400',
    },
    {
      icon: TrophyIcon,
      title: 'Expert Insights',
      description: 'Detailed analysis from professional tipsters with years of experience in sports betting and analytics.',
      color: 'from-red-600 to-red-400',
    },
    {
      icon: UserGroupIcon,
      title: 'Community Driven',
      description: 'Join a community of successful bettors. Share insights, discuss strategies, and learn from each other.',
      color: 'from-indigo-600 to-indigo-400',
    },
  ];

  return (
    <Section padding="lg">
      <Container>
        {/* Section Header */}
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Why Choose <span className="gradient-text">PredictionsApp</span>
          </h2>
          <p className="text-lg text-dark-300 max-w-2xl mx-auto">
            Discover the features that make us the preferred choice for serious bettors 
            and prediction enthusiasts worldwide.
          </p>
        </div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <Card
                key={index}
                className="group hover:shadow-xl transition-all duration-300 hover:-translate-y-1"
                hover
              >
                <div className="flex flex-col h-full">
                  {/* Icon */}
                  <div className="mb-4">
                    <div className={`w-12 h-12 bg-gradient-to-r ${feature.color} rounded-lg flex items-center justify-center group-hover:scale-110 transition-transform duration-300`}>
                      <Icon className="w-6 h-6 text-white" />
                    </div>
                  </div>

                  {/* Content */}
                  <div className="flex-1">
                    <h3 className="text-xl font-semibold text-white mb-3 group-hover:text-primary-400 transition-colors duration-300">
                      {feature.title}
                    </h3>
                    <p className="text-dark-300 leading-relaxed">
                      {feature.description}
                    </p>
                  </div>

                  {/* Hover Effect */}
                  <div className="mt-4 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                    <div className="h-1 bg-gradient-to-r from-primary-600 to-success-600 rounded-full"></div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>

        {/* Bottom CTA */}
        <div className="mt-16 text-center">
          <div className="bg-gradient-to-r from-primary-600/10 to-success-600/10 border border-primary-600/20 rounded-xl p-8 max-w-4xl mx-auto">
            <h3 className="text-2xl font-bold text-white mb-4">
              Ready to Start Winning?
            </h3>
            <p className="text-dark-300 mb-6 max-w-2xl mx-auto">
              Join thousands of successful bettors who trust our predictions. 
              Start your winning streak today with our expert analysis and proven strategies.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button className="px-8 py-3 bg-primary-600 hover:bg-primary-700 text-white font-semibold rounded-lg transition-colors duration-200">
                Get Started Free
              </button>
              <button className="px-8 py-3 border border-primary-600 text-primary-400 hover:bg-primary-600/10 font-semibold rounded-lg transition-colors duration-200">
                View Pricing
              </button>
            </div>
          </div>
        </div>
      </Container>
    </Section>
  );
};

export default FeaturesSection;
