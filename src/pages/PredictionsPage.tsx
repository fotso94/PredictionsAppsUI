import React, { useState, useMemo } from 'react';
import { Helmet } from 'react-helmet-async';
import { CalendarDaysIcon, ClockIcon, AdjustmentsHorizontalIcon } from '@heroicons/react/24/outline';
import Container from '../components/layout/Container';
import PredictionsFilter from '../components/predictions/PredictionsFilter';
import PredictionCard from '../components/ui/PredictionCard';
import { LoadingOverlay, Skeleton } from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';
import Tabs, { TabsList, TabsTrigger, TabsContent } from '../components/ui/Tabs';
import { mockPredictions } from '../data/mockPredictions';

interface FilterOptions {
  predictionType: string;
  league: string;
  confidence: string;
  status: string;
}

const PredictionsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('today');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [filters, setFilters] = useState<FilterOptions>({
    predictionType: 'all',
    league: 'all',
    confidence: 'all',
    status: 'all',
  });

  // Filter predictions based on current filters and tab
  const filteredPredictions = useMemo(() => {
    let predictions = [...mockPredictions];

    // Filter by tab (today/tomorrow/all)
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    if (activeTab === 'today') {
      predictions = predictions.filter(p => {
        const matchDate = new Date(p.match.date);
        return matchDate.toDateString() === today.toDateString();
      });
    } else if (activeTab === 'tomorrow') {
      predictions = predictions.filter(p => {
        const matchDate = new Date(p.match.date);
        return matchDate.toDateString() === tomorrow.toDateString();
      });
    }

    // Apply filters
    if (filters.predictionType !== 'all') {
      predictions = predictions.filter(p => p.predictionType === filters.predictionType);
    }

    if (filters.league !== 'all') {
      predictions = predictions.filter(p => 
        p.match.league.name.toLowerCase().includes(filters.league.replace('-', ' '))
      );
    }

    if (filters.confidence !== 'all') {
      predictions = predictions.filter(p => {
        if (filters.confidence === 'high') return p.confidence >= 80;
        if (filters.confidence === 'medium') return p.confidence >= 60 && p.confidence < 80;
        if (filters.confidence === 'low') return p.confidence < 60;
        return true;
      });
    }

    if (filters.status !== 'all') {
      predictions = predictions.filter(p => p.status === filters.status);
    }

    return predictions;
  }, [activeTab, filters]);

  const handleFilterChange = (newFilters: FilterOptions) => {
    setFilters(newFilters);
  };

  const handleClearFilters = () => {
    setFilters({
      predictionType: 'all',
      league: 'all',
      confidence: 'all',
      status: 'all',
    });
  };

  const getTabTitle = (tab: string) => {
    switch (tab) {
      case 'today': return "Today's Predictions";
      case 'tomorrow': return "Tomorrow's Predictions";
      case 'all': return 'All Predictions';
      default: return 'Predictions';
    }
  };

  const getTabDescription = (tab: string) => {
    switch (tab) {
      case 'today': return 'Expert predictions for today\'s matches with detailed analysis and confidence ratings.';
      case 'tomorrow': return 'Get ahead with tomorrow\'s match predictions and betting insights.';
      case 'all': return 'Browse all available predictions across different leagues and betting markets.';
      default: return 'Expert soccer predictions and betting tips.';
    }
  };

  return (
    <>
      <Helmet>
        <title>{getTabTitle(activeTab)} - PredictionsApp</title>
        <meta name="description" content={getTabDescription(activeTab)} />
        <meta name="keywords" content="soccer predictions, football betting, match predictions, betting tips" />
      </Helmet>

      <div className="min-h-screen bg-dark-900 py-8">
        <Container>
          {/* Page Header */}
          <div className="mb-8">
            <div className="flex items-center space-x-2 mb-4">
              <CalendarDaysIcon className="w-8 h-8 text-primary-500" />
              <h1 className="text-3xl md:text-4xl font-bold text-white">
                Soccer <span className="gradient-text">Predictions</span>
              </h1>
            </div>
            <p className="text-lg text-dark-300 max-w-2xl">
              Expert predictions with detailed analysis, confidence ratings, and proven track record.
              Filter by league, betting market, or confidence level to find the perfect picks.
            </p>
          </div>

          {/* Tabs */}
          <div className="mb-6">
            <Tabs value={activeTab} onChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="today">
                  <ClockIcon className="w-4 h-4 mr-2" />
                  Today
                </TabsTrigger>
                <TabsTrigger value="tomorrow">
                  <CalendarDaysIcon className="w-4 h-4 mr-2" />
                  Tomorrow
                </TabsTrigger>
                <TabsTrigger value="all">
                  All Predictions
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Mobile Filter Toggle */}
          <div className="lg:hidden mb-4">
            <Button
              variant="outline"
              onClick={() => setIsFilterOpen(!isFilterOpen)}
              icon={<AdjustmentsHorizontalIcon className="w-5 h-5" />}
              fullWidth
            >
              {isFilterOpen ? 'Hide Filters' : 'Show Filters'}
            </Button>
          </div>

          {/* Filters */}
          <div className="mb-6">
            <PredictionsFilter
              filters={filters}
              onFilterChange={handleFilterChange}
              onClearFilters={handleClearFilters}
              isOpen={isFilterOpen}
              onToggle={() => setIsFilterOpen(!isFilterOpen)}
            />
          </div>

          {/* Results Summary */}
          <div className="mb-6">
            <div className="flex items-center justify-between">
              <div className="text-dark-300">
                Showing <span className="text-white font-semibold">{filteredPredictions.length}</span> predictions
              </div>
              <div className="text-sm text-dark-400">
                Last updated: {new Date().toLocaleTimeString()}
              </div>
            </div>
          </div>

          {/* Tab Content */}
          <Tabs value={activeTab} onChange={setActiveTab}>
            <TabsContent value="today">
              <LoadingOverlay isLoading={isLoading}>
                {filteredPredictions.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredPredictions.map((prediction) => (
                      <PredictionCard
                        key={prediction.id}
                        prediction={prediction}
                        onViewDetails={() => {
                          // Navigate to prediction details
                        }}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <div className="text-6xl mb-4">🔍</div>
                    <h3 className="text-xl font-semibold text-white mb-2">No predictions found</h3>
                    <p className="text-dark-400 mb-4">
                      Try adjusting your filters or check back later for new predictions.
                    </p>
                    <Button variant="outline" onClick={handleClearFilters}>
                      Clear Filters
                    </Button>
                  </div>
                )}
              </LoadingOverlay>
            </TabsContent>

            <TabsContent value="tomorrow">
              <LoadingOverlay isLoading={isLoading}>
                {filteredPredictions.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredPredictions.map((prediction) => (
                      <PredictionCard
                        key={prediction.id}
                        prediction={prediction}
                        onViewDetails={() => {
                          // Navigate to prediction details
                        }}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <div className="text-6xl mb-4">📅</div>
                    <h3 className="text-xl font-semibold text-white mb-2">No predictions for tomorrow yet</h3>
                    <p className="text-dark-400 mb-4">
                      Tomorrow's predictions will be available soon. Check back later!
                    </p>
                    <Button variant="primary" onClick={() => setActiveTab('today')}>
                      View Today's Predictions
                    </Button>
                  </div>
                )}
              </LoadingOverlay>
            </TabsContent>

            <TabsContent value="all">
              <LoadingOverlay isLoading={isLoading}>
                {filteredPredictions.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredPredictions.map((prediction) => (
                      <PredictionCard
                        key={prediction.id}
                        prediction={prediction}
                        onViewDetails={() => {
                          // Navigate to prediction details
                        }}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <div className="text-6xl mb-4">🎯</div>
                    <h3 className="text-xl font-semibold text-white mb-2">No predictions available</h3>
                    <p className="text-dark-400 mb-4">
                      Our experts are working on new predictions. Please check back soon!
                    </p>
                  </div>
                )}
              </LoadingOverlay>
            </TabsContent>
          </Tabs>

          {/* Load More Button */}
          {filteredPredictions.length > 0 && (
            <div className="text-center mt-8">
              <Button
                variant="outline"
                size="lg"
                onClick={() => {
                  setIsLoading(true);
                  // Simulate loading more predictions
                  setTimeout(() => setIsLoading(false), 1000);
                }}
              >
                Load More Predictions
              </Button>
            </div>
          )}
        </Container>
      </div>
    </>
  );
};

export default PredictionsPage;
