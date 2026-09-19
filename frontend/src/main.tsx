import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from 'react-query'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './contexts/AuthContext'
import App from './App.tsx'
import './index.css'

/**
 * Defaults for react-query.
 *
 * READ THIS BEFORE ADDING THE FIRST `useQuery`. Nothing in src/ uses react-query yet — every fetch
 * in this application goes through the services in src/services and their own stores — so these
 * options currently configure a provider with no queries under it. They are set correctly anyway,
 * because the first person to add a query will inherit them silently.
 *
 * `refetchOnWindowFocus` was false, which is what "nothing on this page ever refreshes" looked
 * like in configuration. A reader who leaves the tab open and comes back should see the current
 * state of what they saved, so it is on, together with the same behaviour after a dropped
 * connection.
 *
 * THE ONE THING A NEW QUERY MUST NOT DO. Refetching on focus is only safe for endpoints that read
 * stored data. `GET /api/v1/matches` is declared `refresh: bool = Query(True)` on the backend, so
 * a query over the dated match lists that inherits these defaults would go to the fixtures
 * provider every time somebody alt-tabs — and the forecast provider's allowance is eight requests
 * a day. Pass `refresh=false` (see STORED_ONLY in src/services/match-data-source.ts), or set
 * `refetchOnWindowFocus: false` on that query.
 *
 * The refresh that is actually in force today lives in src/services/favourites.service.ts: it
 * re-reads the signed-in reader's saved and followed fixtures when the tab comes back, and polls
 * once a minute only while one of their matches is in play. Both read stored data only.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      // Focus does not mean "request again": a query refetches on focus only once its data is
      // stale, so returning to a tab twice in a minute costs one request, not two.
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <HelmetProvider>
        <BrowserRouter>
          <AuthProvider>
            <App />
            <Toaster
              position="top-right"
              toastOptions={{
                duration: 4000,
                style: {
                  background: '#1e293b',
                  color: '#ffffff',
                  border: '1px solid #475569',
                },
                success: {
                  iconTheme: {
                    primary: '#22c55e',
                    secondary: '#ffffff',
                  },
                },
                error: {
                  iconTheme: {
                    primary: '#ef4444',
                    secondary: '#ffffff',
                  },
                },
              }}
            />
          </AuthProvider>
        </BrowserRouter>
      </HelmetProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
