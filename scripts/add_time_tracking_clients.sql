-- Клиенты time manager (биллинг). Применяется автоматически при старте time_tracking; можно выполнить вручную.
-- БД: та же, что и для time_tracking (kosta_time_tracking).

CREATE TABLE IF NOT EXISTS time_tracking_clients (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    address TEXT,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    invoice_due_mode VARCHAR(50) NOT NULL DEFAULT 'custom',
    invoice_due_days_after_issue INTEGER,
    tax_percent NUMERIC(8, 4),
    tax2_percent NUMERIC(8, 4),
    discount_percent NUMERIC(8, 4),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_tt_clients_name ON time_tracking_clients (name);
