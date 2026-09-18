# Soccer Predictions Frontend

A React 18 / TypeScript / Vite single-page app for the Soccer Predictions Platform. It renders
fixtures, model forecasts and expert predictions served by the FastAPI backend, and provides the
authentication, expert publishing and account screens.

> **What this document is.** Everything below is checked against the code in this directory. Where a
> property has not been measured, it says so instead of claiming a number. Nothing here should be
> read as a production-readiness statement — see [Status](#status).

## Status

| Claim | State |
|---|---|
| `npm run type-check`, `npm run lint`, `npm run build` | Green. `lint` runs with `--max-warnings 0`, so it fails on a single warning |
| Playwright suite (`npm run e2e`) | Green at the last recorded run (2026-09-18). No count is quoted here on purpose — specs are still being added, so a number written into a README goes stale; run the command and read what it prints. Needs the local stack running |
| Unit/component tests | **None.** There is no Vitest/Jest setup in this package |
| Lighthouse / Core Web Vitals | **Never measured.** No audit has been run and no score is claimed |
| WCAG / accessibility conformance | **Never audited.** Components use semantic elements and some ARIA attributes, but no conformance level has been tested or claimed |
| Route-level code splitting / lazy loading | **Not implemented.** Every page in `src/App.tsx` is a static top-level `import`; there is no `React.lazy` or `<Suspense>` anywhere in the app. `npm run build` confirms it: the whole app emits as **one 680 kB JS chunk** (189 kB gzipped) and Vite prints its own "chunks are larger than 500 kB" warning. Route-level splitting is a *target*, not a current property |
| PWA / service worker | **Not implemented.** No manifest, no service worker, no `vite-plugin-pwa` |
| Production readiness | Not claimed. The app has never been deployed against the current backend; see the root `README.md` deployment section |

## Tech stack

| Concern | What is used | Notes |
|---|---|---|
| Framework | React 18 + TypeScript | |
| Build | Vite | `vite.config.ts`; `base: './'`, source maps disabled in production builds |
| Styling | Tailwind CSS, dark theme | `tailwind.config.js` |
| Routing | React Router DOM v6 | all routes declared in `src/App.tsx` |
| HTTP | Axios | `src/services/api-client.ts` |
| Auth state | React context | `src/contexts/AuthContext.tsx`, `src/hooks/useAuth.ts` |
| Icons | Heroicons | |
| Animation | Framer Motion | used on the home and predictions pages |
| Head/SEO tags | React Helmet Async | |
| Notifications | React Hot Toast | |
| Dialog/menu primitives | Headless UI | used in `src/components/layout/Header.tsx` |
| E2E tests | Playwright | `playwright.config.ts`, specs in `e2e/` |

Two dependencies are declared in `package.json` but are **not used by any source file**, so do not
assume they describe behaviour:

- `recharts` — no import anywhere in `src/`.
- `react-query` — `QueryClientProvider` is mounted in `src/main.tsx`, but there is no `useQuery` or
  `useMutation` in the app. Data fetching goes through the service modules and Axios.

## Install and run

```bash
cd frontend
npm install
cp .env.example .env     # defaults work against a local backend
npm run dev              # http://localhost:3000
```

The dev server port is `3000` (`vite.config.ts` and the `dev` script). Override it with
`npx vite --port 3100 --strictPort` when 3000 is taken.

The backend must be running for real data; see the root `README.md` for the backend and Docker
steps.

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Vite dev server on port 3000 |
| `npm run build` | `tsc` then `vite build` into `dist/` |
| `npm run preview` | Serve the built `dist/` |
| `npm run type-check` | `tsc --noEmit` |
| `npm run lint` | ESLint, `--max-warnings 0` |
| `npm run lint:fix` | ESLint with `--fix` |
| `npm run e2e` | Every Playwright project |
| `npm run e2e:mocked` | The deterministic mocked desktop + mobile projects |
| `npm run e2e:live` | The expert publishing flow against the local backend |
| `npm run e2e:report` | Open the last Playwright HTML report |

`e2e:mocked` stubs every backend call from the captured payloads in `e2e/fixtures/`, so it spends no
provider allowance. `e2e:live` needs the local stack running and creates only its own clearly-marked
QA records.

## Project structure

```
frontend/
├── e2e/                  # Playwright
│   ├── fixtures/        # captured, sanitised backend payloads
│   ├── live/            # specs that run against the local backend
│   ├── mocked/          # deterministic specs, every backend call stubbed
│   └── support/         # helpers and shared setup
├── public/
│   ├── leagues/         # league crest assets
│   └── teams/           # team crest assets
├── src/
│   ├── components/
│   │   ├── layout/      # Header, Footer, Layout, SearchDropdown
│   │   ├── ui/          # Card, Button, Badge, MatchCard, provider/forecast notices,
│   │   │                # and the probability/market/forecast-status helpers
│   │   ├── ProtectedRoute.tsx
│   │   └── PredictionSourceBadge.tsx
│   ├── contexts/        # AuthContext
│   ├── hooks/           # useAuth
│   ├── pages/           # one component per route, all imported eagerly by App.tsx
│   ├── services/        # API clients and mappers (see below)
│   ├── types/           # auth.ts, expert.ts, index.ts
│   ├── utils/           # errors, matchFilters, predictionLabels
│   ├── App.tsx          # route table
│   ├── main.tsx         # providers and mount
│   └── index.css
├── playwright.config.ts
├── vite.config.ts
└── package.json
```

There is no `src/data/` directory and no mock data. `src/data/mockData.ts` was **deleted**: it held
a hard-coded user record and a `Math.random()` prediction generator that were being bundled into the
production app. The `@data/*` alias is gone from `vite.config.ts`; a stale `@data/*` entry remains in
`tsconfig.json` and resolves to nothing.

There is no `src/assets/` directory either — images live in `public/`.

## Backend integration

There is no `src/services/api.ts`. The HTTP layer is `src/services/api-client.ts`, and it reads Vite
environment variables through `import.meta.env`, **not** `process.env` (`process.env` is not defined
in a Vite browser bundle):

```ts
// src/services/api-client.ts
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const API_TIMEOUT = parseInt(import.meta.env.VITE_API_TIMEOUT || '30000', 10);
```

The data source is selected at runtime by `VITE_DATA_SOURCE`
(`src/services/match-data-source.ts`):

- `backend` (default) — fixtures, forecasts, leagues and teams come from the FastAPI backend
  (`backend-match-data.service.ts`). Provider credentials stay on the server.
- `api-football` — the retained legacy path that calls API-Football from the browser through the
  Vite **dev-server** proxy (`/api/football` in `vite.config.ts`). That proxy exists only while
  `vite dev` is running, so this data source does not work in a production build.

### Environment variables

`.env.example` is the authoritative list. The ones that matter:

```bash
VITE_API_BASE_URL=http://localhost:8000   # FastAPI backend
VITE_API_TIMEOUT=30000
VITE_DATA_SOURCE=backend                  # backend | api-football
API_FOOTBALL_KEY=                         # NO VITE_ prefix: dev-server proxy only
```

Never set `VITE_API_FOOTBALL_KEY`. Any `VITE_`-prefixed value is embedded verbatim in the public
bundle and shipped to every visitor.

### Authentication

JWT access and refresh tokens are handled in `src/services/auth.service.ts` and
`src/contexts/AuthContext.tsx`; `src/components/ProtectedRoute.tsx` guards the authenticated routes.
Axios interceptors in `api-client.ts` attach the access token and handle refresh.

## Design system

### Colours

Six extended colour families are defined in `tailwind.config.js`, each as a full 50-950 scale. The
`500` step of each:

| Family | `500` | Used for |
|---|---|---|
| `primary` | `#0ea5e9` (sky blue) | primary actions and links |
| `secondary` | `#64748b` (slate) | secondary surfaces and text |
| `success` | `#22c55e` (green) | positive states |
| `warning` | `#f59e0b` (amber) | cautions |
| `danger` | `#ef4444` (red) | errors and destructive actions |
| `dark` | `#64748b` | the dark-theme surface scale (`dark.800` `#1e293b`, `dark.900` `#0f172a`) |

`darkMode: 'class'`. `tailwind.config.js` is authoritative; do not hard-code hex values in
components.

### Typography

Inter, with a `system-ui, sans-serif` fallback stack (`theme.extend.fontFamily.sans`).

## Responsive design

Tailwind's default breakpoints, mobile-first. The Playwright `mocked-mobile` project runs the whole
mocked suite at iPhone 13 dimensions, so mobile rendering is exercised on every run. No specific
device matrix beyond that is claimed.

## Known gaps

- No unit or component test setup (Playwright is the only automated coverage).
- No route-level code splitting: `npm run build` emits a single ~680 kB JS chunk (189 kB gzipped)
  and Vite warns about it on every build. `React.lazy` on the route components in `App.tsx` is the
  fix.
- No Lighthouse, Core Web Vitals or accessibility audit has been run.
- `recharts` and `react-query` are installed but unused; both could be removed.
- The `@data/*` path alias in `tsconfig.json` points at a directory that no longer exists.

## Contributing

1. Create a feature branch.
2. Make your changes.
3. Run `npm run type-check`, `npm run lint`, `npm run build` and `npm run e2e:mocked`.
4. Open a pull request.

Do not disable a lint rule or raise the `--max-warnings` threshold to make the gate pass.

## License

No `LICENSE` file exists in this repository, so no licence is currently granted. Earlier revisions of
this file claimed MIT; that was not backed by a licence file. Ask the owner before reusing this code.
