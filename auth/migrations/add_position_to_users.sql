-- Добавить колонку должности (position) в таблицу users.
-- Выполнить при обновлении с версии без поля position.
-- Для новой установки не требуется (схема создаётся из моделей).

ALTER TABLE users ADD COLUMN IF NOT EXISTS position VARCHAR(256) NULL;
