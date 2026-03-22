import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://backend:8080',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://backend:8080',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://backend:8080',
        changeOrigin: true,
        ws: true,
      },
      '/docs': {
        target: 'http://backend:8080',
        changeOrigin: true,
      },
      '/redoc': {
        target: 'http://backend:8080',
        changeOrigin: true,
      },
      '/openapi.json': {
        target: 'http://backend:8080',
        changeOrigin: true,
      },
    },
  },
});
