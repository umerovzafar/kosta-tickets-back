// База URL gateway (FastAPI). Пустая строка — авто в app.js:
// - порт 8080/8081 → тот же хост, порт 1234 (или ADMIN_GATEWAY_PORT);
// - иначе тот же origin (прод с nginx и proxy /api).
// Явно, если gateway на другом хосте/порту:
// window.ADMIN_API_BASE = 'http://192.168.1.10:1234';
// window.ADMIN_GATEWAY_PORT = '1234';
window.ADMIN_API_BASE = '';
