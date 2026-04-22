#!/usr/bin/env bash
# Удаление мок-данных: time tracking + мок-заявки в БД expenses (как в delete_mock_data.py).
# Запуск из корня приложения time tracking, например: cd /app
#
#   ./scripts/delete_mock_data.sh              # сухой прогон (только подсчёт)
#   ./scripts/delete_mock_data.sh --apply      # фактическое удаление, включая expenses
#
# Требуется: DATABASE_URL или TIME_TRACKING_DATABASE_URL; для расходов — EXPENSES_DATABASE_URL
# (в Docker обычно уже в environment; иначе экспорт в shell или .env).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$HERE/.." && pwd)"
cd "$APP_ROOT"
export PYTHONPATH="${APP_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
exec python "$HERE/delete_mock_data.py" "$@"
