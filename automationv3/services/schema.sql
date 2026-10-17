-- Application schema. Applied on every startup, so every statement
-- must be idempotent. There are no migrations: a column added to an
-- existing table is also listed in database.ADDED_COLUMNS; any other
-- change of shape means deleting the database and reloading it.

-- Requirements, imported from DOORS exports (services/requirements).
-- Content is stored by its sha256, so importing the same content again
-- adds nothing.

-- Each spec as last imported
CREATE TABLE IF NOT EXISTS specs(
    key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    level TEXT NOT NULL,
    parents TEXT NOT NULL DEFAULT '[]'
);

-- The files of specs' source trees
CREATE TABLE IF NOT EXISTS blobs(
    hash TEXT PRIMARY KEY,
    content BLOB NOT NULL
);

-- A spec's content at one point. tree is JSON: path -> blob hash;
-- attributes is its attribute schema.
CREATE TABLE IF NOT EXISTS spec_versions(
    hash TEXT PRIMARY KEY,
    spec TEXT NOT NULL,
    title TEXT NOT NULL,
    level TEXT NOT NULL,
    parents TEXT NOT NULL,
    attributes TEXT NOT NULL,
    tree TEXT NOT NULL
);

-- A requirement's content: hash is of all of it; the four facet hashes
-- (text, metadata, links, section) decide what changed
CREATE TABLE IF NOT EXISTS requirement_versions(
    hash TEXT PRIMARY KEY,
    id TEXT NOT NULL,
    text TEXT NOT NULL,
    attributes TEXT NOT NULL,
    satisfies TEXT NOT NULL,
    section TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    metadata_hash TEXT NOT NULL,
    links_hash TEXT NOT NULL,
    section_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS requirement_versions_id ON requirement_versions(id);

-- The requirements in each spec version, in document order
CREATE TABLE IF NOT EXISTS spec_contents(
    spec_version TEXT NOT NULL,
    position INTEGER NOT NULL,
    requirement_version TEXT NOT NULL,
    PRIMARY KEY(spec_version, position)
);

-- Each import of an export folder
CREATE TABLE IF NOT EXISTS imports(
    id INTEGER PRIMARY KEY,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    exported_at TEXT,
    source TEXT NOT NULL,
    manifest TEXT NOT NULL
);

-- Trunk: the version of each spec each import saw, changed or not, and
-- when it was exported. A spec's trunk is its row with the highest
-- import_id; trunk only moves forward, so exported_at never decreases.
CREATE TABLE IF NOT EXISTS trunk_versions(
    import_id INTEGER NOT NULL,
    spec TEXT NOT NULL,
    spec_version TEXT NOT NULL,
    exported_at TEXT NOT NULL,
    PRIMARY KEY(import_id, spec)
);

-- The trunk change log: each requirement an import added, removed or
-- changed. before/after are requirement_versions hashes (NULL when added
-- or removed); changes is JSON: ["added"], ["removed"] or the facets.
CREATE TABLE IF NOT EXISTS requirement_changes(
    import_id INTEGER NOT NULL,
    spec TEXT NOT NULL,
    id TEXT NOT NULL,
    before TEXT,
    after TEXT,
    changes TEXT NOT NULL,
    PRIMARY KEY(import_id, spec, id)
);
CREATE INDEX IF NOT EXISTS requirement_changes_id ON requirement_changes(id);

-- Baselines never change once imported
CREATE TABLE IF NOT EXISTS baselines(
    spec TEXT NOT NULL,
    name TEXT NOT NULL,
    spec_version TEXT NOT NULL,
    import_id INTEGER NOT NULL,
    PRIMARY KEY(spec, name)
);

-- Baseline sets (releases): the baseline of each spec they pin
CREATE TABLE IF NOT EXISTS baseline_sets(
    name TEXT NOT NULL,
    spec TEXT NOT NULL,
    baseline TEXT NOT NULL,
    import_id INTEGER NOT NULL,
    PRIMARY KEY(name, spec)
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

-- Suspect links: the text of a requirement each link was last reviewed
-- against. A link whose requirement's text has changed since is suspect.
-- how is 'first seen' (recorded when the link was first found) or
-- 'reviewed' (someone looked).
CREATE TABLE IF NOT EXISTS script_reviews(
    workspace TEXT NOT NULL,
    script TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    how TEXT NOT NULL,
    PRIMARY KEY(workspace, script, requirement_id)
);

-- The same for trace links in trunk: a child requirement against the
-- text of the parent it satisfies
CREATE TABLE IF NOT EXISTS trace_reviews(
    child TEXT NOT NULL,
    parent TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    how TEXT NOT NULL,
    PRIMARY KEY(child, parent)
);

-- Workspace tree view: which folders are expanded, per workspace
CREATE TABLE IF NOT EXISTS expanded_nodes(
    workspace_id TEXT NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY(workspace_id, path)
);
