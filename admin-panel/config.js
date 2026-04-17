// База URL gateway (FastAPI). Пустая строка — авто в app.js (см. docs/ADMIN_PANEL.md).
// Авто: localhost:8080/8081 → тот же хост :1234; частные IP (192.168.x и т.д.) → тот же хост :1234.
// Явно, если gateway на другом хосте или нестандартном порту:
// window.ADMIN_API_BASE = 'http://192.168.230.142:1234';
// window.ADMIN_GATEWAY_PORT = '1234';
window.ADMIN_API_BASE = '';
