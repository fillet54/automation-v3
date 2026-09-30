-- Application schema. Applied on every startup, so every statement
-- must be idempotent. There are no migrations: if a table changes
-- shape, delete the database and reload it.

-- Requirements
CREATE TABLE IF NOT EXISTS requirements(
    id TEXT PRIMARY KEY,
    text TEXT,
    subsystem TEXT
);

-- Job queue workers
CREATE TABLE IF NOT EXISTS workers(
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'available',
    last_keepalive TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Editor
CREATE TABLE IF NOT EXISTS documents(
    id TEXT PRIMARY KEY,
    path TEXT,
    draft TEXT,
    mime TEXT NOT NULL,
    st_mtime REAL,
    meta TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editors(
    id INTEGER PRIMARY KEY,
    active_tab TEXT
);

CREATE TABLE IF NOT EXISTS opened_documents(
    id INTEGER PRIMARY KEY,
    editor_id INTEGER REFERENCES editors(id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS treeviews(
    id INTEGER PRIMARY KEY,
    opened TEXT,
    root TEXT,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE
);

-- Workspaces
CREATE TABLE IF NOT EXISTS workspaces(
    id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS workspace_editors(
    id INTEGER PRIMARY KEY,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    editor_id INTEGER REFERENCES editors(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workspace_treeviews(
    id INTEGER PRIMARY KEY,
    type TEXT,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    treeview_id INTEGER REFERENCES treeviews(id) ON DELETE CASCADE
);
