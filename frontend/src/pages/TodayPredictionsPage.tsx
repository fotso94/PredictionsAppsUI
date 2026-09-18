import React from 'react'
import MatchesPage from './MatchesPage'

/**
 * `/predictions/today`.
 *
 * The route is kept because it is linked from across the site and asserted by the browser suite;
 * the page it renders is now the one matchday workspace with today preselected, rather than a
 * second near-copy of the same list with its own filter panel to maintain.
 */
const TodayPredictionsPage: React.FC = () => <MatchesPage preset="today" />

export default TodayPredictionsPage
