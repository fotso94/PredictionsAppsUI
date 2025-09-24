import React, { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { FunnelIcon, CalendarDaysIcon } from '@heroicons/react/24/outline'
import { mockTomorrowMatches, mockLeagues } from '@/data/mockData'
import { BettingMarket, ConfidenceLevel } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import MatchCard from '@/components/ui/MatchCard'
import { Badge } from '@/components/ui/Badge'
import { motion } from 'framer-motion'

const TomorrowPredictionsPage: React.FC = () => {
  const [selectedLeagues, setSelectedLeagues] = useState<string[]>([])
  const [selectedMarkets, setSelectedMarkets] = useState<BettingMarket[]>([])
  const [selectedConfidence, setSelectedConfidence] = useState<ConfidenceLevel[]>([])

  const markets: { value: BettingMarket; label: string }[] = [
    { value: '1x2', label: '1X2' },
    { value: 'btts', label: 'Both Teams to Score' },
    { value: 'over-under', label: 'Over/Under' },
    { value: 'correct-score', label: 'Correct Score' },
  ]

  const confidenceLevels: { value: ConfidenceLevel; label: string }[] = [
    { value: 'low', label: 'Low' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' },
    { value: 'very-high', label: 'Very High' },
  ]

  const filteredMatches = mockTomorrowMatches.filter(match => {
    if (selectedLeagues.length > 0 && !selectedLeagues.includes(match.league.id)) {
      return false
    }
    
    if (selectedConfidence.length > 0) {
      const hasMatchingConfidence = 
        selectedConfidence.includes(match.predictions.outcome.confidence) ||
        selectedConfidence.includes(match.predictions.bothTeamsToScore.confidence) ||
        selectedConfidence.includes(match.predictions.totalGoals.confidence)
      
      if (!hasMatchingConfidence) return false
    }
    
    return true
  })

  const toggleLeague = (leagueId: string) => {
    setSelectedLeagues(prev => 
      prev.includes(leagueId) 
        ? prev.filter(id => id !== leagueId)
        : [...prev, leagueId]
    )
  }

  const toggleMarket = (market: BettingMarket) => {
    setSelectedMarkets(prev => 
      prev.includes(market) 
        ? prev.filter(m => m !== market)
        : [...prev, market]
    )
  }

  const toggleConfidence = (confidence: ConfidenceLevel) => {
    setSelectedConfidence(prev => 
      prev.includes(confidence) 
        ? prev.filter(c => c !== confidence)
        : [...prev, confidence]
    )
  }

  const clearFilters = () => {
    setSelectedLeagues([])
    setSelectedMarkets([])
    setSelectedConfidence([])
  }

  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const tomorrowFormatted = tomorrow.toLocaleDateString('en-US', { 
    weekday: 'long', 
    year: 'numeric', 
    month: 'long', 
    day: 'numeric' 
  })

  return (
    <>
      <Helmet>
        <title>Tomorrow's Soccer Predictions - {tomorrowFormatted}</title>
        <meta name="description" content={`Professional soccer predictions for ${tomorrowFormatted}. Get expert betting tips and match analysis for tomorrow's games.`} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="mb-8"
          >
            <div className="flex items-center space-x-2 mb-2">
              <CalendarDaysIcon className="h-6 w-6 text-primary-500" />
              <h1 className="text-3xl font-bold text-white">Tomorrow's Predictions</h1>
            </div>
            <p className="text-secondary-400">{tomorrowFormatted}</p>
            <div className="mt-4 flex items-center space-x-4">
              <Badge variant="info">{filteredMatches.length} matches</Badge>
              <Badge variant="success">
                {filteredMatches.filter(m => m.predictions.outcome.confidence === 'high' || m.predictions.outcome.confidence === 'very-high').length} high confidence
              </Badge>
            </div>
          </motion.div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
            {/* Filters Sidebar */}
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="lg:col-span-1"
            >
              <Card>
                <Card.Header>
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-white flex items-center">
                      <FunnelIcon className="h-5 w-5 mr-2" />
                      Filters
                    </h3>
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      onClick={clearFilters}
                      className="text-xs"
                    >
                      Clear All
                    </Button>
                  </div>
                </Card.Header>
                <Card.Body className="space-y-6">
                  {/* Leagues Filter */}
                  <div>
                    <h4 className="text-sm font-medium text-white mb-3">Leagues</h4>
                    <div className="space-y-2">
                      {mockLeagues.map(league => (
                        <label key={league.id} className="flex items-center">
                          <input
                            type="checkbox"
                            checked={selectedLeagues.includes(league.id)}
                            onChange={() => toggleLeague(league.id)}
                            className="rounded border-dark-600 bg-dark-800 text-primary-600 focus:ring-primary-500"
                          />
                          <span className="ml-2 text-sm text-secondary-300">{league.shortName}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Markets Filter */}
                  <div>
                    <h4 className="text-sm font-medium text-white mb-3">Markets</h4>
                    <div className="space-y-2">
                      {markets.map(market => (
                        <label key={market.value} className="flex items-center">
                          <input
                            type="checkbox"
                            checked={selectedMarkets.includes(market.value)}
                            onChange={() => toggleMarket(market.value)}
                            className="rounded border-dark-600 bg-dark-800 text-primary-600 focus:ring-primary-500"
                          />
                          <span className="ml-2 text-sm text-secondary-300">{market.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Confidence Filter */}
                  <div>
                    <h4 className="text-sm font-medium text-white mb-3">Confidence Level</h4>
                    <div className="space-y-2">
                      {confidenceLevels.map(level => (
                        <label key={level.value} className="flex items-center">
                          <input
                            type="checkbox"
                            checked={selectedConfidence.includes(level.value)}
                            onChange={() => toggleConfidence(level.value)}
                            className="rounded border-dark-600 bg-dark-800 text-primary-600 focus:ring-primary-500"
                          />
                          <span className="ml-2 text-sm text-secondary-300">{level.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </Card.Body>
              </Card>
            </motion.div>

            {/* Matches Grid */}
            <div className="lg:col-span-3">
              {filteredMatches.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.6 }}
                  className="text-center py-12"
                >
                  <div className="text-secondary-400 mb-4">No matches found with current filters</div>
                  <Button onClick={clearFilters}>Clear Filters</Button>
                </motion.div>
              ) : (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.6, delay: 0.4 }}
                  className="grid grid-cols-1 xl:grid-cols-2 gap-6"
                >
                  {filteredMatches.map((match, index) => (
                    <motion.div
                      key={match.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.5, delay: 0.1 * index }}
                    >
                      <MatchCard match={match} />
                    </motion.div>
                  ))}
                </motion.div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

export default TomorrowPredictionsPage
