import React from 'react';
import { FunnelIcon, XMarkIcon } from '@heroicons/react/24/outline';
import Button from '../ui/Button';
import Dropdown from '../ui/Dropdown';
import Badge from '../ui/Badge';

interface FilterOptions {
  predictionType: string;
  league: string;
  confidence: string;
  status: string;
}

interface PredictionsFilterProps {
  filters: FilterOptions;
  onFilterChange: (filters: FilterOptions) => void;
  onClearFilters: () => void;
  isOpen: boolean;
  onToggle: () => void;
}

const PredictionsFilter: React.FC<PredictionsFilterProps> = ({
  filters,
  onFilterChange,
  onClearFilters,
  isOpen,
  onToggle,
}) => {
  const predictionTypeOptions = [
    { value: 'all', label: 'All Types' },
    { value: '1x2', label: '1X2 (Match Result)' },
    { value: 'btts', label: 'Both Teams to Score' },
    { value: 'over_under', label: 'Over/Under Goals' },
    { value: 'correct_score', label: 'Correct Score' },
    { value: 'double_chance', label: 'Double Chance' },
    { value: 'handicap', label: 'Asian Handicap' },
  ];

  const leagueOptions = [
    { value: 'all', label: 'All Leagues' },
    { value: 'premier-league', label: 'Premier League' },
    { value: 'champions-league', label: 'Champions League' },
    { value: 'la-liga', label: 'La Liga' },
    { value: 'bundesliga', label: 'Bundesliga' },
    { value: 'serie-a', label: 'Serie A' },
    { value: 'ligue-1', label: 'Ligue 1' },
  ];

  const confidenceOptions = [
    { value: 'all', label: 'All Confidence' },
    { value: 'high', label: 'High (80%+)' },
    { value: 'medium', label: 'Medium (60-79%)' },
    { value: 'low', label: 'Low (<60%)' },
  ];

  const statusOptions = [
    { value: 'all', label: 'All Status' },
    { value: 'pending', label: 'Pending' },
    { value: 'won', label: 'Won' },
    { value: 'lost', label: 'Lost' },
  ];

  const handleFilterChange = (key: keyof FilterOptions, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value,
    });
  };

  const getActiveFiltersCount = () => {
    return Object.values(filters).filter(value => value !== 'all').length;
  };

  const activeFiltersCount = getActiveFiltersCount();

  return (
    <div className="bg-dark-800 border border-dark-700 rounded-lg">
      {/* Filter Header */}
      <div className="flex items-center justify-between p-4 border-b border-dark-700">
        <div className="flex items-center space-x-2">
          <FunnelIcon className="w-5 h-5 text-primary-400" />
          <span className="font-semibold text-white">Filters</span>
          {activeFiltersCount > 0 && (
            <Badge variant="primary" size="sm">
              {activeFiltersCount}
            </Badge>
          )}
        </div>
        
        <div className="flex items-center space-x-2">
          {activeFiltersCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onClearFilters}
              icon={<XMarkIcon className="w-4 h-4" />}
            >
              Clear All
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggle}
            className="lg:hidden"
          >
            {isOpen ? 'Hide' : 'Show'}
          </Button>
        </div>
      </div>

      {/* Filter Content */}
      <div className={`${isOpen ? 'block' : 'hidden'} lg:block p-4`}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Prediction Type Filter */}
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              Prediction Type
            </label>
            <Dropdown
              options={predictionTypeOptions}
              value={filters.predictionType}
              onChange={(value) => handleFilterChange('predictionType', value)}
              fullWidth
            />
          </div>

          {/* League Filter */}
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              League
            </label>
            <Dropdown
              options={leagueOptions}
              value={filters.league}
              onChange={(value) => handleFilterChange('league', value)}
              fullWidth
            />
          </div>

          {/* Confidence Filter */}
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              Confidence Level
            </label>
            <Dropdown
              options={confidenceOptions}
              value={filters.confidence}
              onChange={(value) => handleFilterChange('confidence', value)}
              fullWidth
            />
          </div>

          {/* Status Filter */}
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              Status
            </label>
            <Dropdown
              options={statusOptions}
              value={filters.status}
              onChange={(value) => handleFilterChange('status', value)}
              fullWidth
            />
          </div>
        </div>

        {/* Active Filters Display */}
        {activeFiltersCount > 0 && (
          <div className="mt-4 pt-4 border-t border-dark-700">
            <div className="flex flex-wrap gap-2">
              {Object.entries(filters).map(([key, value]) => {
                if (value === 'all') return null;
                
                const getFilterLabel = (key: string, value: string) => {
                  switch (key) {
                    case 'predictionType':
                      return predictionTypeOptions.find(opt => opt.value === value)?.label || value;
                    case 'league':
                      return leagueOptions.find(opt => opt.value === value)?.label || value;
                    case 'confidence':
                      return confidenceOptions.find(opt => opt.value === value)?.label || value;
                    case 'status':
                      return statusOptions.find(opt => opt.value === value)?.label || value;
                    default:
                      return value;
                  }
                };

                return (
                  <div
                    key={key}
                    className="flex items-center space-x-1 bg-primary-600/20 text-primary-400 px-3 py-1 rounded-full text-sm"
                  >
                    <span>{getFilterLabel(key, value)}</span>
                    <button
                      onClick={() => handleFilterChange(key as keyof FilterOptions, 'all')}
                      className="hover:text-primary-300 transition-colors duration-200"
                    >
                      <XMarkIcon className="w-4 h-4" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default PredictionsFilter;
