#!/usr/bin/env bash
# Мок-данные Time Tracking — запуск из корня приложения (в Docker: cd /app)
#
#   chmod +x run_mock_data.sh    # один раз
#   ./run_mock_data.sh --help
#   ./run_mock_data.sh seed --weeks 8
#   ./run_mock_data.sh delete --apply
#   ./run_mock_data.sh reset --weeks 10
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${HERE}${PYTHONPATH:+:$PYTHONPATH}"
cd "$HERE"
exec python "$HERE/scripts/tt_mock_data.py" "$@"
