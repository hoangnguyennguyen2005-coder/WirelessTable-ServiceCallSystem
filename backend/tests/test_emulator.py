"""Shipped gateway emulator against the real serial worker (USB protocol v2).

The loopback check drives the emulator class in-process, so the table-node and staff-device
round trips are exercised on every platform. The PTY check additionally runs the emulator as
a separate process over a real pseudo-terminal and pyserial; it needs Linux.
"""

import importlib.util
import os
import queue
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.adapters.serial_gateway import SerialGateway
from helpers import act, kinds

ROOT = Path(__file__).resolve().parents[2]


def wait(predicate, seconds=7):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert predicate()


def load_emulator():
    spec = importlib.util.spec_from_file_location(
        "serial_emulator", ROOT / "tools" / "serial_emulator.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_emulator_loopback_table_and_staff_round_trip(setup):
    s, _ = setup
    to_pc, lines = queue.Queue(), []
    emulator = load_emulator().GatewayEmulator(
        to_pc.put,
        poll_seconds=0.2,
        staff_poll_seconds=0.1,
        log=lambda *parts: lines.append(" ".join(map(str, parts))),
    )

    class Loop:
        """In-process stand-in for the serial port between the PC adapter and the emulator."""

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n):
            emulator.tick()
            try:
                return to_pc.get(timeout=0.02)
            except queue.Empty:
                return b""

        def write(self, data):
            emulator.feed(data)

    gateway = SerialGateway(s, "loop", factory=Loop)
    gateway.start()
    try:
        for line in ("bad", "oversized", "fragment 1 bill"):
            emulator.command(line)
        wait(lambda: len(s.snapshot()["requests"]) == 1)
        r = s.snapshot()["requests"][0]
        assert r["category"] == "BILL"
        wait(lambda: s.snapshot()["tables"][0]["led"] == "RED")
        r = s.action(r["id"], "ack", act(r["version"]))
        wait(lambda: s.snapshot()["tables"][0]["led"] == "GREEN")  # on the node's next poll

        emulator.command("staff 101 on")
        r = s.action(r["id"], "dispatch", act(r["version"], staff_id=1))
        wait(lambda: s.detail(r["id"])["request"]["delivered_at"] is not None)
        assert s.detail(r["id"])["request"]["accepted_at"] is None  # shown, not accepted
        emulator.command("accept 101")
        wait(lambda: s.detail(r["id"])["request"]["accepted_at"] is not None)
        wait(lambda: emulator.staff[101]["tasks"][r["id"]]["state"] == "ACCEPTED")

        emulator.command("venue 2")  # a frame of another venue must not be mixed in
        emulator.command("poll 2")
        wait(lambda: any("wrong_venue" in line for line in lines))
        emulator.command("venue 1")
        emulator.command("battery 1 2150 low")
        wait(lambda: s.snapshot()["tables"][0]["battery_low"] == 1)
        assert len(s.snapshot()["requests"]) == 1

        emulator.command("done 1")
        wait(lambda: not s.snapshot()["requests"])
        wait(lambda: s.snapshot()["tables"][0]["led"] == "OFF")
        wait(lambda: emulator.staff[101]["tasks"] == {})  # closed task leaves the device
        assert gateway.parser_errors >= 2
    finally:
        gateway.stop()
    # While the emulated gateway claimed venue 2, all of its frames were refused and recorded.
    failures = {e["reason"] for e in s.event_log(kind="FAILURE", limit=200)["items"]}
    assert failures and all(
        reason.endswith(":wrong_venue") or reason.startswith("gateway_malformed_frame")
        for reason in failures
    )
    assert [k for k in kinds(s, r["id"]) if k != "FAILURE"] == [
        "REGISTERED",
        "ACKNOWLEDGED",
        "DISPATCHED",
        "DELIVERED",
        "ACCEPTED",
        "COMPLETED",
    ]


@pytest.mark.skipif(os.name != "posix", reason="PTY is a Linux software check")
def test_shipped_emulator_real_pty(setup):
    s, _ = setup
    process = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "tools/serial_emulator.py"), "--pty"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    gateway = None
    try:
        line = process.stdout.readline()
        assert "EMULATED GATEWAY PC PORT:" in line
        port = line.strip().split(": ", 1)[1]
        gateway = SerialGateway(s, port)
        gateway.start()
        process.stdin.write("bad\noversized\nfragment 1 bill\n")
        process.stdin.flush()
        wait(lambda: len(s.snapshot()["requests"]) == 1)
        r = s.snapshot()["requests"][0]
        assert r["category"] == "BILL"
        s.action(r["id"], "ack", act(1))
        wait(lambda: s.snapshot()["tables"][0]["led"] == "GREEN")
        process.stdin.write("done 1\n")
        process.stdin.flush()
        wait(lambda: not s.snapshot()["requests"])
        wait(lambda: s.snapshot()["tables"][0]["led"] == "OFF")
        assert gateway.parser_errors >= 2
    finally:
        if gateway:
            gateway.stop()
        process.terminate()
        process.communicate(timeout=3)
