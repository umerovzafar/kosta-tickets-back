-- Kanban-доска пользователя (сервис todos). Таблицы создаются также через SQLAlchemy create_all при старте.

CREATE TABLE IF NOT EXISTS todo_boards (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    background_url TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_todo_boards_user_id ON todo_boards (user_id);

CREATE TABLE IF NOT EXISTS todo_board_columns (
    id SERIAL PRIMARY KEY,
    board_id INTEGER NOT NULL REFERENCES todo_boards (id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    position INTEGER NOT NULL,
    color VARCHAR(32) NOT NULL DEFAULT '#6b7280',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_todo_board_columns_board_id ON todo_board_columns (board_id);

CREATE TABLE IF NOT EXISTS todo_board_cards (
    id SERIAL PRIMARY KEY,
    column_id INTEGER NOT NULL REFERENCES todo_board_columns (id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    body TEXT,
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_todo_board_cards_column_id ON todo_board_cards (column_id);
