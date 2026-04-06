-- Существующая БД kosta_time_tracking: добавить ёмкость и таблицу записей времени.
-- Выполнить один раз (psql, DBeaver, Portainer exec).

ALTER TABLE time_tracking_users
    ADD COLUMN IF NOT EXISTS weekly_capacity_hours NUMERIC(10, 2) NOT NULL DEFAULT 35;

CREATE TABLE IF NOT EXISTS time_tracking_entries (
    id VARCHAR(36) PRIMARY KEY,
    auth_user_id INTEGER NOT NULL REFERENCES time_tracking_users (auth_user_id) ON DELETE CASCADE,
    work_date DATE NOT NULL,
    hours NUMERIC(12, 2) NOT NULL,
    is_billable BOOLEAN NOT NULL DEFAULT TRUE,
    project_id VARCHAR(36),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_tt_entries_user_date ON time_tracking_entries (auth_user_id, work_date);
