import React from 'react';
import { clsx } from 'clsx';
import { CalendarIcon, ClockIcon, MapPinIcon } from '@heroicons/react/24/outline';
import type { Match } from '../../types';
import Card from './Card';
import Badge from './Badge';
import Button from './Button';

interface MatchCardProps {
  match: Match;
  onViewPredictions?: () => void;
  onViewDetails?: () => void;
  className?: string;
  showPredictions?: boolean;
}

const MatchCard: React.FC<MatchCardProps> = ({
  match,
  onViewPredictions,
  onViewDetails,
  className,
  showPredictions = true,
}) => {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'live': return 'success';
      case 'finished': return 'secondary';
      case 'scheduled': return 'primary';
      case 'postponed': return 'warning';
      case 'cancelled': return 'danger';
      default: return 'secondary';
    }
  };

  const formatStatus = (status: string) => {
    switch (status) {
      case 'live': return 'LIVE';
      case 'finished': return 'FT';
      case 'scheduled': return 'Scheduled';
      case 'postponed': return 'Postponed';
      case 'cancelled': return 'Cancelled';
      default: return status.toUpperCase();
    }
  };

  return (
    <Card 
      className={clsx('transition-all duration-200 hover:shadow-xl', className)}
      hover
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <img 
            src={match.league.logo} 
            alt={match.league.name}
            className="w-6 h-6"
            onError={(e) => {
              e.currentTarget.src = '/images/placeholder-league.png';
            }}
          />
          <span className="text-sm font-medium text-primary-400">
            {match.league.name}
          </span>
        </div>
        <Badge variant={getStatusColor(match.status)} size="sm">
          {formatStatus(match.status)}
        </Badge>
      </div>

      {/* Teams */}
      <div className="mb-4">
        <div className="flex items-center justify-between">
          {/* Home Team */}
          <div className="flex items-center space-x-3 flex-1">
            <img 
              src={match.homeTeam.logo} 
              alt={match.homeTeam.name}
              className="w-10 h-10"
              onError={(e) => {
                e.currentTarget.src = '/images/placeholder-team.png';
              }}
            />
            <div>
              <div className="text-white font-semibold">{match.homeTeam.name}</div>
              <div className="text-sm text-dark-400">{match.homeTeam.shortName}</div>
            </div>
          </div>

          {/* Score or Time */}
          <div className="flex flex-col items-center px-4">
            {match.result ? (
              <div className="text-center">
                <div className="text-2xl font-bold text-white">
                  {match.result.homeScore} - {match.result.awayScore}
                </div>
                {match.result.halftimeScore && (
                  <div className="text-sm text-dark-400">
                    HT: {match.result.halftimeScore.home}-{match.result.halftimeScore.away}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center">
                <div className="text-lg font-semibold text-white">{match.time}</div>
                <div className="text-sm text-dark-400">
                  {new Date(match.date).toLocaleDateString()}
                </div>
              </div>
            )}
          </div>

          {/* Away Team */}
          <div className="flex items-center space-x-3 flex-1 justify-end">
            <div className="text-right">
              <div className="text-white font-semibold">{match.awayTeam.name}</div>
              <div className="text-sm text-dark-400">{match.awayTeam.shortName}</div>
            </div>
            <img 
              src={match.awayTeam.logo} 
              alt={match.awayTeam.name}
              className="w-10 h-10"
              onError={(e) => {
                e.currentTarget.src = '/images/placeholder-team.png';
              }}
            />
          </div>
        </div>
      </div>

      {/* Match Details */}
      <div className="mb-4 space-y-2">
        <div className="flex items-center space-x-4 text-sm text-dark-400">
          <div className="flex items-center space-x-1">
            <CalendarIcon className="w-4 h-4" />
            <span>{new Date(match.date).toLocaleDateString()}</span>
          </div>
          <div className="flex items-center space-x-1">
            <ClockIcon className="w-4 h-4" />
            <span>{match.time}</span>
          </div>
          {match.venue && (
            <div className="flex items-center space-x-1">
              <MapPinIcon className="w-4 h-4" />
              <span>{match.venue}</span>
            </div>
          )}
        </div>
      </div>

      {/* Odds (if available) */}
      {match.odds && (
        <div className="mb-4">
          <div className="bg-dark-700 rounded-lg p-3">
            <div className="text-sm text-dark-300 mb-2">Odds:</div>
            <div className="grid grid-cols-3 gap-2 text-sm">
              <div className="text-center">
                <div className="text-dark-400">1</div>
                <div className="text-white font-semibold">{match.odds.homeWin}</div>
              </div>
              <div className="text-center">
                <div className="text-dark-400">X</div>
                <div className="text-white font-semibold">{match.odds.draw}</div>
              </div>
              <div className="text-center">
                <div className="text-dark-400">2</div>
                <div className="text-white font-semibold">{match.odds.awayWin}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex space-x-2">
        {showPredictions && onViewPredictions && (
          <Button
            variant="primary"
            size="sm"
            onClick={onViewPredictions}
            fullWidth
          >
            View Predictions
          </Button>
        )}
        {onViewDetails && (
          <Button
            variant="outline"
            size="sm"
            onClick={onViewDetails}
            fullWidth={!showPredictions}
          >
            Match Details
          </Button>
        )}
      </div>
    </Card>
  );
};

export default MatchCard;
