-- Сброс таблиц модуля расходов (kosta_expenses).
-- Нужен, если раньше таблицы создались с неверными типами (например expense_requests.id INTEGER
-- вместо VARCHAR), из‑за чего при старте падает CREATE TABLE expense_status_history с ошибкой
-- «incompatible types: character varying and integer».
-- При старте контейнера expenses тот же сброс выполняется автоматически, если обнаружен integer id.
--
-- ВНИМАНИЕ: удаляются данные заявок, вложений, истории статусов и аудита.
-- Справочники (expense_types, expense_departments, expense_projects, exchange_rates) не трогаем —
-- при необходимости очистите их отдельно.
--
-- Выполнение (Portainer → Console у expenses_db, или psql с хоста):
--   psql -U expenses -d kosta_expenses -f expenses-db-reset.sql

BEGIN;

DROP TABLE IF EXISTS expense_attachments CASCADE;
DROP TABLE IF EXISTS expense_status_history CASCADE;
DROP TABLE IF EXISTS expense_audit_logs CASCADE;
DROP TABLE IF EXISTS expense_requests CASCADE;
DROP TABLE IF EXISTS expense_kl_sequence CASCADE;

COMMIT;

-- После этого перезапустите контейнер expenses — SQLAlchemy create_all создаст схему заново.
