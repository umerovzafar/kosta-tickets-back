/**
 * Пример для SPA (Vite) в репозитории tickets-front: скопируйте в vite.config.ts.
 *
 * Ошибка «http proxy error … ECONNREFUSED» значит: на целевом адресе нет gateway.
 * Локально поднимите API, например:
 *   docker compose up -d gateway todos todos_db
 * Для /api/v1/todos/calendar/* нужны gateway и сервис todos.
 *
 * Без локального gateway: в tickets-front/.env.development задайте
 *   VITE_PROXY_TARGET=https://ticketsback.kostalegal.com
 * (CORS на gateway уже разрешает localhost:5173).
 *
 * Альтернатива без прокси: VITE_API_URL=http://127.0.0.1:1234 и запросы на полный URL.
 */
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = (env.VITE_PROXY_TARGET || 'http://127.0.0.1:1234').replace(/\/$/, '');

  const apiProxy = {
    target,
    changeOrigin: true,
    secure: false,
    configure(proxy) {
      proxy.on('error', (err) => {
        const m = err instanceof Error ? err.message : String(err);
        console.warn(
          `[vite proxy] ${m}\n` +
            `  → Проверьте, что API доступен по ${target} (часто: docker compose up -d gateway todos todos_db в tickets-back).`,
        );
      });
    },
  };

  return {
    server: {
      proxy: {
        '/api': apiProxy,
      },
    },
  };
});
