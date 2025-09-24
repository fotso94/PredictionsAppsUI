import React from 'react';
import { clsx } from 'clsx';
import { CalendarIcon, ClockIcon, TrophyIcon } from '@heroicons/react/24/outline';
import type { Prediction } from '../../types';
import Card from './Card';
import Badge, { ConfidenceBadge } from './Badge';
import Button from './Button';

interface PredictionCardProps {
  prediction: Prediction;
  onViewDetails?: () => void;
  className?: string;
  compact?: boolean;
}

const PredictionCard: React.FC<PredictionCardProps> = ({
  prediction,
  onViewDetails,
  className,
  compact = false,
}) => {
  const { match, predictionType, prediction: predictionValue, confidence, odds, status } = prediction;

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'won': return 'success';
      case 'lost': return 'danger';
      case 'pending': return 'warning';
      default: return 'secondary';
    }
  };

  const formatPredictionType = (type: string) => {
    switch (type) {
      case '1x2': return '1X2';
      case 'over_under': return 'Over/Under';
      case 'btts': return 'BTTS';
      case 'correct_score': return 'Correct Score';
      case 'double_chance': return 'Double Chance';
      default: return type.replace('_', ' ').toUpperCase();
    }
  };

  return (
    <Card 
      className={clsx('transition-all duration-200 hover:shadow-xl', className)}
      padding={compact ? 'sm' : 'md'}
      hover
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <TrophyIcon className="w-5 h-5 text-primary-500" />
          <span className="text-sm font-medium text-primary-400">
            {formatPredictionType(predictionType)}
          </span>
        </div>
        <Badge variant={getStatusColor(status)} size="sm">
          {status.toUpperCase()}
        </Badge>
      </div>

      {/* Match Info */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2">
              <img 
                src={match.homeTeam.logo} 
                alt={match.homeTeam.name}
                className="w-6 h-6"
                onError={(e) => {
                  e.currentTarget.src = '/images/placeholder-team.png';
                }}
              />
              <span className="text-white font-medium">
                {compact ? match.homeTeam.shortName : match.homeTeam.name}
              </span>
            </div>
            <span className="text-dark-400">vs</span>
            <div className="flex items-center space-x-2">
              <img 
                src={match.awayTeam.logo} 
                alt={match.awayTeam.name}
                className="w-6 h-6"
                onError={(e) => {
                  e.currentTarget.src = '/images/placeholder-team.png';
                }}
              />
              <span className="text-white font-medium">
                {compact ? match.awayTeam.shortName : match.awayTeam.name}
              </span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center space-x-4 text-sm text-dark-400">
          <div className="flex items-center space-x-1">
            <CalendarIcon className="w-4 h-4" />
            <span>{new Date(match.date).toLocaleDateString()}</span>
          </div>
          <div className="flex items-center space-x-1">
            <ClockIcon className="w-4 h-4" />
            <span>{match.time}</span>
          </div>
          <span className="text-primary-400">{match.league.name}</span>
        </div>
      </div>

      {/* Prediction Details */}
      <div className="mb-4">
        <div className="bg-dark-700 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-dark-300">Prediction:</span>
            <span className="text-white font-semibold">{predictionValue}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-dark-300">Odds:</span>
            <span className="text-success-400 font-semibold">{odds.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {/* Confidence & Actions */}
      <div className="flex items-center justify-between">
        <ConfidenceBadge confidence={confidence} />
        {onViewDetails && (
          <Button
            variant="outline"
            size="sm"
            onClick={onViewDetails}
          >
            View Details
          </Button>
        )}
      </div>

      {/* Result (if available) */}
      {prediction.result && (
        <div className="mt-3 pt-3 border-t border-dark-700">
          <div className="flex items-center justify-between text-sm">
            <span className="text-dark-300">Result:</span>
            <div className="flex items-center space-x-2">
              <span className={clsx(
                'font-semibold',
                prediction.result.status === 'won' ? 'text-success-400' : 'text-danger-400'
              )}>
                {prediction.result.status === 'won' ? '+' : ''}
                ${prediction.result.profit.toFixed(2)}
              </span>
              <Badge 
                variant={prediction.result.status === 'won' ? 'success' : 'danger'} 
                size="sm"
              >
                {prediction.result.status.toUpperCase()}
              </Badge>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
};

export default PredictionCard;
