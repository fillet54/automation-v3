-- Application schema. Applied on every startup, so every statement
-- must be idempotent. There are no migrations: a column added to an
-- existing table is also listed in database.ADDED_COLUMNS; any other
-- change of shape means deleting the database and reloading it.

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
-- fingerprint_hash pins an identical rerun to workers whose environment
-- still has that fingerprint.
CREATE TABLE IF NOT EXISTS jobs(
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    script TEXT NOT NULL,
    environment TEXT,
    variation TEXT,
    uut_versions TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    worker_url TEXT,
    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at TEXT,
    fingerprint_hash TEXT
);

-- Requirement links: a derived index of the :req: references in each
-- workspace's scripts, refreshed from files whose mtime changed
CREATE TABLE IF NOT EXISTS indexed_scripts(
    workspace TEXT NOT NULL,
    script TEXT NOT NULL,
    st_mtime REAL NOT NULL,
    PRIMARY KEY(workspace, script)
);

CREATE TABLE IF NOT EXISTS requirement_links(
    workspace TEXT NOT NULL,
    script TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    PRIMARY KEY(workspace, script, requirement_id)
);

-- Workspace tree view: which folders are expanded, per workspace
CREATE TABLE IF NOT EXISTS expanded_nodes(
    workspace_id TEXT NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY(workspace_id, path)
);
