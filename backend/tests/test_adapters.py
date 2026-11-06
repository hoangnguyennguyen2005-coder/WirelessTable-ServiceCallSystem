import json
from app.adapters.serial_gateway import FrameParser, SerialGateway
from app.adapters.simulator import Simulator
from test_domain import event


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


def test_hold_cancel_exact5_and_idle_no_polls(setup):
    s, c = setup
    sim = Simulator(s)
    sim.press(1, True)
    c.now += 4.9
    sim.press(1, False)
    assert not s.snapshot()["requests"]
    sim.press(1, True)
    c.now += 5
    sim.press(1, False)
    assert len(s.snapshot()["requests"]) == 1
    assert sim.node(1)["led"] == "RED"
    sim.tick()
    assert len(s.snapshot()["requests"]) == 1
    assert 2 not in sim.nodes  # sleeping nodes have no heartbeat


def test_lost_call_and_done_receipt_duplicate_reconnect(setup):
    from test_domain import act

    s, c = setup
    sim = Simulator(s)
    sim.fault = "drop_receipt"
    sim.press(1, True)
    c.now += 5
    sim.tick()
    assert sim.node(1)["phase"] == "sending" and sim.node(1)["led"] == "OFF"
    sim.connected = False
    c.now += 5
    sim.tick()
    assert sim.node(1)["phase"] == "sending"
    sim.connected = True
    sim.fault = "duplicate"
    sim.tick()
    assert sim.node(1)["led"] == "RED"
    r = s.snapshot()["requests"][0]
    s.action(r["id"], "ack", act(1))
    c.now += 5
    sim.tick()
    assert sim.node(1)["led"] == "GREEN"
    sim.fault = "drop_receipt"
    sim.hidden_press(1)
    c.now += 0.1
    sim.hidden_press(1)
    assert not s.snapshot()["requests"] and sim.node(1)["led"] == "GREEN"
    c.now += 5
    sim.tick()
    assert sim.node(1)["led"] == "OFF" and sim.node(1)["phase"] == "sleep"


def test_command_backoff_limit_expiry_restart(setup):
    from app.domain.service import Service
    from app.db.store import Store

    s, c = setup
    s.event(event())
    for i in range(5):
        commands = s.commands(1)
        assert len(commands) == 1
        assert not s.commands(1)
        c.now += 2**i
    assert not s.commands(1)
    assert s.store.read("SELECT status FROM outbox")[0]["status"] == "failed"
    s.event(event("STATUS_POLL"))
    s = Service(Store(s.store.path), c)
    assert s.commands(1)
    c.now += 121
    assert not s.commands(1)
    assert any(
        x["status"] == "expired" for x in s.store.read("SELECT status FROM outbox")
    )


def test_real_serial_worker_reconnect_fake_transport(setup):
    import time
    import serial

    s, _ = setup
    writes, attempts = [], []

    class Fake:
        def __init__(self, *args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise serial.SerialException("disconnect")
            self.read_once = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n):
            if not self.read_once:
                self.read_once = True
                return event().model_dump_json().encode() + b"\n"
            time.sleep(0.01)
            return b""

        def write(self, data):
            writes.append(json.loads(data))

    gateway = SerialGateway(s, "fake", factory=Fake)
    gateway.start()
    deadline = time.time() + 3
    while not writes and time.time() < deadline:
        time.sleep(0.02)
    gateway.stop()
    assert len(attempts) >= 2
    assert writes[0]["message_type"] == "CALL_RECEIPT"
    assert len(s.snapshot()["requests"]) == 1


def test_lost_event_delay_and_cancel_restart_rehydration(setup):
    s, c = setup
    sim = Simulator(s)
    sim.delay = 2
    sim.fault = "drop_event"
    sim.press(1, True)
    c.now += 5
    sim.tick()
    assert sim.node(1)["phase"] == "sending"
    assert not s.snapshot()["requests"]
    c.now += 2
    sim.tick()  # lost event, no false red success
    assert not s.snapshot()["requests"] and sim.node(1)["led"] == "OFF"
    c.now += 5
    sim.tick()
    assert len(s.snapshot()["requests"]) == 1
    restored = Simulator(s)
    assert restored.node(1)["phase"] == "sending"
    restored.tick()
    assert restored.node(1)["led"] == "RED"
