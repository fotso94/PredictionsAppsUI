import React from 'react';
import type { Team } from '../../types';

interface TeamStatsProps {
  homeTeam: Team;
  awayTeam: Team;
}

interface StatItem {
  label: string;
  homeValue: number | string;
  awayValue: number | string;
  format?: 'number' | 'percentage' | 'decimal';
}

const TeamStats: React.FC<TeamStatsProps> = ({ homeTeam, awayTeam }) => {
  const stats: StatItem[] = [
    {
      label: 'League Position',
      homeValue: homeTeam.leaguePosition || 'N/A',
      awayValue: awayTeam.leaguePosition || 'N/A',
    },
    {
      label: 'Matches Played',
      homeValue: homeTeam.matchesPlayed || 0,
      awayValue: awayTeam.matchesPlayed || 0,
    },
    {
      label: 'Wins',
      homeValue: homeTeam.wins || 0,
      awayValue: awayTeam.wins || 0,
    },
    {
      label: 'Draws',
      homeValue: homeTeam.draws || 0,
      awayValue: awayTeam.draws || 0,
    },
    {
      label: 'Losses',
      homeValue: homeTeam.losses || 0,
      awayValue: awayTeam.losses || 0,
    },
    {
      label: 'Goals For',
      homeValue: homeTeam.goalsFor || 0,
      awayValue: awayTeam.goalsFor || 0,
    },
    {
      label: 'Goals Against',
      homeValue: homeTeam.goalsAgainst || 0,
      awayValue: awayTeam.goalsAgainst || 0,
    },
    {
      label: 'Goal Difference',
      homeValue: (homeTeam.goalsFor || 0) - (homeTeam.goalsAgainst || 0),
      awayValue: (awayTeam.goalsFor || 0) - (awayTeam.goalsAgainst || 0),
    },
    {
      label: 'Points',
      homeValue: homeTeam.points || 0,
      awayValue: awayTeam.points || 0,
    },
    {
      label: 'Win Rate',
      homeValue: homeTeam.matchesPlayed ? ((homeTeam.wins || 0) / homeTeam.matchesPlayed * 100) : 0,
      awayValue: awayTeam.matchesPlayed ? ((awayTeam.wins || 0) / awayTeam.matchesPlayed * 100) : 0,
      format: 'percentage' as const,
    },
    {
      label: 'Avg Goals/Game',
      homeValue: homeTeam.matchesPlayed ? ((homeTeam.goalsFor || 0) / homeTeam.matchesPlayed) : 0,
      awayValue: awayTeam.matchesPlayed ? ((awayTeam.goalsFor || 0) / awayTeam.matchesPlayed) : 0,
      format: 'decimal' as const,
    },
    {
      label: 'Clean Sheets',
      homeValue: homeTeam.cleanSheets || 0,
      awayValue: awayTeam.cleanSheets || 0,
    },
  ];

  const formatValue = (value: number | string, format?: string): string => {
    if (typeof value === 'string') return value;
    
    switch (format) {
      case 'percentage':
        return `${value.toFixed(1)}%`;
      case 'decimal':
        return value.toFixed(2);
      default:
        return value.toString();
    }
  };

  const getStatComparison = (homeValue: number | string, awayValue: number | string) => {
    if (typeof homeValue === 'string' || typeof awayValue === 'string') {
      return { homeWidth: 50, awayWidth: 50 };
    }

    const total = Math.abs(homeValue) + Math.abs(awayValue);
    if (total === 0) return { homeWidth: 50, awayWidth: 50 };

    const homeWidth = (Math.abs(homeValue) / total) * 100;
    const awayWidth = (Math.abs(awayValue) / total) * 100;

    return { homeWidth, awayWidth };
  };

  const getBetterStat = (homeValue: number | string, awayValue: number | string, label: string) => {
    if (typeof homeValue === 'string' || typeof awayValue === 'string') return 'neutral';
    
    // For some stats, lower is better
    const lowerIsBetter = ['Goals Against', 'Losses', 'League Position'];
    
    if (lowerIsBetter.includes(label)) {
      if (homeValue < awayValue) return 'home';
      if (awayValue < homeValue) return 'away';
    } else {
      if (homeValue > awayValue) return 'home';
      if (awayValue > homeValue) return 'away';
    }
    
    return 'neutral';
  };

  return (
    <div className="bg-dark-800 border border-dark-700 rounded-lg p-6">
      <h3 className="text-xl font-bold text-white mb-6 text-center">Team Statistics</h3>
      
      <div className="space-y-4">
        {stats.map((stat, index) => {
          const comparison = getStatComparison(stat.homeValue, stat.awayValue);
          const betterStat = getBetterStat(stat.homeValue, stat.awayValue, stat.label);
          
          return (
            <div key={index} className="space-y-2">
              {/* Stat Labels and Values */}
              <div className="flex items-center justify-between">
                <div className={`text-sm font-medium ${betterStat === 'home' ? 'text-success-400' : 'text-white'}`}>
                  {formatValue(stat.homeValue, stat.format)}
                </div>
                <div className="text-sm font-medium text-dark-300 text-center flex-1 px-4">
                  {stat.label}
                </div>
                <div className={`text-sm font-medium ${betterStat === 'away' ? 'text-success-400' : 'text-white'}`}>
                  {formatValue(stat.awayValue, stat.format)}
                </div>
              </div>
              
              {/* Visual Comparison Bar */}
              {typeof stat.homeValue === 'number' && typeof stat.awayValue === 'number' && (
                <div className="flex items-center space-x-2">
                  {/* Home Team Bar */}
                  <div className="flex-1 h-2 bg-dark-700 rounded-full overflow-hidden">
                    <div 
                      className={`h-full transition-all duration-300 ${
                        betterStat === 'home' ? 'bg-success-500' : 'bg-primary-500'
                      }`}
                      style={{ width: `${comparison.homeWidth}%` }}
                    />
                  </div>
                  
                  {/* Center Divider */}
                  <div className="w-px h-4 bg-dark-600" />
                  
                  {/* Away Team Bar */}
                  <div className="flex-1 h-2 bg-dark-700 rounded-full overflow-hidden">
                    <div 
                      className={`h-full transition-all duration-300 ml-auto ${
                        betterStat === 'away' ? 'bg-success-500' : 'bg-primary-500'
                      }`}
                      style={{ width: `${comparison.awayWidth}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Team Names Footer */}
      <div className="flex items-center justify-between mt-6 pt-4 border-t border-dark-700">
        <div className="flex items-center space-x-2">
          <img 
            src={homeTeam.logo} 
            alt={homeTeam.name}
            className="w-6 h-6"
            onError={(e) => {
              e.currentTarget.src = '/images/placeholder-team.png';
            }}
          />
          <span className="text-sm font-medium text-white">{homeTeam.shortName}</span>
        </div>
        
        <div className="flex items-center space-x-2">
          <span className="text-sm font-medium text-white">{awayTeam.shortName}</span>
          <img 
            src={awayTeam.logo} 
            alt={awayTeam.name}
            className="w-6 h-6"
            onError={(e) => {
              e.currentTarget.src = '/images/placeholder-team.png';
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default TeamStats;
