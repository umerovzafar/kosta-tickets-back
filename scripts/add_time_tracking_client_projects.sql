-- Проекты клиента time manager (идемпотентно; см. time_tracking schema_patches).

CREATE TABLE IF NOT EXISTS time_tracking_client_projects (
    id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES time_tracking_clients (id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    code VARCHAR(64),
    start_date DATE,
    end_date DATE,
    notes TEXT,
    report_visibility VARCHAR(32) NOT NULL DEFAULT 'managers_only',
    project_type VARCHAR(32) NOT NULL DEFAULT 'time_and_materials',
    billable_rate_type VARCHAR(64),
    budget_type VARCHAR(64),
    budget_amount NUMERIC(18, 4),
    budget_hours NUMERIC(12, 2),
    budget_resets_every_month BOOLEAN NOT NULL DEFAULT FALSE,
    budget_includes_expenses BOOLEAN NOT NULL DEFAULT FALSE,
    send_budget_alerts BOOLEAN NOT NULL DEFAULT FALSE,
    budget_alert_threshold_percent NUMERIC(8, 2),
    fixed_fee_amount NUMERIC(18, 4),
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_tt_client_projects_client
    ON time_tracking_client_projects (client_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tt_client_project_code
    ON time_tracking_client_projects (client_id, lower(trim(code)))
    WHERE code IS NOT NULL AND trim(code) <> '';
