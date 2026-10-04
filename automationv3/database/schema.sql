-- Application schema. Applied on every startup, so every statement
-- must be idempotent. There are no migrations: if a table changes
-- shape, delete the database and reload it.

-- Requirements
CREATE TABLE IF NOT EXISTS requirements(
    id TEXT PRIMARY KEY,
    text TEXT,
    subsystem TEXT
);

-- Job queue workers. uut_types is a JSON list of the UUT plugins the
-- worker can install.
CREATE TABLE IF NOT EXISTS workers(
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'available',
    last_keepalive TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uut_types TEXT NOT NULL DEFAULT '[]'
);

-- Environments each worker hosts, with their current fingerprint
CREATE TABLE IF NOT EXISTS worker_environments(
    worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    fingerprint_hash TEXT NOT NULL,
    PRIMARY KEY(worker_id, name)
);

-- Job queue: pending and in-progress runs only. The id is the run's
-- uuidv7; a row is removed once its run.json has an outcome.
-- environment is NULL when the script declares none (any worker may run
-- it); uut_versions is JSON: uut name -> {"id", "digest"}.
CREATE TABLE IF NOT EXISTS jobs(
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    script TEXT NOT NULL,
    environment TEXT,
    uut_versions TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    worker_url TEXT,
    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at TEXT
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

-- Workspaces
CREATE TABLE IF NOT EXISTS workspaces(
    id TEXT PRIMARY KEY,
    editor_id INTEGER NOT NULL REFERENCES editors(id)
);

CREATE TABLE IF NOT EXISTS expanded_nodes(
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    PRIMARY KEY(workspace_id, path)
);
