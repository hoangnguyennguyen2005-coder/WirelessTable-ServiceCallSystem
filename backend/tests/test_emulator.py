"""End-to-end real pyserial over Linux PTY to the shipped emulator process."""

import os
import subprocess
import sys
import time
from pathlib import Path
import pytest
from app.adapters.serial_gateway import SerialGateway
from test_domain import act


@pytest.mark.skipif(os.name != "posix", reason="PTY is a Linux software check")
def test_shipped_emulator_real_pty(setup):
    s, _ = setup
    root = Path(__file__).resolve().parents[2]
    process = subprocess.Popen(
        [sys.executable, "-u", str(root / "tools/serial_emulator.py"), "--pty"],
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
        process.stdin.write("bad\noversized\nfragment 1\n")
        process.stdin.flush()

        def wait(predicate):
            deadline = time.monotonic() + 7
            while not predicate() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert predicate()

        wait(lambda: len(s.snapshot()["requests"]) == 1)
        r = s.snapshot()["requests"][0]
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
