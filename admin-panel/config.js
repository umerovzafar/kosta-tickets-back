// База API gateway.
// Пустая строка: запросы на тот же origin, что и страница (прод: https://ticketsback.kostalegal.com).
// Локально (Docker): админка на :8080, gateway на :1234 — см. app.js или явно задайте:
// window.ADMIN_API_BASE = 'http://localhost:1234';
window.ADMIN_API_BASE = '';
