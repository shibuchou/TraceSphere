"""SQLite WAL storage bootstrap.

Single-writer design: all platform writes go through this module; readers are
safe under WAL. Indexes follow 方案 §2.2/§5.5:
``timestamp / resource_id / correlation_id / event_type / cluster_id``.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .util import format_rfc3339

MIGRATIONS: Sequence[str] = (
    # v1 -- initial schema
    """
CREATE TABLE IF NOT EXISTS resources (
    resource_id    TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    name           TEXT,
    state          TEXT,
    cluster_id     TEXT,
    zone_id        TEXT,
    host_id        TEXT,
    vm_id          TEXT,
    container_id   TEXT,
    correlation_id TEXT,
    origin         TEXT NOT NULL DEFAULT 'zsvirt',
    mode           TEXT NOT NULL DEFAULT 'real',
    labels         TEXT NOT NULL DEFAULT '{}',
    attributes     TEXT NOT NULL DEFAULT '{}',
    observed_at    TEXT,
    ingested_at    TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_resources_kind        ON resources(kind);
CREATE INDEX IF NOT EXISTS idx_resources_cluster     ON resources(cluster_id);
CREATE INDEX IF NOT EXISTS idx_resources_vm          ON resources(vm_id);
CREATE INDEX IF NOT EXISTS idx_resources_host        ON resources(host_id);
CREATE INDEX IF NOT EXISTS idx_resources_container   ON resources(container_id);
CREATE INDEX IF NOT EXISTS idx_resources_name        ON resources(kind, name);
CREATE INDEX IF NOT EXISTS idx_resources_corr        ON resources(correlation_id);

CREATE TABLE IF NOT EXISTS resource_edges (
    src_id      TEXT NOT NULL,
    dst_id      TEXT NOT NULL,
    relation    TEXT NOT NULL,
    origin      TEXT NOT NULL DEFAULT 'zsvirt',
    mode        TEXT NOT NULL DEFAULT 'real',
    labels      TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (src_id, dst_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_edges_dst      ON resource_edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON resource_edges(relation);

CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    schema_version  TEXT NOT NULL DEFAULT 'v1',
    origin          TEXT NOT NULL,
    mode            TEXT NOT NULL,
    observed_at     TEXT NOT NULL,
    ingested_at     TEXT NOT NULL,
    type            TEXT NOT NULL DEFAULT 'event',
    event_type      TEXT NOT NULL DEFAULT 'unknown',
    resource_id     TEXT,
    correlation_id  TEXT,
    trace_id        TEXT,
    task_id         TEXT,
    severity        TEXT,
    cluster_id      TEXT,
    source          TEXT,
    payload         TEXT NOT NULL DEFAULT '{}',
    dedup_key       TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_observed    ON events(observed_at);
CREATE INDEX IF NOT EXISTS idx_events_resource    ON events(resource_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_events_corr        ON events(correlation_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_events_type        ON events(event_type, observed_at);
CREATE INDEX IF NOT EXISTS idx_events_cluster     ON events(cluster_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_events_task        ON events(task_id, observed_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup ON events(dedup_key) WHERE dedup_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS clusters (
    cluster_id     TEXT PRIMARY KEY,
    cluster_key    TEXT UNIQUE,
    correlation_id TEXT,
    resource_id    TEXT,
    rule           TEXT,
    window_start   TEXT,
    window_end     TEXT,
    status         TEXT NOT NULL DEFAULT 'open',
    event_ids      TEXT NOT NULL DEFAULT '[]',
    evidence_ids   TEXT NOT NULL DEFAULT '[]',
    summary        TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clusters_corr     ON clusters(correlation_id);
CREATE INDEX IF NOT EXISTS idx_clusters_resource ON clusters(resource_id);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id     TEXT PRIMARY KEY,
    cluster_id      TEXT,
    kind            TEXT NOT NULL,
    signal          TEXT,
    description     TEXT,
    resource_id     TEXT,
    correlation_id  TEXT,
    task_id         TEXT,
    observed_at     TEXT NOT NULL,
    ingested_at     TEXT NOT NULL,
    source_event_ids TEXT NOT NULL DEFAULT '[]',
    payload         TEXT NOT NULL DEFAULT '{}',
    weight          REAL,
    origin          TEXT,
    mode            TEXT,
    created_at      TEXT NOT NULL,
    dedup_key       TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_cluster  ON evidence(cluster_id);
CREATE INDEX IF NOT EXISTS idx_evidence_resource ON evidence(resource_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_evidence_corr     ON evidence(correlation_id);
CREATE INDEX IF NOT EXISTS idx_evidence_signal   ON evidence(signal);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_dedup ON evidence(dedup_key) WHERE dedup_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS agents (
    agent_id            TEXT PRIMARY KEY,
    resource_id         TEXT,
    configured_vm_uuid  TEXT,
    machine_id          TEXT,
    dmi_uuid            TEXT,
    hostname            TEXT,
    ips                 TEXT NOT NULL DEFAULT '[]',
    version             TEXT,
    registered_at       TEXT NOT NULL,
    last_seen           TEXT NOT NULL,
    raw                 TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_agents_vm_uuid  ON agents(configured_vm_uuid);
CREATE INDEX IF NOT EXISTS idx_agents_resource ON agents(resource_id);

CREATE TABLE IF NOT EXISTS sync_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT NOT NULL,
    mode        TEXT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    ok          INTEGER NOT NULL DEFAULT 0,
    counts      TEXT NOT NULL DEFAULT '{}',
    error       TEXT
);
""",
)


class Database:
    """Thread-local SQLite connection wrapper (safe for ThreadingHTTPServer)."""

    def __init__(self, path: str):
        self.path = path
        self._local = threading.local()
        self._init_lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            directory = os.path.dirname(os.path.abspath(self.path))
            if directory and not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=15.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def init(self) -> None:
        with self._init_lock:
            conn = self.connect()
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            for version, script in enumerate(MIGRATIONS, start=1):
                if version in applied:
                    continue
                # NOTE: executescript() commits any pending transaction first and
                # then runs in autocommit mode, so no explicit BEGIN/COMMIT here.
                # Statements are idempotent (CREATE TABLE/INDEX IF NOT EXISTS).
                conn.executescript(script)
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, format_rfc3339()),
                )

    @property
    def in_transaction(self) -> bool:
        return getattr(self._local, "tx_depth", 0) > 0

    @contextmanager
    def tx(self):
        """Explicit transaction; nested calls join the outer transaction."""
        conn = self.connect()
        depth = getattr(self._local, "tx_depth", 0)
        if depth > 0:
            self._local.tx_depth = depth + 1
            try:
                yield conn
            finally:
                self._local.tx_depth -= 1
            return
        conn.execute("BEGIN IMMEDIATE")
        self._local.tx_depth = 1
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._local.tx_depth = 0

    def query(self, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        rows = self.connect().execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
        row = self.connect().execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        row = self.connect().execute(sql, tuple(params)).fetchone()
        return row[0] if row is not None else None

    def insert(self, sql: str, params: Iterable[Any] = ()) -> int:
        """执行 INSERT 并返回自增主键（lastrowid）。

        NOTE: sqlite3 的 INSERT 不产生结果行，``scalar()`` 会返回 None；
        需要行号的调用方必须走本方法。
        """
        cursor = self.connect().execute(sql, tuple(params))
        return int(cursor.lastrowid or 0)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        cursor = self.connect().execute(sql, tuple(params))
        return cursor.rowcount

    def table_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for table in ("resources", "resource_edges", "events", "evidence", "clusters", "agents"):
            try:
                counts[table] = int(self.scalar("SELECT COUNT(*) FROM %s" % table) or 0)
            except sqlite3.Error:
                counts[table] = -1
        return counts
