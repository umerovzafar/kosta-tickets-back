-- Сброс таблиц сервиса auth для пересоздания с актуальной схемой.
-- Выполнить один раз (например: psql -U user -d dbname -f auth/migrations/drop_auth_tables_for_recreate.sql),
-- затем перезапустить контейнер/сервис auth — таблицы создадутся заново с полями position, ms_graph_* и т.д.

DROP TABLE IF EXISTS role_permissions CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS roles CASCADE;
