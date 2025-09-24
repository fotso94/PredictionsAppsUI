import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRightIcon, CalendarDaysIcon } from '@heroicons/react/24/outline';
import { mockMatches } from '../../data/mockMatches';
import Container, { Section } from '../layout/Container';
import MatchCard from '../ui/MatchCard';
import Button from '../ui/Button';

const TodaysMatches: React.FC = () => {
  // Get today's matches (scheduled ones)
  const todaysMatches = mockMatches
    .filter(match => match.status === 'scheduled')
    .slice(0, 6);

  return (
    <Section padding="lg" background="darker">
      <Container>
        {/* Section Header */}
        <div className="text-center mb-12">
          <div className="flex items-center justify-center space-x-2 mb-4">
            <CalendarDaysIcon className="w-8 h-8 text-primary-500" />
            <h2 className="text-3xl md:text-4xl font-bold text-white">
              Today's <span className="gradient-text">Matches</span>
            </h2>
          </div>
          <p className="text-lg text-dark-300 max-w-2xl mx-auto">
            Don't miss out on today's biggest matches. Get predictions and analysis 
            for all the key games happening today.
          </p>
        </div>

        {/* Matches Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
          {todaysMatches.map((match) => (
            <div
              key={match.id}
              className="transform hover:scale-105 transition-transform duration-300"
            >
              <MatchCard
                match={match}
                onViewPredictions={() => {
                  // Navigate to match predictions
                }}
                onViewDetails={() => {
                  // Navigate to match details
                }}
                showPredictions={true}
              />
            </div>
          ))}
        </div>

        {/* View All Button */}
        <div className="text-center">
          <Link to="/matches/today">
            <Button
              variant="primary"
              size="lg"
              icon={<ArrowRightIcon className="w-5 h-5" />}
              iconPosition="right"
            >
              View All Today's Matches
            </Button>
          </Link>
        </div>

        {/* Quick Stats */}
        <div className="mt-12 grid grid-cols-2 md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="text-2xl font-bold text-primary-400 mb-1">
              {todaysMatches.length}
            </div>
            <div className="text-sm text-dark-400">Matches Today</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-success-400 mb-1">
              {todaysMatches.filter(m => m.league.name.includes('Premier')).length}
            </div>
            <div className="text-sm text-dark-400">Premier League</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-yellow-400 mb-1">
              {todaysMatches.filter(m => m.league.name.includes('Champions')).length}
            </div>
            <div className="text-sm text-dark-400">Champions League</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-400 mb-1">
              {todaysMatches.filter(m => m.league.name.includes('La Liga')).length}
            </div>
            <div className="text-sm text-dark-400">La Liga</div>
          </div>
        </div>
      </Container>
    </Section>
  );
};

export default TodaysMatches;
