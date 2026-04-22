#!/usr/bin/env bash
# Сид мок-данных (клиенты, проекты, время, почасовые ставки по валютам, расходы в БД expenses).
# Из корня приложения time tracking, например: cd /app
#
#   ./scripts/seed_mock_data.sh
#   ./scripts/seed_mock_data.sh --skip-expenses
#   ./scripts/seed_mock_data.sh --uzs-per-usd 12850 --no-exchange-table
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$HERE/.." && pwd)"
cd "$APP_ROOT"
export PYTHONPATH="${APP_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
exec python "$HERE/seed_mock_data.py" "$@"
