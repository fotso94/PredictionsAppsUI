/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly DEV: boolean
  readonly PROD: boolean
  readonly MODE: string
  /** INSECURE opt-in for local demos only; see api-football.service.ts */
  readonly VITE_API_FOOTBALL_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

