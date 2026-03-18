#!/usr/bin/env bash
# Очистка всех таблиц во всех БД. Запуск из корня: bash scripts/drop_all_databases.sh
# После выполнения: docker compose restart auth tickets notifications inventory attendance todos time_tracking gateway

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/.."

run_sql() {
  echo "=== $1 ($3) ==="
  cat "$DIR/$4" | docker compose exec -T "$1" psql -U "$2" -d "$3"
}

run_sql users_db gateway kosta_users drop_users_db_tables.sql
run_sql tickets_db tickets kosta_tickets drop_tickets_db_tables.sql
run_sql notifications_db notifications kosta_notifications drop_notifications_db_tables.sql
run_sql inventory_db inventory kosta_inventory drop_inventory_db_tables.sql
run_sql attendance_db attendance kosta_attendance drop_attendance_db_tables.sql
run_sql todos_db todos kosta_todos drop_todos_db_tables.sql
run_sql time_tracking_db time_tracking kosta_time_tracking drop_time_tracking_db_tables.sql

echo "Done. Restart: docker compose restart auth tickets notifications inventory attendance todos time_tracking gateway"
