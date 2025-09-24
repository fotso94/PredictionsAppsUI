import React from 'react';
import { Link } from 'react-router-dom';
import { 
  TrophyIcon, 
  ChartBarIcon, 
  UserGroupIcon,
  ArrowRightIcon 
} from '@heroicons/react/24/outline';
import Button from '../ui/Button';
import Container from '../layout/Container';

const HeroSection: React.FC = () => {
  const stats = [
    {
      icon: TrophyIcon,
      value: '68.5%',
      label: 'Win Rate',
      description: 'Average accuracy across all predictions',
    },
    {
      icon: ChartBarIcon,
      value: '15K+',
      label: 'Predictions',
      description: 'Total predictions made this season',
    },
    {
      icon: UserGroupIcon,
      value: '12K+',
      label: 'Active Users',
      description: 'Trusted by thousands of bettors',
    },
  ];

  return (
    <section className="relative bg-gradient-to-br from-dark-900 via-dark-800 to-dark-900 overflow-hidden">
      {/* Background Pattern */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute inset-0 bg-[url('/images/soccer-pattern.svg')] bg-repeat opacity-20"></div>
        <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-r from-primary-600/20 to-success-600/20"></div>
      </div>

      {/* Floating Elements */}
      <div className="absolute top-20 left-10 w-20 h-20 bg-primary-600/20 rounded-full blur-xl animate-pulse-slow"></div>
      <div className="absolute bottom-20 right-10 w-32 h-32 bg-success-600/20 rounded-full blur-xl animate-pulse-slow delay-1000"></div>
      <div className="absolute top-1/2 left-1/4 w-16 h-16 bg-yellow-600/20 rounded-full blur-xl animate-pulse-slow delay-500"></div>

      <Container className="relative z-10 py-20 lg:py-32">
        <div className="text-center">
          {/* Main Heading */}
          <div className="mb-8">
            <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold mb-6">
              <span className="gradient-text">Expert Soccer</span>
              <br />
              <span className="text-white">Predictions</span>
            </h1>
            <p className="text-xl md:text-2xl text-dark-300 max-w-3xl mx-auto leading-relaxed">
              Join thousands of successful bettors with our AI-powered predictions, 
              expert analysis, and proven track record of winning picks.
            </p>
          </div>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center mb-16">
            <Link to="/predictions/today">
              <Button
                variant="primary"
                size="lg"
                icon={<TrophyIcon className="w-6 h-6" />}
                className="text-lg px-8 py-4"
              >
                View Today's Predictions
              </Button>
            </Link>
            <Link to="/about">
              <Button
                variant="outline"
                size="lg"
                icon={<ArrowRightIcon className="w-6 h-6" />}
                iconPosition="right"
                className="text-lg px-8 py-4"
              >
                Learn More
              </Button>
            </Link>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-4xl mx-auto">
            {stats.map((stat, index) => {
              const Icon = stat.icon;
              return (
                <div
                  key={index}
                  className="bg-dark-800/50 backdrop-blur-sm border border-dark-700/50 rounded-xl p-6 hover:bg-dark-800/70 transition-all duration-300 group"
                >
                  <div className="flex flex-col items-center text-center">
                    <div className="w-12 h-12 bg-gradient-to-r from-primary-600 to-success-600 rounded-lg flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                      <Icon className="w-6 h-6 text-white" />
                    </div>
                    <div className="text-3xl font-bold text-white mb-2">
                      {stat.value}
                    </div>
                    <div className="text-lg font-semibold text-primary-400 mb-2">
                      {stat.label}
                    </div>
                    <div className="text-sm text-dark-400">
                      {stat.description}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Trust Indicators */}
          <div className="mt-16 pt-8 border-t border-dark-700/50">
            <p className="text-dark-400 text-sm mb-4">Trusted by leading betting platforms</p>
            <div className="flex flex-wrap justify-center items-center gap-8 opacity-60">
              {/* Placeholder for partner logos */}
              <div className="h-8 w-24 bg-dark-700 rounded"></div>
              <div className="h-8 w-32 bg-dark-700 rounded"></div>
              <div className="h-8 w-28 bg-dark-700 rounded"></div>
              <div className="h-8 w-36 bg-dark-700 rounded"></div>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
};

export default HeroSection;
