-- Kanban-доска пользователя (сервис todos). Таблицы создаются также через SQLAlchemy create_all при старте.

CREATE TABLE IF NOT EXISTS todo_boards (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    background_url TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_todo_boards_user_id ON todo_boards (user_id);

CREATE TABLE IF NOT EXISTS todo_board_labels (
    id SERIAL PRIMARY KEY,
    board_id INTEGER NOT NULL REFERENCES todo_boards (id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    color VARCHAR(32) NOT NULL DEFAULT '#6b7280',
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_todo_board_labels_board_id ON todo_board_labels (board_id);

CREATE TABLE IF NOT EXISTS todo_board_columns (
    id SERIAL PRIMARY KEY,
    board_id INTEGER NOT NULL REFERENCES todo_boards (id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    position INTEGER NOT NULL,
    color VARCHAR(32) NOT NULL DEFAULT '#6b7280',
    is_collapsed BOOLEAN NOT NULL DEFAULT FALSE,
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
    due_at TIMESTAMPTZ,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_todo_board_cards_column_id ON todo_board_cards (column_id);

CREATE TABLE IF NOT EXISTS todo_card_labels (
    card_id INTEGER NOT NULL REFERENCES todo_board_cards (id) ON DELETE CASCADE,
    label_id INTEGER NOT NULL REFERENCES todo_board_labels (id) ON DELETE CASCADE,
    PRIMARY KEY (card_id, label_id)
);

CREATE TABLE IF NOT EXISTS todo_card_checklist_items (
    id SERIAL PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES todo_board_cards (id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    is_done BOOLEAN NOT NULL DEFAULT FALSE,
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_todo_card_checklist_items_card_id ON todo_card_checklist_items (card_id);

CREATE TABLE IF NOT EXISTS todo_card_participants (
    card_id INTEGER NOT NULL REFERENCES todo_board_cards (id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (card_id, user_id)
);

CREATE TABLE IF NOT EXISTS todo_card_attachments (
    id SERIAL PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES todo_board_cards (id) ON DELETE CASCADE,
    storage_key VARCHAR(1024) NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    mime_type VARCHAR(200),
    size_bytes INTEGER NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_todo_card_attachments_card_id ON todo_card_attachments (card_id);

CREATE TABLE IF NOT EXISTS todo_card_comments (
    id SERIAL PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES todo_board_cards (id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_todo_card_comments_card_id ON todo_card_comments (card_id);
