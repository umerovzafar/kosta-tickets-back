-- Задачи по клиентам. Применяется при старте time_tracking; можно выполнить вручную.

CREATE TABLE IF NOT EXISTS time_tracking_client_tasks (
    id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES time_tracking_clients (id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    default_billable_rate NUMERIC(18, 4),
    billable_by_default BOOLEAN NOT NULL DEFAULT TRUE,
    common_for_future_projects BOOLEAN NOT NULL DEFAULT FALSE,
    add_to_existing_projects BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_tt_client_tasks_client ON time_tracking_client_tasks (client_id);
