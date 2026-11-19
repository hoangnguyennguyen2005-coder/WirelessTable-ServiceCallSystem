"""Software gateway emulator for the USB NDJSON protocol v2 (docs/protocol.md).

It stands in for the ESP32-C3 + nRF24L01+ gateway with emulated table nodes and staff devices,
so the PC adapter can be exercised without hardware. Everything it prints is labelled EMULATED;
it makes no firmware, RF range or timing claim.

Transports:  --pty  (Linux/WSL: prints the slave path to use as PBL_SERIAL_PORT)
             --port COMx or /dev/...  (other end of a virtual serial pair, e.g. com0com)

Commands (one per line on stdin):
  call N [service|bill]     hold completed on table node N: send CALL
  done N                    recessed double press on node N: send DONE
  poll N                    one STATUS_POLL from node N
  hello N                   node N restarted: new session, NODE_HELLO reconcile
  battery N MV [low]        DEVICE_STATUS telemetry from node N
  staff D on|off            power staff device D (polls every 2 s while on)
  accept D [SEQ]            accept the oldest shown task on device D (or request SEQ)
  fragment N [service|bill] CALL split across two writes
  duplicate | bad | oversized   resend last frame / malformed line / line over 4096 bytes
  venue V                   change the venue id sent in frames (cross-venue rejection test)
  quit
"""

import argparse
import json
import os
import queue
import sys
import threading
import time
from uuid import uuid4

PROTOCOL_VERSION = 2
CATEGORIES = {"service": "SERVICE", "bill": "BILL"}
STAFF_FRAMES = ("DISPATCH", "ACCEPT_RECEIPT", "DISPATCH_CANCEL", "STAFF_STATUS")


def session():
    return int(uuid4().hex[:8], 16)


class GatewayEmulator:
    """Emulated endpoints behind one serial link. write() receives bytes for the PC."""

    def __init__(
        self,
        write,
        venue_id=1,
        apply=True,
        poll_seconds=5,
        staff_poll_seconds=2,
        clock=time.monotonic,
        log=None,
    ):
        self.write, self.venue_id, self.apply = write, venue_id, apply
        self.poll_seconds, self.staff_poll_seconds = poll_seconds, staff_poll_seconds
        self.clock = clock
        self.log = log or (lambda *parts: print(*parts, flush=True))
        self.nodes, self.staff = {}, {}
        self.buffer, self.previous = bytearray(), b""
        self.lock = threading.RLock()

    def node(self, number):
        return self.nodes.setdefault(
            number,
            dict(
                boot=session(),
                token=0,
                request_id=None,
                category="SERVICE",
                active=False,
                pending=None,
                next_at=0.0,
                applied=None,
            ),
        )

    def device(self, number):
        return self.staff.setdefault(
            number, dict(boot=session(), on=False, tasks={}, next_at=0.0)
        )

    def frame(self, kind, number, boot, token=0, request_id=None, payload=None):
        return dict(
            protocol_version=PROTOCOL_VERSION,
            venue_id=self.venue_id,
            message_type=kind,
            event_id=str(uuid4()),
            node_id=number,
            boot_id=boot,
            call_token=token,
            request_id=request_id,
            payload=payload or {},
        )

    def emit(self, data, fragment=False):
        self.previous = (json.dumps(data) + "\n").encode()
        if fragment:
            self.write(self.previous[:17])
            time.sleep(0.05)
            self.write(self.previous[17:])
        else:
            self.write(self.previous)
        self.log("EMULATED ->", data["message_type"], data["node_id"])

    def send(self, kind, number, payload=None, fragment=False):
        n = self.node(number)
        request_id = None if kind in ("NODE_HELLO", "DEVICE_STATUS") else n["request_id"]
        self.emit(
            self.frame(kind, number, n["boot"], n["token"], request_id, payload),
            fragment,
        )

    def send_staff(self, kind, number, request_id=None, payload=None):
        d = self.device(number)
        self.emit(self.frame(kind, number, d["boot"], 0, request_id, payload))

    # ----------------------------------------------------------------- commands
    def command(self, line):
        """Run one operator command. Returns False when the emulator should stop."""
        with self.lock:
            parts = line.strip().split()
            if not parts:
                return True
            action, args = parts[0].lower(), parts[1:]
            if action == "quit":
                return False
            try:
                self.run(action, args)
            except (ValueError, IndexError, KeyError) as error:
                self.log("EMULATED: bad command:", line.strip(), "-", error)
            return True

    def run(self, action, args):
        now = self.clock()
        if action in ("call", "fragment"):
            number = int(args[0]) if args else 1
            n = self.node(number)
            if not n["active"]:
                n.update(
                    token=n["token"] + 1,
                    request_id=None,
                    active=True,
                    pending="CALL",
                    applied=None,
                    category=CATEGORIES[args[1].lower()] if len(args) > 1 else "SERVICE",
                )
            self.send("CALL", number, dict(category=n["category"]), action == "fragment")
            n["next_at"] = now + self.poll_seconds
        elif action == "done":
            number = int(args[0]) if args else 1
            n = self.node(number)
            n["pending"] = "DONE"
            self.send("DONE", number)
            n["next_at"] = now + self.poll_seconds
        elif action == "poll":
            number = int(args[0]) if args else 1
            self.send("STATUS_POLL", number)
            self.node(number)["next_at"] = now + self.poll_seconds
        elif action == "hello":
            number = int(args[0]) if args else 1
            n = self.node(number)
            n.update(
                boot=session(),
                request_id=None,
                active=True,
                pending="NODE_HELLO",
                applied=None,
            )
            self.send("NODE_HELLO", number)
            n["next_at"] = now + self.poll_seconds
        elif action == "battery":
            payload = dict(battery_mv=int(args[1]))
            if len(args) > 2:
                payload["battery_low"] = args[2].lower() == "low"
            self.send("DEVICE_STATUS", int(args[0]), payload)
        elif action == "staff":
            d = self.device(int(args[0]))
            on = args[1].lower() == "on"
            if on and not d["on"]:
                d.update(boot=session(), tasks={}, next_at=now)
            d["on"] = on
        elif action == "accept":
            number = int(args[0])
            d = self.device(number)
            shown = [
                task
                for task in sorted(d["tasks"].values(), key=lambda t: t["request_seq"])
                if task["state"] == "SHOWN"
                and (len(args) < 2 or task["request_seq"] == int(args[1]))
            ]
            if not shown:
                self.log("EMULATED STAFF", number, ": no shown task to accept")
                return
            task = shown[0]
            self.send_staff(
                "STAFF_ACCEPT",
                number,
                task["request_id"],
                dict(
                    assignment_revision=task["revision"],
                    request_seq=task["request_seq"],
                ),
            )
        elif action == "duplicate":
            if self.previous:
                self.write(self.previous)
        elif action == "bad":
            self.write(b"not-json\n")
        elif action == "oversized":
            self.write(b"x" * 5000 + b"\n")
        elif action == "venue":
            self.venue_id = int(args[0])
        else:
            raise ValueError("unknown command")

    # ------------------------------------------------------------ frames from PC
    def feed(self, data):
        with self.lock:
            self.buffer.extend(data)
            if len(self.buffer) > 16384:
                self.buffer.clear()
                self.log("EMULATED: response buffer overflow")
            while b"\n" in self.buffer:
                line, _, remainder = bytes(self.buffer).partition(b"\n")
                self.buffer = bytearray(remainder)
                try:
                    frame = json.loads(line)
                    self.log("PC ->", json.dumps(frame, ensure_ascii=True))
                    self.handle(frame)
                except (ValueError, KeyError, TypeError) as error:
                    self.log("EMULATED malformed PC response:", str(error))

    def handle(self, frame):
        kind = frame["message_type"]
        if kind == "ERROR":
            return
        number, payload = frame["node_id"], frame["payload"]
        if kind in STAFF_FRAMES:
            self.handle_staff(kind, number, frame, payload)
            return
        n = self.node(number)
        if frame.get("boot_id") != n["boot"] or frame.get("call_token") != n["token"]:
            return  # another session or call
        if frame["request_id"] is None:
            n.update(active=False, pending=None)  # centre holds no active request
            return
        n["request_id"] = frame["request_id"]
        if kind == "DONE_RECEIPT" or payload["led"] == "OFF":
            n.update(active=False, pending=None)
        elif n["pending"] != "DONE":
            n["pending"] = None
        state = (frame["request_id"], payload["revision"], payload["led"])
        if self.apply and n["applied"] != state:
            n["applied"] = state
            self.send(
                "STATUS_APPLIED",
                number,
                dict(led=payload["led"], revision=payload["revision"]),
            )

    def handle_staff(self, kind, number, frame, payload):
        d = self.device(number)
        if kind == "STAFF_STATUS" or not d["on"]:
            return
        request_id, revision = frame["request_id"], payload["assignment_revision"]
        task = d["tasks"].get(request_id)
        if kind == "DISPATCH_CANCEL":
            if task and task["revision"] <= revision:
                del d["tasks"][request_id]
                self.log("EMULATED STAFF", number, ": task cleared seq", task["request_seq"])
            state = "CLEARED"
        else:
            if task and task["revision"] > revision:
                return
            accepted = kind == "ACCEPT_RECEIPT"
            if task is None or task["revision"] != revision:
                task = dict(
                    request_id=request_id,
                    request_seq=payload["request_seq"],
                    revision=revision,
                    state="ACCEPTED" if accepted else "SHOWN",
                )
                d["tasks"][request_id] = task
                self.log(
                    "EMULATED STAFF",
                    number,
                    ": table",
                    payload["table_id"],
                    payload["category"],
                    "seq",
                    payload["request_seq"],
                    "(vibrate)" if not accepted else "(accepted)",
                )
            elif accepted:
                task["state"] = "ACCEPTED"
            state = task["state"]
        self.send_staff(
            "STAFF_APPLIED",
            number,
            request_id,
            dict(assignment_revision=revision, task=state),
        )

    def tick(self):
        with self.lock:
            now = self.clock()
            for number, n in self.nodes.items():
                if n["active"] and now >= n["next_at"]:
                    kind = n["pending"] or "STATUS_POLL"
                    self.send(
                        kind,
                        number,
                        dict(category=n["category"]) if kind == "CALL" else None,
                    )
                    n["next_at"] = now + self.poll_seconds
            for number, d in self.staff.items():
                if d["on"] and now >= d["next_at"]:
                    self.send_staff("STAFF_POLL", number)
                    d["next_at"] = now + self.staff_poll_seconds


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--pty", action="store_true", help="Linux: print slave path for PC adapter"
    )
    parser.add_argument("--port", help="Other endpoint of a virtual serial pair")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--venue", type=int, default=1, help="venue_id sent in frames")
    parser.add_argument(
        "--no-apply", action="store_true", help="Do not send STATUS_APPLIED"
    )
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    close = []
    if args.pty:
        import errno
        import pty
        import tty

        master, slave = pty.openpty()
        tty.setraw(slave)
        print(f"EMULATED GATEWAY PC PORT: {os.ttyname(slave)}", flush=True)
        close = [lambda: os.close(master), lambda: os.close(slave)]

        def write(data):
            os.write(master, data)

        def read():
            try:
                return os.read(master, 4096)
            except OSError as error:
                if error.errno == errno.EIO:
                    time.sleep(0.05)  # PC side not open yet or just closed
                    return b""
                raise

    elif args.port:
        import serial

        transport = serial.Serial(args.port, args.baud, timeout=0.1)
        close = [transport.close]
        write = transport.write

        def read():
            return transport.read(4096)

    else:
        parser.error("Use --pty (Linux) or --port COMx (virtual pair)")

    emulator = GatewayEmulator(write, venue_id=args.venue, apply=not args.no_apply)
    inbox, stop = queue.Queue(), threading.Event()

    def pump_serial():
        while not stop.is_set():
            try:
                data = read()
            except OSError:
                break
            if data:
                inbox.put(("serial", data))

    def pump_stdin():
        # Plain blocking reads in a thread work on Windows and on Linux pipes alike.
        for line in sys.stdin:
            inbox.put(("line", line))
        inbox.put(("line", "quit"))

    threading.Thread(target=pump_serial, daemon=True).start()
    threading.Thread(target=pump_stdin, daemon=True).start()
    print(
        "Serial emulator ready. Commands: call 1 [service|bill] | done 1 | poll 1 | hello 1 | "
        "battery 1 2900 [low] | staff 101 on | accept 101 | duplicate | bad | oversized | "
        "fragment 1 | venue 2 | quit",
        flush=True,
    )
    try:
        running = True
        while running:
            try:
                source, item = inbox.get(timeout=0.1)
            except queue.Empty:
                source = None
            if source == "serial":
                emulator.feed(item)
            elif source == "line":
                running = emulator.command(item)
            emulator.tick()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for action in close:
            try:
                action()
            except OSError:
                pass


if __name__ == "__main__":
    main()
