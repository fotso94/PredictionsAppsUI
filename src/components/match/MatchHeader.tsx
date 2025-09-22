import React from 'react';
import { CalendarDaysIcon, ClockIcon, MapPinIcon, TvIcon } from '@heroicons/react/24/outline';
import type { Match } from '../../types';
import Badge from '../ui/Badge';

interface MatchHeaderProps {
  match: Match;
}

const MatchHeader: React.FC<MatchHeaderProps> = ({ match }) => {
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
      case 'finished': return 'FULL TIME';
      case 'scheduled': return 'UPCOMING';
      case 'postponed': return 'POSTPONED';
      case 'cancelled': return 'CANCELLED';
      default: return status.toUpperCase();
    }
  };

  return (
    <div className="bg-dark-800 border border-dark-700 rounded-lg p-6 mb-6">
      {/* League Info */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <img 
            src={match.league.logo} 
            alt={match.league.name}
            className="w-8 h-8"
            onError={(e) => {
              e.currentTarget.src = '/images/placeholder-league.png';
            }}
          />
          <div>
            <h2 className="text-lg font-semibold text-primary-400">{match.league.name}</h2>
            <p className="text-sm text-dark-400">Matchday {match.matchday || 'TBD'}</p>
          </div>
        </div>
        <Badge variant={getStatusColor(match.status)} size="md">
          {formatStatus(match.status)}
        </Badge>
      </div>

      {/* Teams */}
      <div className="flex items-center justify-between mb-6">
        {/* Home Team */}
        <div className="flex-1 text-center">
          <div className="flex flex-col items-center space-y-3">
            <img 
              src={match.homeTeam.logo} 
              alt={match.homeTeam.name}
              className="w-16 h-16 md:w-20 md:h-20"
              onError={(e) => {
                e.currentTarget.src = '/images/placeholder-team.png';
              }}
            />
            <div>
              <h3 className="text-xl md:text-2xl font-bold text-white">{match.homeTeam.name}</h3>
              <p className="text-sm text-dark-400">{match.homeTeam.shortName}</p>
            </div>
          </div>
        </div>

        {/* Score or Time */}
        <div className="flex-shrink-0 px-6">
          {match.result ? (
            <div className="text-center">
              <div className="text-4xl md:text-5xl font-bold text-white mb-2">
                {match.result.homeScore} - {match.result.awayScore}
              </div>
              {match.result.halftimeScore && (
                <div className="text-sm text-dark-400">
                  HT: {match.result.halftimeScore.home}-{match.result.halftimeScore.away}
                </div>
              )}
              {match.status === 'live' && (
                <div className="text-sm text-success-400 font-medium mt-1">
                  {match.minute || 0}'
                </div>
              )}
            </div>
          ) : (
            <div className="text-center">
              <div className="text-2xl md:text-3xl font-bold text-white mb-2">
                {match.time}
              </div>
              <div className="text-sm text-dark-400">
                {new Date(match.date).toLocaleDateString('en-US', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}
              </div>
            </div>
          )}
        </div>

        {/* Away Team */}
        <div className="flex-1 text-center">
          <div className="flex flex-col items-center space-y-3">
            <img 
              src={match.awayTeam.logo} 
              alt={match.awayTeam.name}
              className="w-16 h-16 md:w-20 md:h-20"
              onError={(e) => {
                e.currentTarget.src = '/images/placeholder-team.png';
              }}
            />
            <div>
              <h3 className="text-xl md:text-2xl font-bold text-white">{match.awayTeam.name}</h3>
              <p className="text-sm text-dark-400">{match.awayTeam.shortName}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Match Details */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-6 border-t border-dark-700">
        <div className="flex items-center space-x-2 text-sm text-dark-400">
          <CalendarDaysIcon className="w-4 h-4" />
          <span>{new Date(match.date).toLocaleDateString()}</span>
        </div>
        
        <div className="flex items-center space-x-2 text-sm text-dark-400">
          <ClockIcon className="w-4 h-4" />
          <span>{match.time}</span>
        </div>
        
        {match.venue && (
          <div className="flex items-center space-x-2 text-sm text-dark-400">
            <MapPinIcon className="w-4 h-4" />
            <span>{match.venue}</span>
          </div>
        )}
        
        {match.referee && (
          <div className="flex items-center space-x-2 text-sm text-dark-400">
            <TvIcon className="w-4 h-4" />
            <span>Ref: {match.referee}</span>
          </div>
        )}
      </div>

      {/* Weather Info */}
      {match.weather && (
        <div className="mt-4 pt-4 border-t border-dark-700">
          <div className="flex items-center justify-center space-x-4 text-sm text-dark-400">
            <span>🌡️ {match.weather.temperature}°C</span>
            <span>💨 {match.weather.windSpeed} km/h</span>
            <span>💧 {match.weather.humidity}%</span>
            <span className="capitalize">{match.weather.condition}</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default MatchHeader;
