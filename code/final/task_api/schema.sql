CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 2000),
    status TEXT NOT NULL DEFAULT 'todo'
        CHECK (status IN ('todo', 'in_progress', 'done')),
    priority TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('low', 'medium', 'high')),
    due_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks(status);
CREATE INDEX IF NOT EXISTS tasks_priority_idx ON tasks(priority);
CREATE INDEX IF NOT EXISTS tasks_due_date_idx ON tasks(due_date);

PRAGMA user_version = 1;

