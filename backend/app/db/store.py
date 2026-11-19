"""SQLite schema v2 (logbook baseline). Every domain mutation uses a fresh immediate transaction.

v2 adds what the ECE411 logbook requires on top of v1: request category (Service/Bill),
a monotonic acceptance sequence for FIFO, dispatch attributes that are independent from the
table indication, staff devices, a venue identity and the domain event record.
"""

import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tables(id INTEGER PRIMARY KEY,node_id INTEGER UNIQUE NOT NULL,name TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS staff(id INTEGER PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,available INTEGER NOT NULL DEFAULT 1,device_id INTEGER);
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,table_id INTEGER NOT NULL REFERENCES tables(id),state TEXT NOT NULL,
received_at REAL NOT NULL,acknowledged_at REAL,staff_id INTEGER REFERENCES staff(id),assignment_revision INTEGER NOT NULL DEFAULT 0,
accepted_at REAL,completed_at REAL,reminded_at REAL,version INTEGER NOT NULL DEFAULT 1,closed_from TEXT,
seq INTEGER,category TEXT NOT NULL DEFAULT 'SERVICE',dispatched_at REAL,delivered_at REAL,
led_revision INTEGER NOT NULL DEFAULT 1,led_changed_at REAL NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS one_active ON requests(table_id) WHERE state!='COMPLETED';
CREATE UNIQUE INDEX IF NOT EXISTS request_seq ON requests(seq);
CREATE UNIQUE INDEX IF NOT EXISTS staff_device ON staff(device_id) WHERE device_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS correlations(node_id INTEGER NOT NULL,boot_id INTEGER NOT NULL,call_token INTEGER NOT NULL,request_id TEXT NOT NULL REFERENCES requests(id),PRIMARY KEY(node_id,boot_id,call_token));
CREATE TABLE IF NOT EXISTS assignments(id INTEGER PRIMARY KEY,request_id TEXT NOT NULL REFERENCES requests(id),staff_id INTEGER NOT NULL REFERENCES staff(id),revision INTEGER NOT NULL,assigned_at REAL NOT NULL,accepted_at REAL,revoked_at REAL,actor TEXT NOT NULL,delivered_at REAL,
device_id INTEGER,revoke_reason TEXT,cleared_at REAL);
CREATE TABLE IF NOT EXISTS observations(node_id INTEGER PRIMARY KEY,last_seen REAL NOT NULL,led TEXT,battery_mv INTEGER,request_id TEXT,revision INTEGER,
battery_low INTEGER NOT NULL DEFAULT 0,boot_id INTEGER,call_token INTEGER);
CREATE TABLE IF NOT EXISTS staff_observations(device_id INTEGER PRIMARY KEY,last_seen REAL NOT NULL,boot_id INTEGER,boot_at REAL NOT NULL DEFAULT 0,boot_mark INTEGER NOT NULL DEFAULT 0,battery_mv INTEGER,battery_low INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,event_id TEXT NOT NULL,type TEXT NOT NULL,source TEXT NOT NULL,actor TEXT,request_id TEXT,received_at REAL NOT NULL,result TEXT NOT NULL,reason TEXT,
table_id INTEGER,category TEXT,request_seq INTEGER,staff_id INTEGER);
CREATE TABLE IF NOT EXISTS processed(event_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,response TEXT NOT NULL,at REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS actions(key TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,response TEXT NOT NULL,at REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS outbox(command_id TEXT PRIMARY KEY,target INTEGER NOT NULL,request_id TEXT NOT NULL REFERENCES requests(id),type TEXT NOT NULL,payload TEXT NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL,expires_at REAL NOT NULL,error TEXT,
channel TEXT NOT NULL DEFAULT 'table',created_at REAL NOT NULL DEFAULT 0,applied_at REAL);
CREATE INDEX IF NOT EXISTS events_request ON events(request_id,id);
CREATE INDEX IF NOT EXISTS events_time ON events(received_at);
CREATE INDEX IF NOT EXISTS outbox_target ON outbox(target,status);
"""

# v1 → v2: additive columns first, then data is rewritten to the logbook vocabulary.
MIGRATE_V1 = """
ALTER TABLE staff ADD COLUMN device_id INTEGER
ALTER TABLE requests ADD COLUMN seq INTEGER
ALTER TABLE requests ADD COLUMN category TEXT NOT NULL DEFAULT 'SERVICE'
ALTER TABLE requests ADD COLUMN dispatched_at REAL
ALTER TABLE requests ADD COLUMN delivered_at REAL
ALTER TABLE requests ADD COLUMN led_revision INTEGER NOT NULL DEFAULT 1
ALTER TABLE requests ADD COLUMN led_changed_at REAL NOT NULL DEFAULT 0
ALTER TABLE assignments ADD COLUMN device_id INTEGER
ALTER TABLE assignments ADD COLUMN revoke_reason TEXT
ALTER TABLE assignments ADD COLUMN cleared_at REAL
ALTER TABLE observations ADD COLUMN battery_low INTEGER NOT NULL DEFAULT 0
ALTER TABLE observations ADD COLUMN boot_id INTEGER
ALTER TABLE observations ADD COLUMN call_token INTEGER
ALTER TABLE events ADD COLUMN table_id INTEGER
ALTER TABLE events ADD COLUMN category TEXT
ALTER TABLE events ADD COLUMN request_seq INTEGER
ALTER TABLE events ADD COLUMN staff_id INTEGER
ALTER TABLE processed ADD COLUMN at REAL NOT NULL DEFAULT 0
ALTER TABLE actions ADD COLUMN at REAL NOT NULL DEFAULT 0
ALTER TABLE outbox ADD COLUMN channel TEXT NOT NULL DEFAULT 'table'
ALTER TABLE outbox ADD COLUMN created_at REAL NOT NULL DEFAULT 0
ALTER TABLE outbox ADD COLUMN applied_at REAL
"""

V1_EVENT_TYPES = {
    "CALL": "REGISTERED",
    "ACK": "ACKNOWLEDGED",
    "ASSIGN": "DISPATCHED",
    "ACCEPT": "ACCEPTED",
    "DONE": "COMPLETED",
    "REMINDER": "OVERDUE",
    "TABLE_CONFIG": "CONFIG",
    "STAFF_CONFIG": "CONFIG",
}


def add_missing_columns(db):
    """Additive repair: give an existing table any column the current schema declares.

    Databases written by earlier builds of schema v2 can lack a later column (for example
    staff_observations.boot_mark). Only columns SQLite can add in place are handled; the
    declared default fills existing rows. Returns the added "table.column" names.
    """
    reference = sqlite3.connect(":memory:")
    try:
        reference.executescript(SCHEMA)
        tables = [
            r[0]
            for r in reference.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
        added = []
        for table in tables:
            have = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            if not have:
                continue
            for _, name, kind, notnull, default, pk in reference.execute(
                f"PRAGMA table_info({table})"
            ):
                if name in have:
                    continue
                if pk or (notnull and default is None):
                    raise RuntimeError(f"Cannot add column {table}.{name} in place")
                clause = f"ALTER TABLE {table} ADD COLUMN {name} {kind}"
                if notnull:
                    clause += " NOT NULL"
                if default is not None:
                    clause += f" DEFAULT {default}"
                db.execute(clause)
                added.append(f"{table}.{name}")
        return added
    finally:
        reference.close()


def migrate_v1(db, now):
    """Rewrite a v1 database in place. The caller wraps this in one transaction."""
    for statement in MIGRATE_V1.strip().splitlines():
        db.execute(statement)
    # FIFO sequence follows the original central receipt order.
    ordered = db.execute("SELECT id FROM requests ORDER BY received_at,rowid").fetchall()
    for number, row in enumerate(ordered, 1):
        db.execute("UPDATE requests SET seq=? WHERE id=?", (number, row[0]))
    # v1 used the request version as the table LED revision; nodes only accept nondecreasing values.
    db.execute(
        "UPDATE requests SET led_revision=version,"
        "led_changed_at=COALESCE(completed_at,acknowledged_at,received_at)"
    )
    # Dispatch is now a set of attributes, not a lifecycle state.
    db.execute(
        "UPDATE requests SET "
        "dispatched_at=(SELECT a.assigned_at FROM assignments a WHERE a.request_id=requests.id AND a.revision=requests.assignment_revision),"
        "delivered_at=(SELECT a.delivered_at FROM assignments a WHERE a.request_id=requests.id AND a.revision=requests.assignment_revision) "
        "WHERE staff_id IS NOT NULL"
    )
    db.execute(
        "UPDATE requests SET closed_from=CASE closed_from "
        "WHEN 'ACCEPTED' THEN 'ACKNOWLEDGED/ACCEPTED' WHEN 'ASSIGNED' THEN 'ACKNOWLEDGED/DISPATCHED' "
        "WHEN 'ACKNOWLEDGED' THEN 'ACKNOWLEDGED/NONE' ELSE closed_from END WHERE state='COMPLETED'"
    )
    db.execute("UPDATE requests SET state='REGISTERED' WHERE state='WAITING_ACK'")
    db.execute(
        "UPDATE requests SET state='ACKNOWLEDGED' WHERE state IN ('ASSIGNED','ACCEPTED')"
    )
    db.execute(
        "UPDATE assignments SET revoke_reason='reassigned' WHERE revoked_at IS NOT NULL"
    )
    db.execute(
        "UPDATE assignments SET revoke_reason='completed',"
        "revoked_at=(SELECT r.completed_at FROM requests r WHERE r.id=assignments.request_id) "
        "WHERE revoked_at IS NULL AND request_id IN (SELECT id FROM requests WHERE state='COMPLETED')"
    )
    # Frames queued by v1 use protocol 1; the next node contact regenerates them.
    db.execute(
        "UPDATE outbox SET status='superseded' WHERE status IN ('pending','gateway_received')"
    )
    db.execute("UPDATE outbox SET created_at=?", (now,))
    db.execute("UPDATE processed SET at=?", (now,))
    db.execute("UPDATE actions SET at=?", (now,))
    # Event record: keep business facts, drop per-poll transport noise.
    db.execute(
        "DELETE FROM events WHERE result='accepted' AND type IN ('STATUS_POLL','STATUS_APPLIED','COMMAND_ACK','DEVICE_STATUS')"
    )
    db.execute(
        "UPDATE events SET reason=type||':'||COALESCE(reason,'rejected'),type='FAILURE',result='failed' WHERE result='rejected'"
    )
    db.execute(
        "UPDATE events SET reason=type||':retry',type='DUPLICATE' WHERE result='duplicate'"
    )
    # v1 logged every retransmission with a fresh event_id as accepted; only the first is the fact.
    db.execute(
        "UPDATE events SET reason=type||':retry',type='DUPLICATE',result='duplicate' "
        "WHERE result='accepted' AND type IN ('CALL','ACK','DONE') AND request_id IS NOT NULL "
        "AND id>(SELECT MIN(e.id) FROM events e WHERE e.request_id=events.request_id AND e.type=events.type AND e.result='accepted')"
    )
    for old, new in V1_EVENT_TYPES.items():
        db.execute(
            "UPDATE events SET type=? WHERE type=? AND result='accepted'", (new, old)
        )
    db.execute(
        "UPDATE events SET table_id=(SELECT r.table_id FROM requests r WHERE r.id=events.request_id),"
        "category=(SELECT r.category FROM requests r WHERE r.id=events.request_id),"
        "request_seq=(SELECT r.seq FROM requests r WHERE r.id=events.request_id) "
        "WHERE request_id IS NOT NULL"
    )


class Store:
    def __init__(self, path: str, demo: bool = False, venue_id: int = 1):
        self.path = path
        self.venue_id = venue_id
        self.generation = 0
        self._lock = threading.Lock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        db = self.connect()
        try:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, SCHEMA_VERSION):
                raise RuntimeError(f"Unsupported schema version {version}")
            db.execute("PRAGMA journal_mode=WAL")
            if version == 1:
                self._backup(db, f"{path}.v1-backup")
                db.execute("BEGIN IMMEDIATE")
                try:
                    migrate_v1(db, time.time())
                    db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
            if version == SCHEMA_VERSION:
                # Columns first: SCHEMA may create indexes on them.
                for column in add_missing_columns(db):
                    log.warning("Added missing column %s", column)
                db.commit()
            db.executescript(SCHEMA)
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            db.execute(
                "INSERT OR IGNORE INTO meta(key,value) VALUES('venue_id',?)",
                (str(venue_id),),
            )
            stored = int(
                db.execute("SELECT value FROM meta WHERE key='venue_id'").fetchone()[0]
            )
            if stored != venue_id:
                raise RuntimeError(
                    f"Database {path} belongs to venue {stored}; configured venue is {venue_id}"
                )
            if demo:
                db.executemany(
                    "INSERT OR IGNORE INTO tables(id,node_id,name,enabled) VALUES(?,?,?,1)",
                    [(i, i, f"Bàn {i:02}") for i in range(1, 25)],
                )
                db.executemany(
                    "INSERT OR IGNORE INTO staff(id,name,active,available,device_id) VALUES(?,?,1,1,?)",
                    [(1, "Minh Anh", 101), (2, "Quốc Bảo", 102)],
                )
                # Demo profiles created by v1 have staff without a simulated device.
                db.execute(
                    "UPDATE staff SET device_id=100+id WHERE device_id IS NULL AND id<=2 "
                    "AND NOT EXISTS(SELECT 1 FROM tables t WHERE t.node_id=100+staff.id) "
                    "AND NOT EXISTS(SELECT 1 FROM staff s WHERE s.device_id=100+staff.id)"
                )
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _backup(db, target):
        if Path(target).exists():
            return
        copy = sqlite3.connect(target)
        try:
            db.backup(copy)
        finally:
            copy.close()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        # Registration is confirmed to the table only after a durable commit (ER-F03, ER-R04).
        db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            changed = db.total_changes
            db.commit()
            if changed:
                with self._lock:
                    self.generation += 1
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def read(self, sql, args=()):
        db = self.connect()
        try:
            return [dict(row) for row in db.execute(sql, args)]
        finally:
            db.close()
