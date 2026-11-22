"""Table-unit simulator, virtual staff device, frame parser and serial worker.

Traceability (logbook Step 6): UT-01/UT-02 hold and double-press qualification, UT-03 state and
indication mapping, UT-04/UT-05 frame validation and retry scheduling, UT-06 bridge discipline,
UT-07/UT-08 staff task and acceptance, AT-07 rows 1–4 fault handling. The simulator is a
software model of the planned firmware behaviour, not a measurement of the real units.
"""

import json
import queue
import time

import pytest

from app.adapters import serial_gateway
from app.adapters.serial_gateway import FrameParser, SerialGateway
from app.adapters.simulator import Simulator
from app.db.store import Store
from app.domain.models import DomainError
from app.domain.service import Service
from helpers import act, event, kinds, staff_event


def pattern(sim, clock, node_id=1):
    return sim.public(sim.node(node_id), clock.now)["pattern"]


def registered(setup, category="SERVICE"):
    """Simulator with table 1 registered at t=1005."""
    s, c = setup
    sim = Simulator(s)
    sim.press(1, True, category)
    c.now = 1005
    sim.tick()
    return s, c, sim, s.snapshot()["requests"][0]


# ------------------------------------------------------------------ UT-04 parser
def test_parser_fragmented_multiple_malformed_oversized():
    parser = FrameParser(512)
    frame = event().model_dump_json().encode() + b"\n"
    assert parser.feed(frame[:20]) == []
    assert len(parser.feed(frame[20:] + frame)) == 2
    assert (
        parser.feed(b"not json\n" + b"x" * 2000 + b"\n" + b'{"message_type":12}\n')
        == []
    )
    assert parser.errors == 3 and len(parser.buffer) == 0
    assert len(parser.feed(frame)) == 1
    assert parser.feed(b"\xff\n") == []


def test_parser_rejects_frames_that_break_the_v2_contract():
    parser = FrameParser()
    good = json.loads(event().model_dump_json())

    def feed(data):
        return parser.feed((json.dumps(data) + "\n").encode())

    assert len(feed(good)) == 1
    broken = [
        dict(protocol_version=1),
        dict(venue_id=0),
        dict(payload={}),  # CALL without Service/Bill category
        dict(payload={"category": "ORDER"}),
        dict(message_type="ORDER"),
        dict(node_id=70000),
        dict(extra_field=1),
        dict(message_type="STAFF_ACCEPT", payload={}),
        dict(message_type="STAFF_APPLIED", payload={"assignment_revision": 1, "request_seq": 1}),
        dict(message_type="STATUS_APPLIED", payload={"led": "GREEN"}),
        dict(message_type="COMMAND_ACK", payload={}),
    ]
    for change in broken:
        assert feed({**good, **change}) == []
    assert feed({k: v for k, v in good.items() if k != "venue_id"}) == []
    assert parser.errors == len(broken) + 1


# ---------------------------------------------------------- UT-01 guest hold input
def test_hold_qualification_exactly_one_attempt_at_5_seconds(setup):
    s, c = setup
    sim = Simulator(s)
    for held in (0, 1.0, 4.9, 4.999):
        c.now = float(int(c.now) + 10)
        sim.press(1, True, "BILL")
        c.now += held
        sim.press(1, False, "BILL")
        assert not s.snapshot()["requests"] and sim.node(1)["phase"] == "sleep"
    c.now = 2000.0
    sim.press(1, True, "BILL")
    c.now = 2002.0
    assert pattern(sim, c) == "hold"  # red flashes while held
    c.now = 2005.0
    sim.press(1, False, "BILL")  # an exact 5 s hold counts
    assert [(r["category"], r["seq"]) for r in s.snapshot()["requests"]] == [("BILL", 1)]
    assert pattern(sim, c) == "red"
    # ER-F06: further holds while the request is active create nothing and change nothing.
    sim.press(1, True, "SERVICE")
    c.now = 2015.0
    sim.tick()
    sim.press(1, False, "SERVICE")
    active = s.snapshot()["requests"]
    assert [(r["category"], r["received_at"]) for r in active] == [("BILL", 2005.0)]
    assert 2 not in sim.nodes  # sleeping nodes have no heartbeat
    assert kinds(s) == ["REGISTERED"]


def test_first_control_wins_and_continued_hold_adds_nothing(setup):
    s, c = setup
    sim = Simulator(s)
    sim.press(1, True, "SERVICE")
    c.now = 1002
    sim.press(1, True, "BILL")  # second control while the first is held: ignored
    sim.press(1, False, "BILL")
    assert (sim.node(1)["phase"], sim.node(1)["hold_category"]) == ("holding", "SERVICE")
    c.now = 1005
    sim.tick()
    c.now = 1030  # the guest keeps holding long after the threshold
    sim.tick()
    assert [r["category"] for r in s.snapshot()["requests"]] == ["SERVICE"]
    assert kinds(s) == ["REGISTERED"]


# ------------------------------------------- ER-P02 registration outcome within 5 s
def test_registration_unconfirmed_after_5_seconds_then_reconciled(setup):
    """AT-07 row 1a: without the centre's confirmation there is never a steady red."""
    s, c = setup
    sim = Simulator(s)
    sim.connected = False
    sim.press(1, True)
    c.now = 1005
    sim.tick()
    assert pattern(sim, c) == "pending" and not s.snapshot()["requests"]
    c.now = 1009.5
    sim.tick()
    assert pattern(sim, c) == "pending"
    c.now = 1010
    sim.tick()
    assert pattern(sim, c) == "unconfirmed" and sim.node(1)["led"] == "OFF"
    # No second attempt is admitted while the first is unresolved.
    sim.press(1, True, "BILL")
    c.now = 1016
    sim.tick()
    sim.press(1, False, "BILL")
    assert not s.snapshot()["requests"]
    sim.connected = True
    c.now = 1021
    sim.tick()
    assert pattern(sim, c) == "red"
    assert [r["category"] for r in s.snapshot()["requests"]] == ["SERVICE"]
    assert kinds(s) == ["REGISTERED"]


def test_lost_registration_reply_is_reconciled_by_retry(setup):
    """AT-07 row 1b: a lost reply never proves that the centre did not register."""
    s, c = setup
    sim = Simulator(s)
    sim.fault = "drop_receipt"
    sim.press(1, True)
    c.now = 1005
    sim.tick()
    assert len(s.snapshot()["requests"]) == 1  # the centre did register
    assert pattern(sim, c) == "pending"  # the table must not claim it yet
    c.now = 1006
    sim.tick()  # automatic retry inside the 5 s window, same attempt identity
    assert pattern(sim, c) == "red"
    assert [r["received_at"] for r in s.snapshot()["requests"]] == [1005]
    assert kinds(s) == ["REGISTERED", "DUPLICATE"]


def test_fault_armed_for_one_table_is_not_used_by_another(setup):
    """AT-07 rehearsal row 1b: table 1's routine poll must not use up table 2's fault."""
    s, c, sim, _ = registered(setup)
    sim.press(1, False)
    sim.fault, sim.fault_node = "drop_receipt", 2
    sim.press(2, True, "BILL")
    c.now = 1010
    sim.tick()  # table 1 polls and table 2 qualifies in the same tick
    assert pattern(sim, c) == "red"
    assert pattern(sim, c, 2) == "pending"  # table 2 got the dropped reply
    assert (sim.fault, sim.fault_node) == ("none", None)  # used exactly once
    c.now = 1011
    sim.tick()
    assert pattern(sim, c, 2) == "red"
    table2 = [r for r in s.snapshot()["requests"] if r["table_id"] == 2]
    assert [(r["category"], r["received_at"]) for r in table2] == [("BILL", 1010)]
    assert [e["type"] for e in s.event_log(table_id=2, ascending=True)["items"]] == [
        "REGISTERED",
        "DUPLICATE",
    ]


def test_switched_off_staff_device_stays_off_after_centre_restart(setup):
    """AT-07 row 5a: restarting the PC must not power the simulated staff device back on."""
    s, c = setup
    sim = Simulator(s)
    sim.staff.power(2, False, c.now)
    sim.tick()
    again = Simulator(Service(Store(s.store.path, True), c))
    again.tick()
    powered = {d["staff_id"]: d["powered"] for d in again.staff.snapshot()}
    assert powered == {1: True, 2: False}
    again.reset()  # demo reset brings every simulated device back
    again.tick()
    assert all(d["powered"] for d in again.staff.snapshot())


def test_duplicated_registration_frame_gives_one_request(setup):
    s, c = setup
    sim = Simulator(s)
    sim.fault = "duplicate"
    sim.press(1, True, "BILL")
    c.now = 1005
    sim.tick()
    assert pattern(sim, c) == "red"
    assert [(r["table_id"], r["category"]) for r in s.snapshot()["requests"]] == [(1, "BILL")]
    assert kinds(s) == ["REGISTERED", "DUPLICATE"]


def test_delayed_then_lost_call_claims_nothing_until_registered(setup):
    s, c = setup
    sim = Simulator(s)
    sim.fault, sim.delay = "drop_event", 2
    sim.press(1, True)
    c.now = 1005
    sim.tick()
    assert pattern(sim, c) == "pending" and not s.snapshot()["requests"]
    c.now = 1007
    sim.tick()  # sent late, then lost on air: nothing registered, no red
    assert pattern(sim, c) == "pending" and not s.snapshot()["requests"]
    c.now = 1008
    sim.tick()
    assert pattern(sim, c) == "red" and len(s.snapshot()["requests"]) == 1


# ------------------------------------------------ ER-P04 acknowledgement to the table
def test_ack_reaches_table_on_next_poll_and_latency_is_recorded(setup):
    s, c, sim, r = registered(setup)
    c.now = 1006
    s.action(r["id"], "ack", act(r["version"]))
    sim.tick()
    assert pattern(sim, c) == "red"  # manager acknowledged ≠ table already shows green
    assert s.snapshot()["tables"][0]["observed_revision"] == 1
    c.now = 1010
    sim.tick()  # next active poll
    assert pattern(sim, c) == "green"
    snapshot = s.snapshot()
    assert (snapshot["tables"][0]["led"], snapshot["tables"][0]["observed_revision"]) == ("GREEN", 2)
    request = snapshot["requests"][0]
    assert request["table_command"]["applied_at"] - request["led_changed_at"] == 4


# ------------------------------------------------------- UT-02 recessed double press
def test_double_press_window_single_press_and_idle(setup):
    s, c = setup
    sim = Simulator(s)  # default window 1000 ms (ER-F09, provisional until ER-U02)
    sim.hidden_press(1)
    sim.hidden_press(1)  # idle: no completion event at all
    assert kinds(s) == [] and sim.node(1)["pending"] is None
    sim.press(1, True)
    c.now = 1005.0
    sim.tick()
    sim.hidden_press(1)  # a single press never closes
    c.now = 1006.001
    sim.hidden_press(1)  # 1001 ms later: not a pair, counts as a new first press
    assert len(s.snapshot()["requests"]) == 1 and sim.node(1)["phase"] == "active"
    c.now = 1010.0
    sim.hidden_press(1)
    c.now = 1011.0
    sim.hidden_press(1)  # exactly 1000 ms: valid pair
    assert s.snapshot()["requests"] == [] and pattern(sim, c) == "off"
    # Completion before any manager ACK or staff acceptance is valid (ER-F09).
    assert s.history()["items"][0]["closed_from"] == "REGISTERED/NONE"
    sim.hidden_press(1)
    sim.hidden_press(1)  # nothing left to complete
    assert kinds(s) == ["REGISTERED", "COMPLETED"]


def test_completion_stays_pending_until_centre_confirms(setup):
    """ER-F10 / AT-07 row 2b: the table never clears on its own."""
    s, c, sim, r = registered(setup)
    s.action(r["id"], "ack", act(r["version"]))
    c.now = 1010
    sim.tick()
    assert pattern(sim, c) == "green"
    sim.fault = "drop_receipt"
    sim.hidden_press(1)
    c.now = 1010.5
    sim.hidden_press(1)
    assert s.snapshot()["requests"] == []  # the centre closed it durably
    assert pattern(sim, c) == "completing" and sim.node(1)["led"] == "GREEN"
    sim.hidden_press(1)
    sim.hidden_press(1)  # more presses while pending: no second closure
    # A delayed acknowledgement frame cannot end or override the pending completion.
    node = sim.node(1)
    late = s.frame(
        "SET_REQUEST_STATUS",
        1,
        request_id=r["id"],
        boot_id=node["boot_id"],
        call_token=node["call_token"],
        payload=dict(led="GREEN", revision=2),
    )
    sim.apply(node, late)
    assert pattern(sim, c) == "completing"
    c.now = 1011.5
    sim.tick()  # DONE is retried with the same identity
    assert pattern(sim, c) == "off" and sim.node(1)["phase"] == "sleep"
    assert kinds(s)[-2:] == ["COMPLETED", "DUPLICATE"]
    assert s.snapshot()["tables"][0]["led"] == "OFF"


# ----------------------------------------------------------- ER-R03 contact loss
def test_contact_loss_is_visible_within_10_seconds_and_recovers(setup):
    """AT-07 rows 2a and 3: visible unresolved state, then the original request again."""
    s, c, sim, r = registered(setup)
    s.action(r["id"], "ack", act(r["version"]))
    c.now = 1010
    sim.tick()
    assert pattern(sim, c) == "green"
    sim.connected = False
    c.now = 1015
    sim.tick()
    assert pattern(sim, c) == "green"  # one missed poll is not yet a loss
    c.now = 1020
    sim.tick()
    assert pattern(sim, c) == "unconfirmed"  # 10 s without an application-level reply
    assert sim.node(1)["led"] == "GREEN"  # no false clear; the state is kept for recovery
    c.now = 1020
    assert s.watch() == 1  # the centre records it too: 10 s after the last good poll (ER-R03)
    assert s.event_log(kind="FAILURE")["items"][0]["reason"] == "table_contact_lost"
    sim.connected = True
    c.now = 1025
    sim.tick()
    assert pattern(sim, c) == "green"
    active = s.snapshot()["requests"]
    assert [(x["id"], x["received_at"], x["state"]) for x in active] == [
        (r["id"], 1005, "ACKNOWLEDGED")
    ]


def test_restarted_node_reconciles_before_admitting_a_new_request(setup):
    """ER-F05 / AT-07 row 4."""
    s, c, sim, r = registered(setup, "BILL")
    sim.connected = False
    sim.restart(1)  # cells replaced while the centre is unreachable
    assert pattern(sim, c) == "reconciling"
    sim.press(1, True, "SERVICE")
    c.now = 1012
    sim.tick()
    sim.press(1, False, "SERVICE")
    assert sim.node(1)["phase"] == "reconciling" and len(s.snapshot()["requests"]) == 1
    c.now = 1016
    assert pattern(sim, c) == "unconfirmed"
    sim.connected = True
    c.now = 1020
    sim.tick()
    node = sim.node(1)
    assert pattern(sim, c) == "red"
    assert (node["request_id"], node["category"]) == (r["id"], "BILL")
    assert s.snapshot()["requests"][0]["received_at"] == 1005
    sim.hidden_press(1)
    sim.hidden_press(1)  # the reconciled session can complete the original request
    assert s.snapshot()["requests"] == []
    sim.restart(2)  # nothing outstanding: the node may sleep and accept a new hold
    assert sim.node(2)["phase"] == "sleep"


def test_failed_node_does_not_block_other_tables_or_invent_calls(setup):
    """ER-R02 / AT-07 row 4."""
    s, c = setup
    sim = Simulator(s)
    sim.press(1, True)
    sim.press(2, True, "BILL")
    c.now = 1005
    sim.tick()
    del sim.nodes[1]  # node 1 dies: it simply goes silent
    sim.press(3, True)
    c.now = 1010
    sim.tick()
    assert [r["table_id"] for r in s.snapshot()["requests"]] == [1, 2, 3]
    sim.hidden_press(2)
    c.now = 1010.5
    sim.hidden_press(2)
    assert [r["table_id"] for r in s.snapshot()["requests"]] == [1, 3]
    c.now = 1015
    sim.tick()
    c.now = 1020
    sim.tick()
    assert s.watch() == 1  # only the silent table is reported; no idle heartbeat exists
    lost = s.event_log(kind="FAILURE")["items"][0]
    assert (lost["reason"], lost["table_id"]) == ("table_contact_lost", 1)


def test_simulated_battery_warning_reaches_the_centre(setup):
    s, c = setup
    sim = Simulator(s)
    assert s.snapshot()["tables"][0]["battery_mv"] is None  # no telemetry is invented
    sim.battery(1, True)
    table = s.snapshot()["tables"][0]
    assert (table["battery_low"], table["battery_mv"]) == (1, 2150)
    sim.battery(1, False)
    assert s.snapshot()["tables"][0]["battery_low"] == 0
    assert kinds(s) == ["BATTERY_LOW"]


# ------------------------------------------------------- UT-07/UT-08 staff device
def test_staff_device_shows_task_once_and_accepts_explicitly(setup):
    s, c, sim, r = registered(setup, "BILL")
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    c.now = 1007
    sim.tick()  # the device polls every 2 s
    device = sim.staff.device(1)
    shot = device.snapshot(c.now)
    assert shot["vibrating"]
    assert [(t["table_name"], t["category"], t["state"]) for t in shot["tasks"]] == [
        ("Bàn 01", "BILL", "SHOWN")
    ]
    assert s.stage(s.detail(r["id"])["request"]) == "DELIVERED"  # receipt, not acceptance
    c.now = 1020
    sim.tick()
    assert s.stage(s.detail(r["id"])["request"]) == "DELIVERED" and len(device.tasks) == 1
    assert not device.snapshot(c.now)["vibrating"]
    with pytest.raises(DomainError):
        device.accept("unknown-request", c.now)
    device.accept(r["id"], c.now)
    assert device.tasks[r["id"]]["state"] == "ACCEPTED"
    assert s.stage(s.detail(r["id"])["request"]) == "ACCEPTED"
    assert sim.staff.device(2).snapshot(c.now)["tasks"] == []  # addressed to one device
    assert pattern(sim, c) == "red"  # acceptance alone never turns the table green


def test_acceptance_stays_pending_until_confirmed_or_cancelled(setup):
    """AT-07 row 2c / ER-R03."""
    s, c, sim, r = registered(setup)
    sim.press(2, True, "BILL")
    c.now = 1010
    sim.tick()
    other = s.snapshot()["requests"][1]
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    other = s.action(other["id"], "dispatch", act(other["version"], staff_id=1))
    c.now = 1012
    sim.tick()
    device = sim.staff.device(1)
    assert [t["state"] for t in device.snapshot(c.now)["tasks"]] == ["SHOWN", "SHOWN"]
    sim.connected = False
    device.accept(r["id"], c.now, link_up=False)
    device.accept(other["id"], c.now, link_up=False)
    assert device.tasks[r["id"]]["state"] == "ACCEPTING"
    assert s.stage(s.detail(r["id"])["request"]) == "DELIVERED"  # pending on both sides
    # The manager explicitly cancels one of them while the link is down.
    other = s.action(other["id"], "cancel_dispatch", act(other["version"]))
    sim.connected = True
    c.now = 1014
    sim.tick()
    assert [(t["request_id"], t["state"]) for t in device.snapshot(c.now)["tasks"]] == [
        (r["id"], "ACCEPTED")
    ]
    assert s.stage(s.detail(r["id"])["request"]) == "ACCEPTED"
    assert s.stage(s.detail(other["id"])["request"]) == "NONE"
    assert "ACCEPTED" not in kinds(s, other["id"])


def test_reassignment_clears_the_old_device(setup):
    s, c, sim, r = registered(setup)
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    c.now = 1007
    sim.tick()
    first, second = sim.staff.device(1), sim.staff.device(2)
    assert len(first.tasks) == 1
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=2))
    c.now = 1009
    sim.tick()
    assert first.tasks == {}  # a reassigned task must not remain actionable
    assert [t["revision"] for t in second.snapshot(c.now)["tasks"]] == [2]
    second.accept(r["id"], c.now)
    r = s.detail(r["id"])["request"]
    assert (r["staff_id"], s.stage(r)) == (2, "ACCEPTED")


def test_dispatch_to_powered_off_device_stays_unresolved_then_delivers(setup):
    """ER-P05: a missing delivery remains visible; nothing is silently assumed."""
    s, c, sim, r = registered(setup)
    sim.staff.device(1).power(False, c.now)
    r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
    c.now = 1016
    sim.tick()
    assert s.stage(s.detail(r["id"])["request"]) == "DISPATCHED"
    assert s.watch() == 2
    reasons = {x["reason"] for x in s.event_log(kind="FAILURE")["items"]}
    assert reasons == {"dispatch_not_delivered", "staff_device_contact_lost"}
    assert sim.staff.device(1).snapshot(c.now)["tasks"] == []
    sim.staff.device(1).power(True, c.now)
    sim.tick()
    assert s.stage(s.detail(r["id"])["request"]) == "DELIVERED"
    assert s.watch() == 0


# --------------------------------------------------------------- outbox and restart
def test_command_backoff_limit_expiry_restart(setup):
    s, c = setup
    s.event(event())
    for i in range(5):
        commands = s.commands(1)
        assert len(commands) == 1
        assert not s.commands(1)
        c.now += 2**i
    assert not s.commands(1)
    assert s.store.read("SELECT status FROM outbox")[0]["status"] == "failed"
    assert s.event_log(kind="FAILURE")["items"][0]["reason"] == "CALL_RECEIPT:command_failed"
    s.event(event("STATUS_POLL"))
    s = Service(Store(s.store.path), c)
    assert s.commands(1)
    c.now += 121
    assert not s.commands(1)
    assert any(
        x["status"] == "expired" for x in s.store.read("SELECT status FROM outbox")
    )


def test_simulator_rehydrates_active_requests_after_restart(setup):
    s, c, sim, r = registered(setup, "BILL")
    s.action(r["id"], "ack", act(r["version"]))
    r = s.action(r["id"], "dispatch", act(2, staff_id=2))
    c.now = 1007
    sim.tick()
    assert s.stage(s.detail(r["id"])["request"]) == "DELIVERED"
    service = Service(Store(s.store.path, True), c)  # centre restart
    restored = Simulator(service)
    assert pattern(restored, c) == "reconciling"
    restored.tick()
    assert pattern(restored, c) == "green"
    active = service.snapshot()["requests"]
    assert [(x["id"], x["received_at"], x["category"]) for x in active] == [
        (r["id"], 1005, "BILL")
    ]
    # The staff device also came back with a new session and shows its task again.
    assert [t["state"] for t in restored.staff.device(2).snapshot(c.now)["tasks"]] == ["SHOWN"]
    assert kinds(service).count("REGISTERED") == 1


# --------------------------------------------------------- UT-06 gateway bridge
def test_gateway_opens_serial_with_reset_lines_inactive(monkeypatch):
    class Port:
        def __init__(self, *, baudrate, timeout):
            self.baudrate = baudrate
            self.timeout = timeout
            self.dtr = self.rts = True

        def open(self):
            assert (self.port, self.baudrate, self.timeout) == ("COM8", 115200, 0.2)
            assert self.dtr is False and self.rts is False
            self.is_open = True

    monkeypatch.setattr(serial_gateway.serial, "Serial", Port)
    assert serial_gateway.open_gateway_port("COM8", 115200, timeout=0.2).is_open


def test_serial_worker_reconnects_and_bridges_table_and_staff(setup):
    import serial

    s, _ = setup
    writes, attempts, inbound = [], [], queue.Queue()
    reads = []

    class Fake:
        def __init__(self, *args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise serial.SerialException("disconnect")
            self.buffer = b""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def in_waiting(self):
            return len(self.buffer)

        def read(self, n):
            reads.append((self.in_waiting, n))
            if not self.buffer:
                try:
                    self.buffer = inbound.get(timeout=0.01)
                except queue.Empty:
                    return b""
            chunk, self.buffer = self.buffer[:n], self.buffer[n:]
            return chunk

        def write(self, data):
            writes.append(json.loads(data))

    def send(*frames, raw=b""):
        inbound.put(b"".join(f.model_dump_json().encode() + b"\n" for f in frames) + raw)

    def wait(predicate):
        deadline = time.time() + 5
        while not predicate() and time.time() < deadline:
            time.sleep(0.02)
        assert predicate()

    gateway = SerialGateway(s, "fake", factory=Fake)
    gateway.start()
    try:
        bill = event(category="BILL")
        send(bill)
        wait(lambda: len(writes) >= 1)
        assert writes[0]["message_type"] == "CALL_RECEIPT"
        assert writes[0]["event_id"] == bill.event_id
        assert (writes[0]["venue_id"], writes[0]["payload"]["category"]) == (1, "BILL")
        r = s.snapshot()["requests"][0]
        s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
        poll = staff_event("STAFF_POLL")
        send(poll)
        wait(lambda: len(writes) >= 2)
        assert (writes[1]["message_type"], writes[1]["node_id"]) == ("DISPATCH", 101)
        assert writes[1]["event_id"] == poll.event_id
        send(event(node_id=2, venue_id=9), raw=b"garbage\n")
        wait(lambda: len(writes) >= 3 and gateway.parser_errors == 1)
        assert writes[2]["message_type"] == "ERROR"
        assert writes[2]["payload"]["reason"] == "wrong_venue"
    finally:
        gateway.stop()
    assert len(attempts) >= 2 and gateway.status()["frames_in"] == 3
    assert (0, 1) in reads and any(1 < size == waiting < 1024 for waiting, size in reads)
    assert len(s.snapshot()["requests"]) == 1
    reasons = [e["reason"] for e in s.event_log(kind="FAILURE", ascending=True)["items"]]
    assert reasons[0] == "gateway_disconnected:disconnect"
    assert "CALL:wrong_venue" in reasons
    assert any(x.startswith("gateway_malformed_frame") for x in reasons)
    assert "GATEWAY_CONNECTED" in kinds(s)
