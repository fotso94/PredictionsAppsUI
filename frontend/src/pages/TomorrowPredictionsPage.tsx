import React from 'react'
import MatchesPage from './MatchesPage'

/**
 * `/predictions/tomorrow`.
 *
 * Same workspace as `/predictions/today`, with tomorrow preselected. Keeping the two routes costs
 * two lines each and keeps every existing link and bookmark working.
 */
const TomorrowPredictionsPage: React.FC = () => <MatchesPage preset="tomorrow" />

export default TomorrowPredictionsPage
