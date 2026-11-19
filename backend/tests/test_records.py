"""Durable commit, restart recovery, the event record and schema migration.

Traceability to the ECE411 logbook: UT-11 (persistent commit, recovery, event export),
AT-07 rows 5–7 (restart, eight event types, 30-day retention), ER-F03, ER-F11, ER-R04, ER-M03.
"""

import csv
import io
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.db.store import SCHEMA_VERSION, Store
from app.domain.models import DomainError
from app.domain.service import Service
from app.main import EVENT_COLUMNS, create_app
from helpers import accept, act, deliver, event, kinds

V1_SCHEMA = """
CREATE TABLE tables(id INTEGER PRIMARY KEY,node_id INTEGER UNIQUE NOT NULL,name TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE staff(id INTEGER PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,available INTEGER NOT NULL DEFAULT 1);
CREATE TABLE requests(id TEXT PRIMARY KEY,table_id INTEGER NOT NULL REFERENCES tables(id),state TEXT NOT NULL,
received_at REAL NOT NULL,acknowledged_at REAL,staff_id INTEGER REFERENCES staff(id),assignment_revision INTEGER NOT NULL DEFAULT 0,
accepted_at REAL,completed_at REAL,reminded_at REAL,version INTEGER NOT NULL DEFAULT 1,closed_from TEXT);
CREATE UNIQUE INDEX one_active ON requests(table_id) WHERE state!='COMPLETED';
CREATE TABLE correlations(node_id INTEGER NOT NULL,boot_id INTEGER NOT NULL,call_token INTEGER NOT NULL,request_id TEXT NOT NULL REFERENCES requests(id),PRIMARY KEY(node_id,boot_id,call_token));
CREATE TABLE assignments(id INTEGER PRIMARY KEY,request_id TEXT NOT NULL REFERENCES requests(id),staff_id INTEGER NOT NULL REFERENCES staff(id),revision INTEGER NOT NULL,assigned_at REAL NOT NULL,accepted_at REAL,revoked_at REAL,actor TEXT NOT NULL,delivered_at REAL);
CREATE TABLE observations(node_id INTEGER PRIMARY KEY,last_seen REAL NOT NULL,led TEXT,battery_mv INTEGER,request_id TEXT,revision INTEGER);
CREATE TABLE events(id INTEGER PRIMARY KEY,event_id TEXT NOT NULL,type TEXT NOT NULL,source TEXT NOT NULL,actor TEXT,request_id TEXT,received_at REAL NOT NULL,result TEXT NOT NULL,reason TEXT);
CREATE TABLE processed(event_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,response TEXT NOT NULL);
CREATE TABLE actions(key TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,response TEXT NOT NULL);
CREATE TABLE outbox(command_id TEXT PRIMARY KEY,target INTEGER NOT NULL,request_id TEXT NOT NULL REFERENCES requests(id),type TEXT NOT NULL,payload TEXT NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL,expires_at REAL NOT NULL,error TEXT);
CREATE INDEX events_request ON events(request_id,id);
PRAGMA user_version=1;
"""


class BrokenCommit(Store):
    """A store whose commit fails, as with a full disk or power loss before the sync."""

    @contextmanager
    def transaction(self):
        with super().transaction() as db:
            yield db
            raise sqlite3.OperationalError("disk I/O error")


# ----------------------------------------------------------- UT-11 durable commit
def test_no_confirmation_without_durable_commit(tmp_path):
    """UT-11 row 1 / ER-F03: a failed commit authorises no confirmed indication."""
    path = str(tmp_path / "t.db")
    Store(path, True)
    broken = Service(BrokenCommit(path, True))
    with pytest.raises(sqlite3.OperationalError):
        broken.exchange(event())  # nothing is returned to the node
    healthy = Service(Store(path, True))
    assert healthy.snapshot()["requests"] == [] and healthy.history()["total"] == 0
    # The node repeats the same attempt; registration then happens exactly once.
    frames = healthy.exchange(event())
    assert [f["message_type"] for f in frames] == ["CALL_RECEIPT"]
    assert len(healthy.snapshot()["requests"]) == 1


def test_restart_restores_requests_order_states_and_commands(setup):
    """UT-11 row 2 / AT-07 row 5 / ER-R04."""
    s, clock = setup
    a = s.event(event(node_id=1, category="BILL"))["request"]
    clock.now += 5
    b = s.event(event(node_id=2))["request"]
    clock.now += 5
    c = s.event(event(node_id=3))["request"]
    a = s.action(a["id"], "ack", act(a["version"]))
    b = s.action(b["id"], "dispatch", act(b["version"], staff_id=2))
    deliver(s, b, staff_id=2)
    accept(s, b, staff_id=2)
    before = s.snapshot()["requests"]
    outbox = s.store.read("SELECT * FROM outbox ORDER BY rowid")
    restarted = Service(Store(s.store.path, True), clock)  # only the file survives
    assert restarted.snapshot()["requests"] == before
    assert restarted.store.read("SELECT * FROM outbox ORDER BY rowid") == outbox
    assert [
        (r["seq"], r["state"], restarted.stage(r), r["received_at"])
        for r in restarted.snapshot()["requests"]
    ] == [
        (1, "ACKNOWLEDGED", "NONE", 1000),
        (2, "REGISTERED", "ACCEPTED", 1005),
        (3, "REGISTERED", "NONE", 1010),
    ]
    # The pending green command survived and leaves on the next node contact.
    frames = restarted.exchange(event("STATUS_POLL", node_id=1))
    assert frames[0]["payload"]["led"] == "GREEN" and frames[0]["command_id"]
    # Nodes retry after the restart: no duplicate entry, original time kept.
    again = restarted.event(event(node_id=3))["request"]
    assert (again["id"], again["received_at"]) == (c["id"], 1010)
    assert len(restarted.snapshot()["requests"]) == 3


def test_crash_after_commit_before_reply_is_reconciled_by_retry(setup):
    """UT-11 row 2 / AT-07 row 1b: a lost reply never proves that nothing was registered."""
    s, clock = setup
    call = event(category="BILL")
    s.event(call)  # committed, then the process dies before a byte is written
    restarted = Service(Store(s.store.path, True), clock)
    clock.now += 1
    frames = restarted.exchange(call)
    assert [f["message_type"] for f in frames] == ["CALL_RECEIPT"]
    active = restarted.snapshot()["requests"]
    assert len(active) == 1
    assert (active[0]["received_at"], active[0]["category"]) == (1000, "BILL")
    assert kinds(restarted) == ["REGISTERED", "DUPLICATE"]
    # Completion: closed before the crash, the receipt goes out on the DONE retry.
    done = event("DONE")
    restarted.event(done)
    again = Service(Store(s.store.path, True), clock)
    frames = again.exchange(done)
    assert frames[0]["message_type"] == "DONE_RECEIPT"
    assert frames[0]["payload"]["led"] == "OFF"
    assert again.history()["items"][0]["completed_at"] == 1001
    assert kinds(again).count("COMPLETED") == 1


# ------------------------------------------------------------- ER-F11 event record
def test_eight_event_types_are_recorded_and_exported(tmp_path):
    """UT-11 row 3 / AT-07 row 6: types, identity, central ISO 8601 time, no guest data."""
    app = create_app(Config(data_dir=str(tmp_path)))
    with TestClient(app) as c:
        sim = app.state.simulator

        def post(frame, status=200):
            response = c.post("/api/sim/event", json=frame.model_dump())
            assert response.status_code == status, response.text
            return response.json()

        def node_contact():
            with sim.lock:
                sim.node(1)["next_poll"] = 0
                sim.tick()

        with sim.lock:  # a guest holds Bill for 5 s on the simulated table unit
            sim.press(1, True, "BILL")
            sim.node(1)["hold_at"] -= 5
            sim.tick()
        r = c.get("/api/snapshot").json()["requests"][0]  # registered
        post(event(category="BILL", boot_id=4242))  # observed duplicate
        post(event("DONE", node_id=5), 409)  # observed failure

        def action(kind, **extra):
            nonlocal r
            response = c.post(
                f"/api/requests/{r['id']}/{kind}",
                json=dict(
                    expected_version=r["version"],
                    idempotency_key=str(uuid4()),
                    **extra,
                ),
            )
            assert response.status_code == 200, response.text
            r = response.json()

        action("ack")  # manager acknowledged
        node_contact()  # the table shows green on its next poll
        action("dispatch", staff_id=1)  # dispatched
        with sim.lock:
            sim.staff.device(1).poll(app.state.service.clock())  # delivered
        accepted = c.post("/api/staff-device/1/accept", json={"request_id": r["id"]})
        assert accepted.json()["tasks"][0]["state"] == "ACCEPTED"  # staff accepted
        c.post("/api/sim/action", json={"action": "advance", "seconds": 300})  # overdue
        for _ in range(2):  # recessed control pressed twice at the table
            c.post("/api/sim/action", json={"action": "hidden", "node_id": 1})  # completed

        text = c.get("/api/events.csv").text
        rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
        assert list(rows[0]) == EVENT_COLUMNS  # nothing that could identify a guest
        by_type = {row["event"]: row for row in rows}
        eight = [
            "REGISTERED",
            "ACKNOWLEDGED",
            "DISPATCHED",
            "ACCEPTED",
            "OVERDUE",
            "COMPLETED",
            "DUPLICATE",
            "FAILURE",
        ]
        assert set(eight) <= set(by_type)
        for kind in eight[:-1]:
            row = by_type[kind]
            assert (row["table_id"], row["table_name"], row["category"]) == (
                "1",
                "Bàn 01",
                "BILL",
            )
            assert (row["request_id"], row["request_seq"]) == (r["id"], "1")
            stamp = datetime.fromisoformat(row["time"])
            assert stamp.utcoffset() == timedelta(hours=7)
            assert abs(stamp.timestamp() - float(row["epoch"])) < 0.002
        rejected = [x for x in rows if x["detail"] == "DONE:no_request_for_correlation"]
        assert [(x["event"], x["table_id"], x["request_id"]) for x in rejected] == [
            ("FAILURE", "5", "")
        ]
        assert by_type["ACCEPTED"]["staff_name"] == "Minh Anh"
        assert [int(row["id"]) for row in rows] == sorted(int(row["id"]) for row in rows)

        assert c.get("/api/event-log?type=COMPLETED").json()["total"] == 1
        assert c.get("/api/event-log?table_id=5").json()["items"][0]["type"] == "FAILURE"
        only = c.get("/api/events.csv?type=OVERDUE").text.strip().splitlines()
        assert len(only) == 2
        timeline = [e["type"] for e in c.get(f"/api/requests/{r['id']}").json()["events"]]
        assert timeline == [
            "REGISTERED",
            "DUPLICATE",
            "ACKNOWLEDGED",
            "DISPATCHED",
            "DELIVERED",
            "ACCEPTED",
            "OVERDUE",
            "COMPLETED",
        ]


def test_event_retention_never_deletes_before_30_days(setup):
    """UT-11 row 4 / AT-07 row 7, with a labelled controlled clock (not a month-long run)."""
    s, clock = setup
    r = s.event(event())["request"]
    s.event(event("DONE"))
    start, day = clock.now, 86400
    for elapsed, kept in ((29 * day, True), (30 * day, True), (31 * day, False)):
        clock.now = start + elapsed
        s = Service(Store(s.store.path, True), clock, retention_days=30)  # across restarts
        s.prune()
        assert bool(kinds(s, r["id"])) is kept
    assert s.history()["total"] == 1  # the request stays in history
    assert Service(Store(s.store.path, True), clock, retention_days=1).retention_days == 30
    with pytest.raises(ValueError, match="at least 30"):
        Config(retention_days=29)


# -------------------------------------------------------------------- ER-M03 venue
def test_database_belongs_to_one_venue(tmp_path):
    path = str(tmp_path / "venue.db")
    Store(path, venue_id=7)
    with pytest.raises(RuntimeError, match="venue 7"):
        Store(path, venue_id=8)
    assert Service(Store(path, venue_id=7)).venue_id == 7


def test_second_venue_differs_only_by_configuration(tmp_path):
    """AT-04 row 3 (software side): same build, other identifiers, no mixed calls."""
    one = Service(Store(str(tmp_path / "one.db"), True, venue_id=1))
    two = Service(Store(str(tmp_path / "two.db"), True, venue_id=2))
    a = one.event(event(venue_id=1))["request"]
    b = two.event(event(venue_id=2))["request"]
    assert a["id"] != b["id"]
    for service, own, foreign in ((one, 1, 2), (two, 2, 1)):
        with pytest.raises(DomainError, match="wrong_venue"):
            service.event(event(node_id=2, venue_id=foreign))
        with pytest.raises(DomainError, match="wrong_venue"):
            service.event(event("DONE", venue_id=foreign))
        assert len(service.snapshot()["requests"]) == 1
        assert service.exchange(event("STATUS_POLL", venue_id=own))[0]["venue_id"] == own


# ---------------------------------------------------------------- schema migration
def v1_database(path):
    db = sqlite3.connect(path)
    db.executescript(V1_SCHEMA)
    db.executemany(
        "INSERT INTO tables VALUES(?,?,?,1)", [(i, i, f"Bàn {i:02}") for i in (1, 2, 3)]
    )
    db.executemany(
        "INSERT INTO staff VALUES(?,?,1,1)", [(1, "Minh Anh"), (2, "Quốc Bảo")]
    )
    # (id, table, state, received, acked, staff, assignment rev, accepted, completed, reminded, version, closed_from)
    db.executemany(
        "INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("D", 1, "COMPLETED", 10, 12, None, 0, None, 20, None, 3, "ACKNOWLEDGED"),
            ("C", 3, "COMPLETED", 50, 55, 2, 1, 60, 70, None, 5, "ACCEPTED"),
            ("B", 2, "ASSIGNED", 90, 95, 1, 1, None, None, None, 3, None),
            ("A", 1, "WAITING_ACK", 100, None, None, 0, None, None, None, 1, None),
        ],
    )
    db.executemany(
        "INSERT INTO correlations VALUES(?,?,?,?)",
        [(1, 5, 1, "D"), (3, 5, 1, "C"), (2, 5, 1, "B"), (1, 5, 2, "A")],
    )
    db.executemany(
        "INSERT INTO assignments(request_id,staff_id,revision,assigned_at,accepted_at,actor,delivered_at) VALUES(?,?,?,?,?,?,?)",
        [("B", 1, 1, 96, None, "manager", 97), ("C", 2, 1, 56, 60, "manager", 57)],
    )
    db.executemany(
        "INSERT INTO events(event_id,type,source,actor,request_id,received_at,result,reason) VALUES(?,?,?,?,?,?,?,?)",
        [
            ("e1", "CALL", "gateway", "1", "A", 100, "accepted", None),
            ("e2", "CALL", "gateway", "1", "A", 101, "accepted", None),
            ("e3", "STATUS_POLL", "gateway", "1", "A", 102, "accepted", None),
            ("e4", "ACK", "web", "manager", "B", 95, "accepted", None),
            ("e5", "ASSIGN", "web", "manager", "B", 96, "accepted", None),
            ("e6", "DONE", "gateway", "3", "C", 70, "accepted", None),
            ("e6", "DONE", "gateway", "3", "C", 71, "duplicate", None),
            ("e7", "DONE", "gateway", "1", "A", 103, "rejected", "done_before_ack"),
            ("e8", "REMINDER", "worker", "system", "C", 65, "accepted", None),
            ("e9", "TABLE_CONFIG", "web", "manager", None, 5, "accepted", None),
        ],
    )
    db.executemany(
        "INSERT INTO outbox(command_id,target,request_id,type,payload,revision,status,next_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?)",
        [
            ("c1", 2, "B", "SET_REQUEST_STATUS", "{}", 3, "pending", 0, 9e9),
            ("c2", 3, "C", "DONE_RECEIPT", "{}", 5, "applied", 0, 9e9),
        ],
    )
    db.execute("INSERT INTO processed VALUES('e1','f','{}')")
    db.execute("INSERT INTO actions VALUES('key-0001','f','{}')")
    db.commit()
    db.close()


def test_v1_database_is_migrated_in_place_with_backup(tmp_path):
    path = str(tmp_path / "hardware.sqlite3")
    v1_database(path)
    store = Store(path)
    assert store.read("PRAGMA user_version")[0]["user_version"] == SCHEMA_VERSION
    backup = sqlite3.connect(path + ".v1-backup")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
    assert backup.execute("SELECT state FROM requests WHERE id='A'").fetchone()[0] == "WAITING_ACK"
    backup.close()

    rows = {r["id"]: r for r in store.read("SELECT * FROM requests")}
    assert [rows[k]["seq"] for k in "DCBA"] == [1, 2, 3, 4]  # original arrival order
    assert {r["category"] for r in rows.values()} == {"SERVICE"}
    assert (rows["A"]["state"], rows["B"]["state"]) == ("REGISTERED", "ACKNOWLEDGED")
    assert (rows["B"]["dispatched_at"], rows["B"]["delivered_at"], rows["B"]["led_revision"]) == (96, 97, 3)
    assert rows["C"]["closed_from"] == "ACKNOWLEDGED/ACCEPTED"
    assert rows["D"]["closed_from"] == "ACKNOWLEDGED/NONE"
    assignments = {a["request_id"]: a for a in store.read("SELECT * FROM assignments")}
    assert (assignments["C"]["revoked_at"], assignments["C"]["revoke_reason"]) == (70, "completed")
    assert assignments["B"]["revoked_at"] is None
    assert {o["command_id"]: o["status"] for o in store.read("SELECT * FROM outbox")} == {
        "c1": "superseded",
        "c2": "applied",
    }
    events = [
        (e["event_id"], e["type"], e["reason"], e["table_id"])
        for e in store.read("SELECT * FROM events ORDER BY id")
    ]
    assert events == [
        ("e1", "REGISTERED", None, 1),
        ("e2", "DUPLICATE", "CALL:retry", 1),
        ("e4", "ACKNOWLEDGED", None, 2),
        ("e5", "DISPATCHED", None, 2),
        ("e6", "COMPLETED", None, 3),
        ("e6", "DUPLICATE", "DONE:retry", 3),
        ("e7", "FAILURE", "DONE:done_before_ack", 1),
        ("e8", "OVERDUE", None, 3),
        ("e9", "CONFIG", None, None),
    ]

    # The migrated profile keeps working with the current rules.
    Store(path)  # reopening is a no-op
    service = Service(Store(path))
    assert [r["id"] for r in service.snapshot()["requests"]] == ["B", "A"]
    green = service.exchange(event("STATUS_POLL", node_id=2, boot_id=5))
    assert (green[0]["payload"]["led"], green[0]["payload"]["revision"]) == ("GREEN", 3)
    assert service.event(event("DONE", node_id=1, boot_id=5, token=2))["request"]["closed_from"] == "REGISTERED/NONE"
    assert service.event(event(node_id=3, boot_id=5, token=2))["request"]["seq"] == 5
    # Staff from v1 have no device yet; dispatch says so instead of failing silently.
    with pytest.raises(DomainError, match="chưa được gán thiết bị"):
        service.action("B", "dispatch", act(3, staff_id=2, confirm=True))


def test_v1_demo_profile_gets_simulated_staff_devices(tmp_path):
    path = str(tmp_path / "simulation.sqlite3")
    v1_database(path)
    store = Store(path, demo=True)
    assert [s["device_id"] for s in store.read("SELECT device_id FROM staff ORDER BY id")] == [101, 102]
    assert len(store.read("SELECT id FROM tables")) == 24


def test_earlier_v2_database_gets_missing_columns(tmp_path):
    """A v2 file from an earlier build (no staff_observations.boot_mark) is repaired, not crashed."""
    path = str(tmp_path / "simulation.sqlite3")
    Store(path, demo=True).connect().close()
    db = sqlite3.connect(path)
    db.execute("DROP TABLE staff_observations")
    db.execute(
        "CREATE TABLE staff_observations(device_id INTEGER PRIMARY KEY,last_seen REAL NOT NULL,"
        "boot_id INTEGER,boot_at REAL NOT NULL DEFAULT 0,battery_mv INTEGER,"
        "battery_low INTEGER NOT NULL DEFAULT 0)"
    )
    db.execute("INSERT INTO staff_observations(device_id,last_seen) VALUES(101,1)")
    db.commit()
    db.close()
    store = Store(path, demo=True)
    with store.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        row = db.execute("SELECT boot_mark FROM staff_observations").fetchone()
    assert row[0] == 0
    s = Service(store)
    staff = s.snapshot()["staff"]
    assert staff  # staff devices still listed; polling no longer hits a missing column
