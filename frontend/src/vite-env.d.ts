/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly DEV: boolean
  readonly PROD: boolean
  readonly MODE: string
  /** Backend API origin (default http://localhost:8000) */
  readonly VITE_API_BASE_URL?: string
  readonly VITE_API_TIMEOUT?: string
  /**
   * Where fixtures/predictions come from:
   * - "backend" (default): the FastAPI match endpoints (Live Score API + GameForecastAPI, with retained fallbacks)
   * - "api-football": the legacy browser-side API-Football path (retained integration)
   */
  readonly VITE_DATA_SOURCE?: 'backend' | 'api-football'
  /** "true" re-enables the old randomized placeholder predictions/odds in the legacy path. Never set in production. */
  readonly VITE_ALLOW_FAKE_PREDICTIONS?: string
  /** INSECURE opt-in for local demos only; see api-football.service.ts */
  readonly VITE_API_FOOTBALL_KEY?: string
  /** TheSportsDB key for the retained browser-side fallback services (thesportsdb*.service.ts) */
  readonly VITE_THESPORTSDB_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
