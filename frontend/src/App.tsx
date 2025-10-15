
import { Routes, Route } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import Layout from '@/components/layout/Layout'
import ProtectedRoute from '@/components/ProtectedRoute'
import HomePage from '@/pages/HomePage'
import TodayPredictionsPage from '@/pages/TodayPredictionsPage'
import TomorrowPredictionsPage from '@/pages/TomorrowPredictionsPage'
import MatchDetailPage from '@/pages/MatchDetailPage'
import LeaguesPage from '@/pages/LeaguesPage'
import LeagueDetailPage from '@/pages/LeagueDetailPage'
import TeamDetailPage from '@/pages/TeamDetailPage'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import ResetPasswordPage from '@/pages/ResetPasswordPage'
import DashboardPage from '@/pages/DashboardPage'
import ProfilePage from '@/pages/ProfilePage'
import PasswordChangePage from '@/pages/PasswordChangePage'
import SubscriptionPage from '@/pages/SubscriptionPage'
import NotFoundPage from '@/pages/NotFoundPage'
import APITestPage from '@/pages/APITestPage'
import DebugAPIPage from '@/pages/DebugAPIPage'
import ExpertDashboardPage from '@/pages/ExpertDashboardPage'
import ExpertCreatePredictionPage from '@/pages/ExpertCreatePredictionPage'
import ExpertReviewQueuePage from '@/pages/ExpertReviewQueuePage'
import ExpertMyPredictionsPage from '@/pages/ExpertMyPredictionsPage'
import ExpertMatchSelectionPage from '@/pages/ExpertMatchSelectionPage'

function App() {
  return (
    <>
      <Helmet>
        <title>Soccer Predictions - Professional Football Analytics</title>
        <meta name="description" content="Get accurate soccer predictions with advanced analytics and expert insights. Professional football betting tips and match analysis." />
      </Helmet>
      
      <Routes>
        <Route path="/" element={<Layout />}>
          {/* Public routes */}
          <Route index element={<HomePage />} />
          <Route path="predictions">
            <Route path="today" element={<TodayPredictionsPage />} />
            <Route path="tomorrow" element={<TomorrowPredictionsPage />} />
          </Route>
          <Route path="match/:id" element={<MatchDetailPage />} />
          <Route path="leagues" element={<LeaguesPage />} />
          <Route path="league/:id" element={<LeagueDetailPage />} />
          <Route path="leagues/:leagueId" element={<LeagueDetailPage />} />
          <Route path="teams/:teamId" element={<TeamDetailPage />} />

          {/* Protected routes - require authentication */}
          <Route
            path="dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="profile"
            element={
              <ProtectedRoute>
                <ProfilePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="password-change"
            element={
              <ProtectedRoute>
                <PasswordChangePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="subscription"
            element={
              <ProtectedRoute>
                <SubscriptionPage />
              </ProtectedRoute>
            }
          />

          {/* Expert routes - protected for expert users only */}
          <Route
            path="expert/dashboard"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                <ExpertDashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="expert/match-selection"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                <ExpertMatchSelectionPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="expert/predictions/create"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                <ExpertCreatePredictionPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="expert/predictions/review-queue"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                <ExpertReviewQueuePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="expert/predictions/my-predictions"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                <ExpertMyPredictionsPage />
              </ProtectedRoute>
            }
          />

          {/* Debug routes - protected for development */}
          <Route
            path="api-test"
            element={
              <ProtectedRoute>
                <APITestPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="debug-api"
            element={
              <ProtectedRoute>
                <DebugAPIPage />
              </ProtectedRoute>
            }
          />
        </Route>

        {/* Auth routes without layout */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        {/* 404 page */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  )
}

export default App
