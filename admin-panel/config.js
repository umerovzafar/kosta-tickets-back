// База URL gateway (FastAPI). Пустая строка — авто в app.js (см. docs/ADMIN_PANEL.md).
// - страница с порта 8080 или 8081 → тот же хост, порт 1234 (или window.ADMIN_GATEWAY_PORT);
// - иначе тот же origin (прод: nginx проксирует /api на gateway).
// Явно, если gateway на другом хосте/порту:
// window.ADMIN_API_BASE = 'http://192.168.1.10:1234';
// window.ADMIN_GATEWAY_PORT = '1234';
window.ADMIN_API_BASE = '';
