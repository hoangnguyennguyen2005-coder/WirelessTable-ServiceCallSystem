"""Central workflow rules.

Traceability to the ECE411 logbook test plan (Step 6): UT-10 admission/FIFO/de-duplication,
UT-12 waiting age, reminder and assignment states, plus the software side of AT-01 and AT-07.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db.store import Store
from app.domain.models import DeviceEvent, DomainError
from app.domain.service import Service
from helpers import accept, act, deliver, event, kinds, staff_event


# ----------------------------------------------------------------- UT-10 admission
def test_registration_retry_restart_and_concurrent(setup):
    s, clock = setup
    call = event()
    r = s.event(call)["request"]
    assert (r["state"], r["category"], r["seq"]) == ("REGISTERED", "SERVICE", 1)
    clock.now += 40
    s = Service(Store(s.store.path, True), clock)
    again = s.event(call)["request"]
    assert again["id"] == r["id"] and again["received_at"] == 1000
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: s.event(event()), range(8)))
    assert {x["request_id"] for x in results} == {r["id"]}
    assert len(s.snapshot()["requests"]) == 1
    assert len(s.snapshot()["tables"]) == 24
    # Race creation on an initially idle second table, with distinct call tokens.
    with ThreadPoolExecutor(max_workers=4) as pool:
        created = list(
            pool.map(
                lambda number: s.event(event(token=100 + number, node_id=2)), range(8)
            )
        )
    assert len({item["request_id"] for item in created}) == 1
    assert len([x for x in s.snapshot()["requests"] if x["table_id"] == 2]) == 1
    assert kinds(s).count("REGISTERED") == 2


def test_24_tables_fifo_by_acceptance_sequence_with_equal_timestamps(setup):
    """UT-10 row 1 / ER-P03: 24 active requests, order never depends on timestamp ties."""
    s, _ = setup
    order = [7, 3, 24, 1] + [n for n in range(1, 25) if n not in (7, 3, 24, 1)]
    ids = [
        s.event(event(node_id=n, category="BILL" if n % 2 else "SERVICE"))["request_id"]
        for n in order
    ]
    assert len(set(ids)) == 24
    queue = s.snapshot()["requests"]
    assert [r["table_id"] for r in queue] == order
    assert [r["seq"] for r in queue] == list(range(1, 25))
    assert len({r["received_at"] for r in queue}) == 1


def test_category_is_registered_and_never_replaced(setup):
    """UT-10 rows 2–3 / ER-F01, ER-F06."""
    s, clock = setup
    r = s.event(event(category="BILL"))["request"]
    assert r["category"] == "BILL"
    clock.now += 30
    other = s.event(event(token=2, category="SERVICE"))["request"]
    assert (other["id"], other["category"], other["received_at"], other["seq"]) == (
        r["id"],
        "BILL",
        1000,
        1,
    )
    assert len(s.snapshot()["requests"]) == 1
    duplicate = s.event_log(kind="DUPLICATE")["items"][0]
    assert duplicate["reason"] == "CALL:active_request_exists:ignored_SERVICE"
    assert (duplicate["table_id"], duplicate["category"]) == (1, "BILL")
    # After confirmed completion a new hold creates a new request ID.
    s.event(event("DONE"))
    new = s.event(event(token=3, category="SERVICE"))["request"]
    assert new["id"] != r["id"] and (new["seq"], new["category"]) == (2, "SERVICE")


def test_event_collision_unknown_node_venue_and_idempotency(setup):
    s, _ = setup
    e = event()
    s.event(e)
    with pytest.raises(DomainError, match="event_id_collision"):
        s.event(e.model_copy(update={"call_token": 2}))
    with pytest.raises(DomainError, match="unknown_node"):
        s.event(event(node_id=99))
    # ER-M03: frames of another venue are never mixed into this one.
    with pytest.raises(DomainError, match="wrong_venue"):
        s.event(event(node_id=2, venue_id=2))
    assert len(s.snapshot()["requests"]) == 1
    r = s.snapshot()["requests"][0]
    action = act(1)
    s.action(r["id"], "ack", action)
    with pytest.raises(DomainError, match="idempotency_key_reused"):
        s.action(r["id"], "dispatch", action)
    failures = [x["reason"] for x in s.event_log(kind="FAILURE", ascending=True)["items"]]
    assert failures == [
        "CALL:event_id_collision",
        "CALL:unknown_node",
        "CALL:wrong_venue",
        "dispatch:idempotency_key_reused",
    ]
    # A retransmission with fresh telemetry is the same frame, not a collision.
    s.event(e.model_copy(update={"payload": e.payload.model_copy(update={"battery_mv": 2900})}))


def test_disabled_table_rejects_new_call_but_finishes_old_one(setup):
    s, _ = setup
    s.event(event())
    done = event("DONE")
    s.event(done)
    with s.store.transaction() as db:
        db.execute("UPDATE tables SET enabled=0 WHERE id=1")
    assert s.event(done)["command"]["payload"]["led"] == "OFF"
    with pytest.raises(DomainError, match="disabled_node"):
        s.event(event(token=2))


# ------------------------------------------------ indication: registered → acknowledged
def test_only_manager_ack_turns_table_green(setup):
    """ER-F03/F04: USB receipt, dispatch and staff acceptance never produce green."""
    s, _ = setup
    result = s.event(event())
    r, receipt = result["request"], result["command"]
    assert receipt["message_type"] == "CALL_RECEIPT"
    assert receipt["payload"] == dict(led="RED", revision=1, category="SERVICE", request_seq=1)
    command = s.commands(1)[0]
    assert command["command_id"] == receipt["command_id"]
    s.event(event("COMMAND_ACK", command_id=command["command_id"]))
    assert s.detail(r["id"])["request"]["state"] == "REGISTERED"
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    deliver(s, r)
    accept(s, r)
    r = s.detail(r["id"])["request"]
    assert (r["state"], r["led_revision"], s.led(r)) == ("REGISTERED", 1, "RED")
    assert s.event(event("STATUS_POLL"))["command"]["payload"]["led"] == "RED"
    ack = act(r["version"])
    r = s.action(r["id"], "ack", ack)
    assert s.action(r["id"], "ack", ack) == r
    assert (r["state"], r["led_revision"]) == ("ACKNOWLEDGED", 2)
    assert s.snapshot()["tables"][0]["led"] is None  # no applied evidence yet
    poll = s.event(event("STATUS_POLL"))["command"]
    assert (poll["payload"]["led"], poll["payload"]["revision"]) == ("GREEN", 2)
    s.event(event("STATUS_APPLIED", payload={"led": "GREEN", "revision": 2}))
    assert s.snapshot()["tables"][0]["led"] == "GREEN"
    # A second ACK from another browser is semantically idempotent.
    assert s.action(r["id"], "ack", act(1))["version"] == r["version"]
    assert kinds(s, r["id"]).count("ACKNOWLEDGED") == 1


def test_status_reply_is_untracked_once_node_confirmed(setup):
    """Polling a settled node costs no outbox rows; a reply still proves a live centre."""
    s, clock = setup
    r = s.event(event())["request"]
    s.event(event("STATUS_APPLIED", payload={"led": "RED", "revision": 1}))
    rows = len(s.store.read("SELECT * FROM outbox"))
    for _ in range(5):
        clock.now += 5
        frames = s.exchange(event("STATUS_POLL"))
        assert len(frames) == 1 and frames[0]["command_id"] is None
        assert frames[0]["payload"]["led"] == "RED" and frames[0]["request_id"] == r["id"]
    assert len(s.store.read("SELECT * FROM outbox")) == rows
    assert s.store.read("SELECT status,applied_at FROM outbox")[0] == dict(
        status="applied", applied_at=1000
    )


# ------------------------------------------------------- UT-12 dispatch and acceptance
def test_dispatch_delivery_and_acceptance_are_distinct(setup):
    """UT-12 row 3 / ER-F07, ER-P05."""
    s, clock = setup
    r = s.event(event(category="BILL"))["request"]
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    assert (s.stage(r), r["dispatched_at"], r["assignment_revision"]) == (
        "DISPATCHED",
        1000,
        1,
    )
    clock.now += 3
    dispatch = s.exchange(staff_event("STAFF_POLL"))[0]
    assert (dispatch["message_type"], dispatch["node_id"]) == ("DISPATCH", 101)
    assert dispatch["payload"] == dict(
        table_id=1,
        table_name="Bàn 01",
        category="BILL",
        assignment_revision=1,
        request_seq=1,
        task="SHOWN",
    )
    # The frame left the centre; nothing proves yet that the device shows it.
    assert s.stage(s.detail(r["id"])["request"]) == "DISPATCHED"
    s.event(staff_event("STAFF_APPLIED", request=r, task="SHOWN"))
    r = s.detail(r["id"])["request"]
    assert (s.stage(r), r["delivered_at"], r["accepted_at"]) == ("DELIVERED", 1003, None)
    clock.now += 4
    assert accept(s, r)[0]["message_type"] == "ACCEPT_RECEIPT"
    r = s.detail(r["id"])["request"]
    assert (s.stage(r), r["accepted_at"]) == ("ACCEPTED", 1007)
    assert r["state"] == "REGISTERED" and r["completed_at"] is None
    assert kinds(s, r["id"]) == ["REGISTERED", "DISPATCHED", "DELIVERED", "ACCEPTED"]
    # A repeated acceptance changes nothing and is recorded as an observed duplicate.
    accept(s, r)
    assert s.detail(r["id"])["request"]["version"] == r["version"]
    assert kinds(s, r["id"])[-1] == "DUPLICATE"


def test_dispatch_requires_available_staff_with_device(setup):
    s, _ = setup
    r = s.event(event())["request"]
    with s.store.transaction() as db:
        db.execute("INSERT INTO staff(id,name,active,available) VALUES(3,'Chưa có máy',1,1)")
        db.execute("UPDATE staff SET available=0 WHERE id=2")
    for staff_id, reason in ((3, "chưa được gán thiết bị"), (2, "không khả dụng"), (9, "không khả dụng")):
        with pytest.raises(DomainError, match=reason):
            s.action(r["id"], "dispatch", act(r["version"], staff_id=staff_id))
    with pytest.raises(DomainError, match="staff_id"):
        s.action(r["id"], "dispatch", act(r["version"]))
    with pytest.raises(DomainError, match="unknown_staff_device"):
        s.event(DeviceEvent(venue_id=1, message_type="STAFF_POLL", event_id="x1", node_id=555))


def test_reassign_invalidates_old_assignment_and_stale_accept(setup):
    """UT-12 row 4 / IT-02 row 4."""
    s, _ = setup
    r = s.event(event())["request"]
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    deliver(s, r)
    with pytest.raises(DomainError, match="Gửi lại"):
        s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    old = dict(r)
    accept(s, r)
    r = s.detail(r["id"])["request"]
    with pytest.raises(DomainError, match="giao lại"):
        s.action(r["id"], "dispatch", act(r["version"], staff_id=2))
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=2, confirm=True))
    assert (r["staff_id"], r["assignment_revision"], r["accepted_at"]) == (2, 2, None)
    # The old device is told to drop the task; its late acceptance cannot overwrite anything.
    cancel = [
        f
        for f in s.exchange(staff_event("STAFF_POLL"))
        if f["message_type"] == "DISPATCH_CANCEL"
    ]
    assert cancel[0]["payload"]["assignment_revision"] == 1
    assert cancel[0]["payload"]["reason"] == "reassigned"
    with pytest.raises(DomainError, match="stale_assignment"):
        s.event(staff_event("STAFF_ACCEPT", request=old))
    with pytest.raises(DomainError, match="stale_assignment"):
        s.event(staff_event("STAFF_ACCEPT", staff_id=1, request=r))
    assert s.stage(s.detail(r["id"])["request"]) == "DISPATCHED"
    deliver(s, r, staff_id=2, boot_id=888)
    accept(s, r, staff_id=2, boot_id=888)
    r = s.detail(r["id"])["request"]
    assert (s.stage(r), r["staff_id"]) == ("ACCEPTED", 2)
    assignments = s.detail(r["id"])["assignments"]
    assert [a["revoke_reason"] for a in assignments] == ["reassigned", None]
    with pytest.raises(DomainError, match="Dữ liệu đã thay đổi"):
        s.action(r["id"], "dispatch", act(1, staff_id=1, confirm=True))


def test_cancel_and_retry_dispatch(setup):
    """ER-R03: acceptance stays pending until received or explicitly cancelled."""
    s, clock = setup
    r = s.event(event())["request"]
    with pytest.raises(DomainError, match="chưa được giao"):
        s.action(r["id"], "cancel_dispatch", act(r["version"]))
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    first = s.commands(101)[0]
    # Manager retries: a fresh command for the same assignment, not a new assignment.
    r = s.action(r["id"], "retry_dispatch", act(r["version"]))
    assert r["assignment_revision"] == 1
    again = s.commands(101)[0]
    assert again["command_id"] != first["command_id"]
    assert again["message_type"] == "DISPATCH"
    clock.now += 1
    s.event(staff_event("STAFF_APPLIED", request=r, task="SHOWN"))
    accept(s, r)
    r = s.detail(r["id"])["request"]
    with pytest.raises(DomainError, match="Nhân viên đã nhận việc"):
        s.action(r["id"], "retry_dispatch", act(r["version"]))
    with pytest.raises(DomainError, match="thu hồi"):
        s.action(r["id"], "cancel_dispatch", act(r["version"]))
    r = s.action(r["id"], "cancel_dispatch", act(r["version"], confirm=True))
    assert (r["staff_id"], s.stage(r), r["assignment_revision"]) == (None, "NONE", 1)
    assert r["state"] == "REGISTERED"
    clock.now += 2
    frames = s.exchange(staff_event("STAFF_POLL"))
    assert [f["message_type"] for f in frames] == ["DISPATCH_CANCEL"]
    s.event(
        staff_event(
            "STAFF_APPLIED",
            request=dict(id=r["id"], assignment_revision=1),
            task="CLEARED",
        )
    )
    assert s.detail(r["id"])["assignments"][0]["cleared_at"] == clock.now
    clock.now += 2
    assert [f["message_type"] for f in s.exchange(staff_event("STAFF_POLL"))] == [
        "STAFF_STATUS"
    ]
    assert kinds(s, r["id"])[-1] == "DISPATCH_CANCELLED"


def test_staff_device_restart_gets_current_tasks_again(setup):
    s, clock = setup
    one = s.event(event())["request"]
    two = s.event(event(node_id=2))["request"]
    one = s.action(one["id"], "dispatch", act(one["version"], staff_id=1))
    two = s.action(two["id"], "dispatch", act(two["version"], staff_id=1))
    deliver(s, one)
    accept(s, one)
    s.event(staff_event("STAFF_APPLIED", request=one, task="ACCEPTED"))
    clock.now += 2
    assert [f["message_type"] for f in s.exchange(staff_event("STAFF_POLL"))] == [
        "STAFF_STATUS"
    ]
    assert s.exchange(staff_event("STAFF_POLL"))[0]["payload"] == dict(open_tasks=2)
    # New session id: the device lost its RAM, so both tasks are sent again in their state.
    clock.now += 2
    frames = s.exchange(staff_event("STAFF_POLL", boot_id=778))
    assert [(f["message_type"], f["payload"]["table_id"]) for f in frames] == [
        ("ACCEPT_RECEIPT", 1),
        ("DISPATCH", 2),
    ]
    assert s.detail(one["id"])["request"]["accepted_at"] is not None


# ----------------------------------------------------------- completion at the table
@pytest.mark.parametrize(
    "stage", ["REGISTERED/NONE", "ACKNOWLEDGED/NONE", "REGISTERED/DELIVERED", "ACKNOWLEDGED/ACCEPTED"]
)
def test_done_closes_any_registered_request_and_old_done_cannot_close_new(setup, stage):
    """ER-F09/F10: completion is valid before or after ACK and staff acceptance."""
    s, _ = setup
    r = s.event(event())["request"]
    state, dispatch = stage.split("/")
    if state == "ACKNOWLEDGED":
        r = s.action(r["id"], "ack", act(r["version"]))
    if dispatch != "NONE":
        r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
        deliver(s, r)
    if dispatch == "ACCEPTED":
        accept(s, r)
    done = event("DONE")
    result = s.event(done)
    closed = result["request"]
    assert (closed["state"], closed["closed_from"]) == ("COMPLETED", stage)
    assert result["command"]["message_type"] == "DONE_RECEIPT"
    assert result["command"]["payload"]["led"] == "OFF"
    assert s.snapshot()["requests"] == []
    r2 = s.event(event(token=2))["request"]
    assert r2["id"] != r["id"]
    # The retried DONE of the closed request never touches the new one.
    assert s.event(done)["request"]["version"] == closed["version"]
    assert s.detail(r2["id"])["request"]["state"] == "REGISTERED"
    assert kinds(s, r["id"])[-2:] == ["COMPLETED", "DUPLICATE"]
    pending = s.store.read(
        "SELECT * FROM outbox WHERE request_id=? AND channel='table' AND type!='DONE_RECEIPT'",
        (r["id"],),
    )
    assert all(x["status"] == "superseded" for x in pending)
    # A delayed green confirmation of the closed request is rejected.
    with pytest.raises(DomainError, match="stale_device_status"):
        s.event(event("STATUS_APPLIED", payload={"led": "GREEN", "revision": 2}))
    if dispatch != "NONE":
        # The staff task is no longer actionable once the table reported completion.
        cancel = [f for f in s.exchange(staff_event("STAFF_POLL")) if f["message_type"] == "DISPATCH_CANCEL"]
        assert cancel[0]["payload"]["reason"] == "completed"
        with pytest.raises(DomainError, match="stale_assignment"):
            s.event(staff_event("STAFF_ACCEPT", request=r))
        assert s.detail(r["id"])["request"]["staff_id"] == 1  # history keeps who was assigned


def test_done_without_registered_request_creates_nothing(setup):
    """ER-F09: presses while no registered active request exists create no completion."""
    s, _ = setup
    with pytest.raises(DomainError, match="no_request_for_correlation"):
        s.event(event("DONE"))
    assert s.history()["total"] == 0
    assert kinds(s) == ["FAILURE"]


def test_node_restart_reconciles_before_new_request(setup):
    """ER-F05: NODE_HELLO returns the outstanding request; nothing is duplicated or reset."""
    s, clock = setup
    r = s.event(event(category="BILL"))["request"]
    r = s.action(r["id"], "ack", act(r["version"]))
    clock.now += 60
    hello = s.event(event("NODE_HELLO", token=0, boot_id=999))
    assert hello["request_id"] == r["id"]
    assert hello["command"]["payload"] == dict(
        led="GREEN", revision=2, category="BILL", request_seq=1
    )
    assert (hello["command"]["boot_id"], hello["command"]["call_token"]) == (999, 0)
    assert s.detail(r["id"])["request"]["received_at"] == 1000
    assert len(s.snapshot()["requests"]) == 1
    # The new session can now finish the same request.
    assert s.event(event("DONE", token=0, boot_id=999))["request"]["state"] == "COMPLETED"
    idle = s.event(event("NODE_HELLO", token=0, boot_id=1001))
    assert idle["request_id"] is None
    assert idle["command"]["payload"] == dict(led="OFF", revision=0)
    assert "RECONCILED" in kinds(s, r["id"])


# ----------------------------------------------------------------- UT-12 reminder
def test_reminder_from_300_seconds_once_without_reset(setup):
    """UT-12 rows 1–2 / ER-F08: eligible at ≥300 s; age and order never reset."""
    s, clock = setup
    first = s.event(event())["request"]
    clock.now += 10
    second = s.event(event(node_id=2))["request"]
    clock.now = 1299.9
    assert s.remind() == 0
    first = s.action(first["id"], "ack", act(first["version"]))
    first = s.action(first["id"], "dispatch", act(first["version"], staff_id=1))
    deliver(s, first)
    accept(s, first)
    clock.now = 1300.0
    assert s.remind() == 1  # acknowledged and accepted, still reminded
    assert s.remind() == 0
    s = Service(Store(s.store.path, True), clock)
    assert s.remind() == 0
    reminded = s.detail(first["id"])["request"]
    assert (reminded["reminded_at"], reminded["received_at"], reminded["seq"]) == (1300, 1000, 1)
    clock.now = 1310.1
    assert s.remind() == 1  # the unacknowledged request follows at its own 300 s
    assert [r["id"] for r in s.snapshot()["requests"]] == [first["id"], second["id"]]
    assert kinds(s).count("OVERDUE") == 2
    s.event(event("DONE"))
    s.event(event("DONE", node_id=2))
    clock.now += 600
    assert s.remind() == 0  # a closed request never produces a reminder


def test_completed_before_threshold_is_never_reminded(setup):
    s, clock = setup
    s.event(event())
    clock.now += 299
    s.event(event("DONE"))
    clock.now += 100
    assert s.remind() == 0 and "OVERDUE" not in kinds(s)


# ----------------------------------------------------------------- battery warning
def test_low_battery_flag_and_optional_threshold(setup):
    """ER-E02 / O5: warning is shown centrally; no percentage is ever derived."""
    s, _ = setup
    s.event(event("DEVICE_STATUS", payload={"battery_mv": 2900}))
    assert (s.snapshot()["tables"][0]["battery_mv"], s.snapshot()["tables"][0]["battery_low"]) == (2900, 0)
    s.event(event("DEVICE_STATUS", payload={"battery_mv": 2150, "battery_low": True}))
    s.event(event("DEVICE_STATUS", payload={"battery_mv": 2140, "battery_low": True}))
    assert s.snapshot()["tables"][0]["battery_low"] == 1
    assert kinds(s) == ["BATTERY_LOW"]  # once per episode
    s.event(event("DEVICE_STATUS", payload={"battery_mv": 3050, "battery_low": False}))
    assert s.snapshot()["tables"][0]["battery_low"] == 0
    # Optional centre-side threshold for nodes that only report millivolts.
    s.low_battery_mv = 2300
    s.event(event("DEVICE_STATUS", node_id=2, payload={"battery_mv": 2250}))
    assert s.snapshot()["tables"][1]["battery_low"] == 1
    s.event(staff_event("STAFF_POLL", staff_id=2, battery_mv=3400, battery_low=True))
    assert s.snapshot()["staff"][1]["battery_low"] == 1
    assert kinds(s) == ["BATTERY_LOW", "BATTERY_LOW", "BATTERY_LOW"]


# ------------------------------------------------------------ unresolved conditions
def test_watch_records_unresolved_conditions_once(setup):
    """ER-R03/ER-P04/ER-P05: unresolved table state, contact and delivery stay visible."""
    s, clock = setup
    r = s.event(event())["request"]
    s.event(event("STATUS_APPLIED", payload={"led": "RED", "revision": 1}))
    r = s.action(r["id"], "ack", act(r["version"]))
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    assert (s.table_contact_seconds, s.staff_contact_seconds) == (8, 8)  # 5 s / 2 s polls
    clock.now += 8
    assert s.watch() == 0  # exactly 8 s: not yet flagged
    clock.now += 0.5
    assert s.watch() == 3  # 2 s left for watch cadence and screen refresh (ER-R03)
    assert s.watch() == 0
    failures = {x["reason"] for x in s.event_log(kind="FAILURE")["items"]}
    assert failures == {
        "table_contact_lost",
        "table_state_not_applied",
        "dispatch_not_delivered",
    }
    # Recovery clears the episode; a later loss is recorded again.
    s.exchange(event("STATUS_POLL"))
    s.event(event("STATUS_APPLIED", payload={"led": "GREEN", "revision": 2}))
    deliver(s, r)
    assert s.watch() == 0
    clock.now += 13
    assert s.watch() == 2
    assert {x["reason"] for x in s.event_log(kind="FAILURE", limit=2)["items"]} == {
        "table_contact_lost",
        "staff_device_contact_lost",
    }
