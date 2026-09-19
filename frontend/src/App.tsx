import React, { Suspense, lazy, useEffect, useState } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import Layout from '@/components/layout/Layout'
import ProtectedRoute from '@/components/ProtectedRoute'
import type { TranslateFn } from '@/i18n'
import { useT } from '@/i18n/react'

/**
 * The route table, and the one thing it now does differently: it does not hand every reader every
 * page.
 *
 * WHAT IT COST BEFORE, MEASURED. One chunk — 713.10 kB raw / 199.44 kB gzipped when this was
 * re-measured against the tree it shipped from — downloaded in full before a single fixture
 * appeared: the expert composer, the review queue, the dashboard, the subscription screens, the
 * two debug pages and every auth form included. A reader who only ever looks at today's matches
 * paid for all of it, on every new device and after every deploy. It is now a 298.74 kB / 92.65 kB
 * entry plus a 163.32 kB / 53.27 kB react-vendor chunk, with the rest arriving only if asked for.
 *
 * WHAT IS STILL EAGER, AND WHY. The matchday workspace and the two dated routes that resolve to
 * it. That is the destination this product is built around; making it lazy would buy a smaller
 * entry chunk at the price of a second serial round trip before any football appears, which is
 * the wrong trade on exactly the connection this work is for. `NotFoundPage` is eager because it
 * is a handful of lines and it is what a broken link lands on.
 *
 * EVERYTHING ELSE IS `lazy()`. Nothing about the URLs changed: every route resolves to the same
 * page it did before, at the same path, and the loading state below is what the reader sees in
 * the gap.
 */
import MatchesPage from '@/pages/MatchesPage'
import TodayPredictionsPage from '@/pages/TodayPredictionsPage'
import TomorrowPredictionsPage from '@/pages/TomorrowPredictionsPage'
import NotFoundPage from '@/pages/NotFoundPage'

const HomePage = lazy(() => import('@/pages/HomePage'))
const MatchDetailPage = lazy(() => import('@/pages/MatchDetailPage'))
const LeaguesPage = lazy(() => import('@/pages/LeaguesPage'))
const LeagueDetailPage = lazy(() => import('@/pages/LeagueDetailPage'))
const TeamDetailPage = lazy(() => import('@/pages/TeamDetailPage'))
const LoginPage = lazy(() => import('@/pages/LoginPage'))
const RegisterPage = lazy(() => import('@/pages/RegisterPage'))
const ForgotPasswordPage = lazy(() => import('@/pages/ForgotPasswordPage'))
const ResetPasswordPage = lazy(() => import('@/pages/ResetPasswordPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const ProfilePage = lazy(() => import('@/pages/ProfilePage'))
const PasswordChangePage = lazy(() => import('@/pages/PasswordChangePage'))
const SubscriptionPage = lazy(() => import('@/pages/SubscriptionPage'))
const APITestPage = lazy(() => import('@/pages/APITestPage'))
const DebugAPIPage = lazy(() => import('@/pages/DebugAPIPage'))
const ExpertDashboardPage = lazy(() => import('@/pages/ExpertDashboardPage'))
const ExpertCreatePredictionPage = lazy(() => import('@/pages/ExpertCreatePredictionPage'))
const ExpertReviewQueuePage = lazy(() => import('@/pages/ExpertReviewQueuePage'))
const ExpertMyPredictionsPage = lazy(() => import('@/pages/ExpertMyPredictionsPage'))
const ExpertMatchSelectionPage = lazy(() => import('@/pages/ExpertMatchSelectionPage'))

/**
 * The gap between asking for a page and having its code.
 *
 * TWO WAYS THIS GOES WRONG, AND WHAT IS DONE ABOUT EACH.
 *
 * It flashes. On a cached chunk the wait is a few milliseconds, and a spinner that appears and
 * disappears inside one frame is worse than no spinner: it reads as a fault. So nothing is drawn
 * for the first 250 ms — an empty block of roughly the height the page will occupy, which also
 * keeps the scroll position from jumping — and only a wait longer than that gets words.
 *
 * It lies. A skeleton shaped like fixture rows would be this application drawing matches that do
 * not exist yet, which is the one thing it is not allowed to do. So the honest wait says what is
 * actually happening — the page is still arriving — and claims nothing about what will be in it.
 */
const RouteLoading: React.FC<{ t: TranslateFn }> = ({ t }) => {
  const [longEnoughToSay, setLongEnoughToSay] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => setLongEnoughToSay(true), 250)
    return () => window.clearTimeout(timer)
  }, [])

  return (
    <div className="mx-auto min-h-[60vh] max-w-5xl px-3 py-6 sm:px-6 lg:px-8" data-testid="route-loading">
      {longEnoughToSay && (
        <p role="status" aria-live="polite" className="text-sm text-secondary-400">
          {t('route.loading')}
        </p>
      )}
    </div>
  )
}

/**
 * What happens when a chunk does not arrive.
 *
 * Splitting the bundle introduces a failure that did not exist when everything shipped in one
 * file: a dropped connection, or a deploy that replaced the file this tab was told to ask for,
 * now means a route whose code cannot be fetched. Unhandled, React unmounts the tree and the
 * reader gets a blank page.
 *
 * WHY THE TWO MESSAGES ARE NOT ONE. A boundary around a route catches everything that route
 * throws, not only a failed download, and the two are different facts: one is "your connection
 * did not deliver this", which a reload genuinely fixes, and the other is "this page broke", which
 * a reload may not. Telling a reader on a dropped connection that the page is broken, or a reader
 * looking at a bug that their connection failed, are both this application saying something it
 * does not know. So the error is read, and the sentence matches it.
 *
 * Neither message says anything about the data. Nothing rendered, so there is nothing to describe
 * as fresh, stale or stored — and the freshness block that would have said so is part of the page
 * that never arrived.
 */
type RouteFailure = 'not-downloaded' | 'failed-to-render'

/**
 * `t` arrives as a prop rather than from a hook: this is a class component, because an error
 * boundary has to be one, and a class cannot subscribe to a context change on its own. `Routed`
 * below reads the context and hands the translator down, so a language change repaints the
 * error message along with everything else.
 */
interface RouteBoundaryProps { children: React.ReactNode; at: string; t: TranslateFn }
interface RouteBoundaryState { failure: RouteFailure | null; at: string }

/** What a browser says when a dynamic import does not arrive. Each engine phrases it differently. */
const NOT_DOWNLOADED = /dynamically imported module|Importing a module script failed|error loading dynamically imported module|ChunkLoadError|Loading chunk .* failed/i

/**
 * WHY THE BOUNDARY IS TOLD WHICH PATH IT IS GUARDING.
 *
 * React Router renders every route in this layout at the same position in the tree, so React
 * reconciles one `RouteBoundary` instance across a navigation rather than mounting a new one.
 * Without `at`, a single failed chunk therefore latched: measured on a production build, aborting
 * the `/leagues` chunk and then clicking Home left the error on screen at `/`, and at every other
 * lazily loaded route after that — the whole navigation dead until a full reload. On the
 * connection this split was made for, one dropped chunk is likely, not hypothetical, so a failure
 * that survives leaving the page is the worse bug of the two.
 *
 * Changing path clears the failure. Staying on the same path does not: `React.lazy` caches a
 * rejected import, so re-entering the route that failed would re-throw the same error with no
 * second request, and the reader is better served by the Reload button already in front of them.
 */
class RouteBoundary extends React.Component<RouteBoundaryProps, RouteBoundaryState> {
  state: RouteBoundaryState = { failure: null, at: this.props.at }

  static getDerivedStateFromProps(
    props: RouteBoundaryProps,
    state: RouteBoundaryState,
  ): RouteBoundaryState | null {
    return props.at === state.at ? null : { failure: null, at: props.at }
  }

  static getDerivedStateFromError(error: unknown): Pick<RouteBoundaryState, 'failure'> {
    const described = error instanceof Error ? `${error.name}: ${error.message}` : String(error)
    return { failure: NOT_DOWNLOADED.test(described) ? 'not-downloaded' : 'failed-to-render' }
  }

  componentDidCatch(error: unknown): void {
    console.error('Route boundary caught:', error)
  }

  render(): React.ReactNode {
    const { failure } = this.state
    if (!failure) return this.props.children

    const notDownloaded = failure === 'not-downloaded'
    const { t } = this.props
    return (
      <div className="mx-auto max-w-5xl px-3 py-10 sm:px-6 lg:px-8" data-testid="route-error" data-failure={failure}>
        <h1 className="text-lg font-semibold text-white">
          {t(notDownloaded ? 'route.notDownloadedTitle' : 'route.failedTitle')}
        </h1>
        <p className="mt-2 text-sm text-secondary-300">
          {t(notDownloaded ? 'route.notDownloadedBody' : 'route.failedBody')}
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="focus-ring mt-4 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700"
        >
          {t('route.reload')}
        </button>
      </div>
    )
  }
}

/**
 * Wrap one routed page.
 *
 * The boundary and the wait sit INSIDE the route element rather than around `<Routes>`, so the
 * header, the status banner and the footer stay on screen while a page arrives. Suspending the
 * whole router would take the navigation away from the reader at the exact moment they are using
 * it — and leaving the navigation on screen is only worth anything if using it actually works,
 * which is what `useLocation` here is for: see the note on `RouteBoundary`.
 */
const Routed: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { pathname } = useLocation()
  const t = useT()
  return (
    <RouteBoundary at={pathname} t={t}>
      <Suspense fallback={<RouteLoading t={t} />}>{children}</Suspense>
    </RouteBoundary>
  )
}

const routed = (element: React.ReactNode): React.ReactElement => <Routed>{element}</Routed>

function App() {
  const t = useT()
  return (
    <>
      {/*
        The document's own language, and the default title. `htmlAttributes` is how the <html>
        lang attribute gets set on a page react-helmet-async owns; src/i18n also sets it directly
        at boot, before React renders, so assistive technology is never handed the wrong language
        for the first frame.
      */}
      <Helmet htmlAttributes={{ lang: t('app.htmlLang') }}>
        <title>{t('app.defaultTitle')}</title>
        <meta name="description" content={t('app.defaultDescription')} />
      </Helmet>

      <Routes>
        <Route path="/" element={<Layout />}>
          {/* Public routes */}
          <Route index element={routed(<HomePage />)} />
          {/* The matchday workspace. `/matches` takes ?date=; the two older routes name their own
              day and resolve to the same page, so every existing link and bookmark keeps working. */}
          <Route path="matches" element={<MatchesPage />} />
          <Route path="predictions">
            <Route path="today" element={<TodayPredictionsPage />} />
            <Route path="tomorrow" element={<TomorrowPredictionsPage />} />
          </Route>
          <Route path="match/:id" element={routed(<MatchDetailPage />)} />
          <Route path="leagues" element={routed(<LeaguesPage />)} />
          <Route path="league/:id" element={routed(<LeagueDetailPage />)} />
          <Route path="leagues/:leagueId" element={routed(<LeagueDetailPage />)} />
          <Route path="teams/:teamId" element={routed(<TeamDetailPage />)} />

          {/* Protected routes - require authentication */}
          <Route
            path="dashboard"
            element={
              <ProtectedRoute>
                {routed(<DashboardPage />)}
              </ProtectedRoute>
            }
          />
          <Route
            path="profile"
            element={
              <ProtectedRoute>
                {routed(<ProfilePage />)}
              </ProtectedRoute>
            }
          />
          <Route
            path="password-change"
            element={
              <ProtectedRoute>
                {routed(<PasswordChangePage />)}
              </ProtectedRoute>
            }
          />
          <Route
            path="subscription"
            element={
              <ProtectedRoute>
                {routed(<SubscriptionPage />)}
              </ProtectedRoute>
            }
          />

          {/* Expert routes - protected for expert users only */}
          <Route
            path="expert/dashboard"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                {routed(<ExpertDashboardPage />)}
              </ProtectedRoute>
            }
          />
          <Route
            path="expert/match-selection"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                {routed(<ExpertMatchSelectionPage />)}
              </ProtectedRoute>
            }
          />
          <Route
            path="expert/predictions/create"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                {routed(<ExpertCreatePredictionPage />)}
              </ProtectedRoute>
            }
          />
          <Route
            path="expert/predictions/review-queue"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                {routed(<ExpertReviewQueuePage />)}
              </ProtectedRoute>
            }
          />
          <Route
            path="expert/predictions/my-predictions"
            element={
              <ProtectedRoute allowedRoles={['EXPERT', 'ADMIN']}>
                {routed(<ExpertMyPredictionsPage />)}
              </ProtectedRoute>
            }
          />

          {/* Debug routes - protected for development */}
          <Route
            path="api-test"
            element={
              <ProtectedRoute>
                {routed(<APITestPage />)}
              </ProtectedRoute>
            }
          />
          <Route
            path="debug-api"
            element={
              <ProtectedRoute>
                {routed(<DebugAPIPage />)}
              </ProtectedRoute>
            }
          />
        </Route>

        {/* Auth routes without layout */}
        <Route path="/login" element={routed(<LoginPage />)} />
        <Route path="/register" element={routed(<RegisterPage />)} />
        <Route path="/forgot-password" element={routed(<ForgotPasswordPage />)} />
        <Route path="/reset-password" element={routed(<ResetPasswordPage />)} />

        {/* 404 page */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  )
}

export default App
