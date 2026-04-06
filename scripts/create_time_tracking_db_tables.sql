-- Схема БД сервиса time_tracking (PostgreSQL).
-- При старте приложения таблицы также создаются через SQLAlchemy create_all.
-- Этот скрипт — для ручного развёртывания / документации. См. docs/TIME_TRACKING_HOURLY_RATES.md

CREATE TABLE IF NOT EXISTS time_tracking_users (
    id SERIAL PRIMARY KEY,
    auth_user_id INTEGER NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    picture TEXT,
    role VARCHAR(100) NOT NULL DEFAULT '',
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS time_tracking_user_hourly_rates (
    id VARCHAR(36) PRIMARY KEY,
    auth_user_id INTEGER NOT NULL REFERENCES time_tracking_users (auth_user_id) ON DELETE CASCADE,
    rate_kind VARCHAR(20) NOT NULL,
    amount NUMERIC(18, 4) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    valid_from DATE,
    valid_to DATE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_tt_hourly_rates_user_kind
    ON time_tracking_user_hourly_rates (auth_user_id, rate_kind);
