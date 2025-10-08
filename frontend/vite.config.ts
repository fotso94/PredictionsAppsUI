import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
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
          proxy.on('proxyReq', (proxyReq, req, _res) => {
            // Add API key header
            proxyReq.setHeader('x-apisports-key', '38164887e0ce0b93419671e273fe64c0');
            // Remove other headers
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
})
