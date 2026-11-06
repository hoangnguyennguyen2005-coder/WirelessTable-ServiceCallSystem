from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from app.db.store import Store
from app.domain.service import Service
from app.domain.models import DeviceEvent, Action, DomainError


def event(kind="CALL", token=1, **kwargs):
    return DeviceEvent(
        message_type=kind,
        event_id=str(uuid4()),
        node_id=1,
        boot_id=123,
        call_token=token,
        **kwargs,
    )


def act(version, **kwargs):
    return Action(expected_version=version, idempotency_key=str(uuid4()), **kwargs)


def test_call_retry_restart_and_concurrent(setup):
    s, clock = setup
    call = event()
    r = s.event(call)["request"]
    clock.now += 40
    s = Service(Store(s.store.path, True), clock)
    assert s.event(call)["request"]["received_at"] == 1000
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: s.event(event()), range(8)))
    assert {x["request_id"] for x in results} == {r["id"]}
    assert len(s.snapshot()["requests"]) == 1
    assert len(s.snapshot()["tables"]) == 24
    # Race creation on an initially idle second table, with distinct call tokens.
    with ThreadPoolExecutor(max_workers=4) as pool:
        created = list(
            pool.map(
                lambda number: s.event(
                    event(token=100 + number).model_copy(update={"node_id": 2})
                ),
                range(8),
            )
        )
    assert len({item["request_id"] for item in created}) == 1
    assert len([r for r in s.snapshot()["requests"] if r["table_id"] == 2]) == 1


def test_ack_outbox_applied_and_no_transport_ack_business(setup):
    s, _ = setup
    r = s.event(event())["request"]
    command = s.commands(1)[0]
    s.event(event("COMMAND_ACK", command_id=command["command_id"]))
    assert s.detail(r["id"])["request"]["state"] == "WAITING_ACK"
    ack = act(1)
    r = s.action(r["id"], "ack", ack)
    assert s.action(r["id"], "ack", ack) == r
    assert r["state"] == "ACKNOWLEDGED"
    table = s.snapshot()["tables"][0]
    assert table["led"] is None
    poll = s.event(event("STATUS_POLL"))["command"]
    assert poll["payload"]["led"] == "GREEN"
    s.event(event("STATUS_APPLIED", payload=poll["payload"]))
    assert s.snapshot()["tables"][0]["led"] == "GREEN"


def test_assign_accept_reassign_conflicts(setup):
    s, _ = setup
    r = s.event(event())["request"]
    r = s.action(r["id"], "ack", act(1))
    r = s.action(r["id"], "assign", act(r["version"], staff_id=1))
    with pytest.raises(DomainError):
        s.action(r["id"], "accept", act(r["version"], staff_id=2, revision=1))
    r = s.action(r["id"], "accept", act(r["version"], staff_id=1, revision=1))
    assert r["state"] == "ACCEPTED" and r["completed_at"] is None
    assert (
        s.action(r["id"], "accept", act(1, staff_id=1, revision=1))["state"]
        == "ACCEPTED"
    )
    with pytest.raises(DomainError):
        s.action(r["id"], "assign", act(r["version"], staff_id=2))
    r = s.action(
        r["id"], "assign", act(r["version"], staff_id=2, confirm_reassign=True)
    )
    assert r["assignment_revision"] == 2
    with pytest.raises(DomainError):
        s.action(r["id"], "accept", act(r["version"], staff_id=1, revision=1))
    with pytest.raises(DomainError):
        s.action(r["id"], "assign", act(1, staff_id=1))
    assert len(s.detail(r["id"])["assignments"]) == 2


@pytest.mark.parametrize("closing_state", ["ACKNOWLEDGED", "ASSIGNED", "ACCEPTED"])
def test_done_valid_and_old_done_cannot_close_new(setup, closing_state):
    s, _ = setup
    r = s.event(event())["request"]
    with pytest.raises(DomainError, match="done_before_ack"):
        s.event(event("DONE"))
    r = s.action(r["id"], "ack", act(1))
    if closing_state != "ACKNOWLEDGED":
        r = s.action(r["id"], "assign", act(r["version"], staff_id=1))
    if closing_state == "ACCEPTED":
        r = s.action(r["id"], "accept", act(r["version"], staff_id=1, revision=1))
    done = event("DONE")
    closed = s.event(done)["request"]
    assert closed["closed_from"] == closing_state
    assert closed["state"] == "COMPLETED"
    r2 = s.event(event(token=2))["request"]
    assert r2["id"] != r["id"]
    assert s.event(done)["request"]["version"] == closed["version"]
    assert s.detail(r2["id"])["request"]["state"] == "WAITING_ACK"
    old = s.store.read(
        "SELECT * FROM outbox WHERE request_id=? AND type='SET_REQUEST_STATUS'",
        (r["id"],),
    )
    assert all(x["status"] == "superseded" for x in old)
    with pytest.raises(DomainError):
        s.event(
            event("STATUS_APPLIED", payload={"led": "GREEN", "revision": r["version"]})
        )


def test_reminder_strict_threshold_restart_once_no_reset(setup):
    s, clock = setup
    r = s.event(event())["request"]
    clock.now = 1300
    assert s.remind() == 0
    s.action(r["id"], "ack", act(1))
    clock.now += 0.01
    assert s.remind() == 1
    s = Service(Store(s.store.path, True), clock)
    assert s.remind() == 0
    assert s.detail(r["id"])["request"]["reminded_at"] == 1300.01
    assert s.store.read("SELECT COUNT(*) AS n FROM outbox")[0]["n"] > 0
    s.event(event("DONE"))
    clock.now += 600
    assert s.remind() == 0


def test_event_collision_unknown_and_idempotency_payload(setup):
    s, _ = setup
    e = event()
    s.event(e)
    with pytest.raises(DomainError):
        s.event(e.model_copy(update={"call_token": 2}))
    with pytest.raises(DomainError):
        s.event(e.model_copy(update={"node_id": 99, "event_id": str(uuid4())}))
    r = s.snapshot()["requests"][0]
    action = act(1)
    s.action(r["id"], "ack", action)
    with pytest.raises(DomainError):
        s.action(r["id"], "assign", action)
    assert len(s.store.read("SELECT * FROM events WHERE result='rejected'")) == 3


def test_old_accept_idempotency_key_rejected_after_reassign(setup):
    s, _ = setup
    r = s.event(event())["request"]
    r = s.action(r["id"], "ack", act(1))
    r = s.action(r["id"], "assign", act(r["version"], staff_id=1))
    accept = act(r["version"], staff_id=1, revision=1)
    r = s.action(r["id"], "accept", accept)
    r = s.action(
        r["id"], "assign", act(r["version"], staff_id=2, confirm_reassign=True)
    )
    with pytest.raises(DomainError):
        s.action(r["id"], "accept", accept)
    assert s.detail(r["id"])["request"]["staff_id"] == 2


def test_disable_completed_table_still_allows_done_receipt_retry(setup):
    s, _ = setup
    r = s.event(event())["request"]
    s.action(r["id"], "ack", act(1))
    done = event("DONE")
    s.event(done)
    with s.store.transaction() as db:
        db.execute("UPDATE tables SET enabled=0 WHERE id=1")
    assert s.event(done)["command"]["payload"]["led"] == "OFF"
    with pytest.raises(DomainError):
        s.event(event(token=2))
