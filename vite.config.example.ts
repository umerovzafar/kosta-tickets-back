/**
 * Пример для SPA (Vite): проксирование /api на gateway.
 * Скопируйте фрагмент server.proxy в свой vite.config.ts или используйте как есть.
 *
 * Без прокси: в .env.development задайте VITE_API_URL=http://127.0.0.1:1234
 * и в клиенте собирайте URL как `${import.meta.env.VITE_API_URL}/api/v1/...`.
 */
import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:1234',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
