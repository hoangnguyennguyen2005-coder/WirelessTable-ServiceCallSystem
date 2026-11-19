"""HTTP boundary: manager actions, staff device screen, configuration and profile isolation."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.main import create_app
from helpers import event


def body(version, **extra):
    return dict(expected_version=version, idempotency_key=str(uuid4()), **extra)


def test_api_lifecycle_security_history_config(tmp_path):
    app = create_app(Config(data_dir=str(tmp_path)))
    with TestClient(app) as c:
        sim = app.state.simulator
        snapshot = c.get("/api/snapshot").json()
        assert len(snapshot["tables"]) == 24 and snapshot["venue_id"] == 1
        assert snapshot["limits"]["reminder_seconds"] == 300
        assert [s["device_id"] for s in snapshot["staff"]] == [101, 102]
        assert (
            c.post(
                "/api/sim/action",
                json={"action": "burst"},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        # Four tables call together; categories are kept and the queue is FIFO.
        queue = c.post("/api/sim/action", json={"action": "burst"}).json()
        assert [n["pattern"] for n in queue["nodes"]] == ["red"] * 4
        requests = c.get("/api/snapshot").json()["requests"]
        assert [(r["table_id"], r["seq"], r["category"]) for r in requests] == [
            (1, 1, "SERVICE"),
            (2, 2, "BILL"),
            (3, 3, "SERVICE"),
            (4, 4, "BILL"),
        ]
        r = requests[1]

        def action(kind, status=200, **extra):
            nonlocal r
            response = c.post(
                f"/api/requests/{r['id']}/{kind}", json=body(r["version"], **extra)
            )
            assert response.status_code == status, response.text
            if status == 200:
                r = response.json()
            return response

        # Dispatch does not need a prior acknowledgement and does not turn the table green.
        action("dispatch", staff_id=1)
        with sim.lock:
            sim.staff.device(1).poll(app.state.service.clock())
        device = c.get("/api/staff-device/1").json()
        assert [(t["table_name"], t["category"], t["state"]) for t in device["tasks"]] == [
            ("Bàn 02", "BILL", "SHOWN")
        ]
        assert c.get("/api/staff-device/2").json()["tasks"] == []
        assert c.get("/api/staff-device/9").status_code == 404
        accepted = c.post("/api/staff-device/1/accept", json={"request_id": r["id"]})
        assert accepted.json()["tasks"][0]["state"] == "ACCEPTED"
        r = c.get(f"/api/requests/{r['id']}").json()["request"]
        assert (r["state"], r["accepted_at"] is not None) == ("REGISTERED", True)
        assert c.post("/api/staff-device/1/accept", json={"request_id": "gone"}).status_code == 409
        action("ack")
        assert r["state"] == "ACKNOWLEDGED"
        assert "xác nhận giao lại" in action("dispatch", 409, staff_id=2).json()["detail"]
        action("cancel-dispatch", confirm=True)
        assert r["staff_id"] is None
        assert action("retry-dispatch", 409).json()["detail"] == "Yêu cầu chưa được giao"
        # No web shortcut can complete a request.
        for path in ("done", "complete", "accept"):
            assert c.post(f"/api/requests/{r['id']}/{path}", json={}).status_code == 404
        assert c.post("/api/staff-device/1/done", json={}).status_code in (404, 405)
        for _ in range(2):
            c.post("/api/sim/action", json={"action": "hidden", "node_id": 2})
        history = c.get("/api/history?state=COMPLETED&table_id=2").json()
        assert history["total"] == 1
        assert history["items"][0]["closed_from"] == "ACKNOWLEDGED/NONE"
        assert c.get("/api/history?category=BILL").json()["total"] == 2
        assert c.get("/api/history?staff_id=2").json()["total"] == 0
        assert (
            c.post(
                "/api/config/tables", json={"id": 1, "node_id": 1, "name": "=SUM(A1)"}
            ).status_code
            == 200
        )
        export = c.get("/api/export.csv").text
        assert "'=SUM(A1)" in export and "registered_at" in export.splitlines()[0]
        health = c.get("/api/health").json()
        assert (health["status"], health["schema"], health["protocol_version"]) == ("ok", 2, 2)
        assert health["startup"]["recovered_active"] == 0
        assert health["startup"]["recovery_ms"] >= 0
        assert c.post("/api/sim/action", json={"action": "reset"}).status_code == 422
        assert (
            c.post(
                "/api/sim/action", json={"action": "reset", "confirm": "RESET DEMO"}
            ).status_code
            == 200
        )
        assert c.get("/api/history").json()["total"] == 0
        assert c.get("/api/event-log").json()["total"] == 0


def test_simulator_actions_for_node_and_staff_device(tmp_path):
    app = create_app(Config(data_dir=str(tmp_path)))
    with TestClient(app) as c:

        def sim(**action):
            response = c.post("/api/sim/action", json=action)
            assert response.status_code == 200, response.text
            return response.json()

        low = sim(action="battery", node_id=3, enabled=True)
        assert [n["battery_low"] for n in low["nodes"] if n["node_id"] == 3] == [True]
        assert c.get("/api/snapshot").json()["tables"][2]["battery_low"] == 1
        assert sim(action="restart", node_id=3)["nodes"][0]["phase"] == "sleep"
        off = sim(action="staff_power", staff_id=2, enabled=False)
        assert [d["powered"] for d in off["staff_devices"]] == [True, False]
        assert sim(action="connection", enabled=False)["connected"] is False
        assert c.get("/api/snapshot").json()["gateway"]["connected"] is False
        armed = sim(action="fault", fault="drop_receipt", node_id=2)
        assert (armed["fault"], armed["fault_node"]) == ("drop_receipt", 2)
        assert sim(action="fault", fault="duplicate")["fault_node"] is None  # any table
        assert sim(action="delay", seconds=3)["delay"] == 3
        pressed = sim(action="press", node_id=5, category="BILL")
        assert [(n["pattern"], n["category"]) for n in pressed["nodes"] if n["node_id"] == 5] == [
            ("hold", "BILL")
        ]
        released = sim(action="release", node_id=5, category="BILL")
        assert [n["pattern"] for n in released["nodes"] if n["node_id"] == 5] == ["off"]
        assert c.post("/api/sim/action", json={"action": "press", "node_id": 99}).status_code == 422
        assert c.post("/api/sim/action", json={"action": "press", "category": "ORDER"}).status_code == 422


def test_configuration_rules_for_devices(tmp_path):
    app = create_app(Config(data_dir=str(tmp_path)))
    with TestClient(app) as c:
        staff = {"id": 3, "name": "Thu Hà", "device_id": 103}
        assert c.post("/api/config/staff", json=staff).status_code == 200
        assert [s["device_id"] for s in c.get("/api/snapshot").json()["staff"]] == [101, 102, 103]
        # One address space: a staff device can never reuse a table node id, and vice versa.
        assert c.post("/api/config/staff", json={**staff, "device_id": 5}).status_code == 409
        assert c.post("/api/config/staff", json={**staff, "device_id": 101}).status_code == 409
        assert c.post("/api/config/tables", json={"id": 30, "node_id": 103, "name": "Sân"}).status_code == 409
        assert c.post("/api/config/tables", json={"id": 30, "node_id": 2, "name": "Sân"}).status_code == 409
        assert c.post("/api/config/tables", json={"id": 30, "node_id": 30, "name": "  "}).status_code == 422
        # While work is assigned the device binding and the table node cannot change.
        r = c.post("/api/sim/event", json=event().model_dump()).json()["request"]
        c.post(f"/api/requests/{r['id']}/dispatch", json=body(r["version"], staff_id=3))
        assert c.post("/api/config/staff", json={**staff, "device_id": 104}).status_code == 409
        assert c.post("/api/config/staff", json={**staff, "active": False}).status_code == 409
        assert c.post("/api/config/staff", json={**staff, "name": "Thu Hà B"}).status_code == 200
        assert c.post("/api/config/tables", json={"id": 1, "node_id": 40, "name": "Bàn 01"}).status_code == 409
        assert c.post("/api/config/tables", json={"id": 1, "node_id": 1, "name": "Bàn 01", "enabled": False}).status_code == 409
        log = c.get("/api/event-log?type=CONFIG").json()
        assert log["total"] == 2


def test_hardware_profile_isolation_and_staff_stub(tmp_path):
    demo = create_app(Config(data_dir=str(tmp_path)))
    with TestClient(demo) as c:
        c.post("/api/sim/event", json=event().model_dump())
    # Without a token the hardware profile hosts no virtual staff device at all.
    plain = create_app(Config(mode="hardware", data_dir=str(tmp_path)))
    with TestClient(plain) as c:
        assert c.get("/api/snapshot").json()["tables"] == []
        assert c.get("/api/snapshot").json()["requests"] == []
        assert c.get("/api/snapshot").json()["staff_stub"] is False
        assert c.post("/api/sim/event", json=event().model_dump()).status_code == 404
        assert c.post("/api/sim/action", json={"action": "burst"}).status_code == 404
        assert c.get("/api/staff-device/1").status_code == 404
        assert c.get("/api/health", headers={"Host": "example.com"}).status_code == 403
        assert c.get("/api/health").json()["gateway"]["connected"] is False
    app = create_app(
        Config(mode="hardware", data_dir=str(tmp_path), staff_token="test-secret")
    )
    with TestClient(app) as c:
        key = {"x-staff-token": "test-secret"}
        assert c.post("/api/config/tables", json={"id": 1, "node_id": 1, "name": "Bàn 01"}).status_code == 200
        assert c.post("/api/config/staff", json={"id": 1, "name": "Stub", "device_id": 201}).status_code == 200
        assert c.get("/api/staff-device/1").status_code == 403
        assert c.get("/api/staff-device/1", headers={"x-staff-token": "wrong"}).status_code == 403
        assert c.get("/api/staff-device/2", headers=key).status_code == 403
        device = c.get("/api/staff-device/1", headers=key).json()
        assert (device["source"], device["device_id"], device["tasks"]) == ("stub", 201, [])
        # The stub speaks the same device events as a real unit: a frame for the table node
        # arrives through the service exactly as the gateway would deliver it.
        service = app.state.service
        r = service.event(event(category="BILL"))["request"]
        c.post(f"/api/requests/{r['id']}/dispatch", json=body(r["version"], staff_id=1))
        with app.state.staff_stub.lock:
            app.state.staff_stub.device(1).poll(service.clock())
        shown = c.get("/api/staff-device/1", headers=key).json()["tasks"]
        assert [(t["category"], t["state"]) for t in shown] == [("BILL", "SHOWN")]
        done = c.post("/api/staff-device/1/accept", json={"request_id": r["id"]}, headers=key)
        assert done.json()["tasks"][0]["state"] == "ACCEPTED"
        events = [e["source"] for e in c.get(f"/api/requests/{r['id']}").json()["events"]]
        assert events == ["gateway", "web", "stub", "stub"]


def test_database_of_another_venue_is_refused(tmp_path):
    create_app(Config(mode="hardware", data_dir=str(tmp_path), venue_id=1))
    with pytest.raises(RuntimeError, match="venue 1"):
        create_app(Config(mode="hardware", data_dir=str(tmp_path), venue_id=2))
    other = create_app(Config(mode="hardware", data_dir=str(tmp_path / "branch2"), venue_id=2))
    with TestClient(other) as c:
        assert c.get("/api/health").json()["venue_id"] == 2
