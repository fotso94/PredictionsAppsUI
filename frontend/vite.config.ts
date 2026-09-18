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
        '@data': '/src/data',
        '@assets': '/src/assets'
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
      sourcemap: true
    },
    base: './'
  }
})
