
import { Routes, Route } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import Layout from '@/components/layout/Layout'
import HomePage from '@/pages/HomePage'
import TodayPredictionsPage from '@/pages/TodayPredictionsPage'
import TomorrowPredictionsPage from '@/pages/TomorrowPredictionsPage'
import MatchDetailPage from '@/pages/MatchDetailPage'
import LeaguesPage from '@/pages/LeaguesPage'
import LeagueDetailPage from '@/pages/LeagueDetailPage'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import DashboardPage from '@/pages/DashboardPage'
import NotFoundPage from '@/pages/NotFoundPage'

function App() {
  return (
    <>
      <Helmet>
        <title>Soccer Predictions - Professional Football Analytics</title>
        <meta name="description" content="Get accurate soccer predictions with advanced analytics and expert insights. Professional football betting tips and match analysis." />
      </Helmet>
      
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="predictions">
            <Route path="today" element={<TodayPredictionsPage />} />
            <Route path="tomorrow" element={<TomorrowPredictionsPage />} />
          </Route>
          <Route path="match/:id" element={<MatchDetailPage />} />
          <Route path="leagues" element={<LeaguesPage />} />
          <Route path="league/:id" element={<LeagueDetailPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
        </Route>
        
        {/* Auth routes without layout */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        
        {/* 404 page */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  )
}

export default App
