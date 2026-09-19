import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load frontend/.env* for use inside this config only. Variables WITHOUT the VITE_ prefix
  // are never exposed to the browser bundle, which is exactly what we want for API keys.
  const env = loadEnv(mode, process.cwd(), '')
  const apiFootballKey = process.env.API_FOOTBALL_KEY || env.API_FOOTBALL_KEY || ''

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': '/src',
        '@components': '/src/components',
        '@pages': '/src/pages',
        '@types': '/src/types',
        '@services': '/src/services',
        '@utils': '/src/utils',
        '@hooks': '/src/hooks',
        // '@data' removed with src/data/mockData.ts: it held a hard-coded user record and a
        // Math.random() prediction generator that were bundled into the production app.
      }
    },
    server: {
      port: 3000,
      host: true,
      proxy: {
        '/api/football': {
          target: 'https://v3.football.api-sports.io',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/football/, ''),
          configure: (proxy, _options) => {
            proxy.on('proxyReq', (proxyReq, _req, _res) => {
              // The API key is injected here, on the dev server, from API_FOOTBALL_KEY in
              // frontend/.env. Never hard-code it and never expose it to the browser.
              if (apiFootballKey) {
                proxyReq.setHeader('x-apisports-key', apiFootballKey);
              }
              proxyReq.removeHeader('origin');
              proxyReq.removeHeader('referer');
            });
          },
        },
      },
    },
    build: {
      outDir: 'dist',
      // Never in production: a published .map exposes the complete frontend source (~2.6 MB here)
      // to anyone who opens the site. Dev and preview builds keep them for debugging.
      sourcemap: mode !== 'production',
      rollupOptions: {
        output: {
          /**
           * One vendor chunk for the framework, separate from the application.
           *
           * React, React DOM and the router are the part of the download that does not change
           * when the application does. Keeping them in their own file means a reader who has
           * visited before re-downloads only what was actually edited after a deploy, instead of
           * the whole entry chunk again. The routes themselves are split by `lazy()` in
           * src/App.tsx; this only separates the libraries underneath them.
           *
           * Deliberately narrow. Everything else the shell needs — the HTTP client, the menu
           * primitives, the toast and helmet providers — is imported by the header and the
           * matchday workspace on the first screen, so giving it a chunk of its own would buy an
           * extra request and no fewer bytes.
           */
          manualChunks: {
            'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          },
        },
      },
    },
    /**
     * Absolute, not './'.
     *
     * With a relative base the entry script is written into index.html as `./assets/index-*.js`.
     * That resolves correctly for `/matches`, and nowhere deeper: served at `/predictions/today`
     * the browser asks for `/predictions/assets/index-*.js`, which does not exist. Measured on
     * the production build before this change — `/matches` 200, `/predictions/assets/index-*.js`
     * 404 — so every two-segment route (`/predictions/today`, `/expert/dashboard`, `/match/:id`,
     * `/leagues/:id`) served a blank page in a production build while working perfectly in dev.
     * index.html already refers to `/vite.svg` absolutely, so the file was half-committed to a
     * root-hosted app anyway, and AWS_PRODUCTION_DEPLOYMENT_PLAN.md puts the build in a bucket of
     * its own behind CloudFront — i.e. at the root.
     *
     * If this app is ever served from a sub-path instead, this is the line to change, and it must
     * change to that sub-path rather than back to './'.
     */
    base: '/'
  }
})
