"""SQLite schema v1. Every domain mutation uses a fresh immediate transaction."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tables(id INTEGER PRIMARY KEY,node_id INTEGER UNIQUE NOT NULL,name TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS staff(id INTEGER PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,available INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,table_id INTEGER NOT NULL REFERENCES tables(id),state TEXT NOT NULL,
received_at REAL NOT NULL,acknowledged_at REAL,staff_id INTEGER REFERENCES staff(id),assignment_revision INTEGER NOT NULL DEFAULT 0,
accepted_at REAL,completed_at REAL,reminded_at REAL,version INTEGER NOT NULL DEFAULT 1,closed_from TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_active ON requests(table_id) WHERE state!='COMPLETED';
CREATE TABLE IF NOT EXISTS correlations(node_id INTEGER NOT NULL,boot_id INTEGER NOT NULL,call_token INTEGER NOT NULL,request_id TEXT NOT NULL REFERENCES requests(id),PRIMARY KEY(node_id,boot_id,call_token));
CREATE TABLE IF NOT EXISTS assignments(id INTEGER PRIMARY KEY,request_id TEXT NOT NULL REFERENCES requests(id),staff_id INTEGER NOT NULL REFERENCES staff(id),revision INTEGER NOT NULL,assigned_at REAL NOT NULL,accepted_at REAL,revoked_at REAL,actor TEXT NOT NULL,delivered_at REAL);
CREATE TABLE IF NOT EXISTS observations(node_id INTEGER PRIMARY KEY,last_seen REAL NOT NULL,led TEXT,battery_mv INTEGER,request_id TEXT,revision INTEGER);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,event_id TEXT NOT NULL,type TEXT NOT NULL,source TEXT NOT NULL,actor TEXT,request_id TEXT,received_at REAL NOT NULL,result TEXT NOT NULL,reason TEXT);
CREATE TABLE IF NOT EXISTS processed(event_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,response TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS actions(key TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,response TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(command_id TEXT PRIMARY KEY,target INTEGER NOT NULL,request_id TEXT NOT NULL REFERENCES requests(id),type TEXT NOT NULL,payload TEXT NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL,expires_at REAL NOT NULL,error TEXT);
CREATE INDEX IF NOT EXISTS events_request ON events(request_id,id);
PRAGMA user_version=1;
"""


class Store:
    def __init__(self, path: str, demo: bool = False):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(f"Unsupported schema version {version}")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            if demo:
                db.executemany(
                    "INSERT OR IGNORE INTO tables VALUES(?,?,?,1)",
                    [(i, i, f"Bàn {i:02}") for i in range(1, 25)],
                )
                db.executemany(
                    "INSERT OR IGNORE INTO staff VALUES(?,?,1,1)",
                    [(1, "Minh Anh"), (2, "Quốc Bảo")],
                )

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def read(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args)]
