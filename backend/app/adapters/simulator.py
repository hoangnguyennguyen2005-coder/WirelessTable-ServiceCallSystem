"""Simulated table units behind a simulated gateway link.

Every simulated frame goes through Service.exchange, the same path the serial gateway uses.
The node model follows the logbook table unit (Step 5 Level 2): two guest controls held 5 s,
a recessed completion control pressed twice, and these indications (Step 6 §6.3, proposed and
still subject to the ER-U02 user trials):

    hold         flashing red while a guest control is held
    pending      registration sent, no confirmation yet (< 5 s)
    red          steady red, only after the centre confirmed durable registration
    green        steady green, only after the manager acknowledgement reached the table
    unconfirmed  repeated double-red flash: registration unconfirmed or contact lost
    completing   alternating red/green: completion sent, not yet confirmed by the centre
    reconciling  restarted node asking the centre before it admits a new request
    off          idle, sleeping (no heartbeat)
"""

import threading
import time
from uuid import uuid4

from app.adapters.staff import VirtualStaffHub
from app.domain.models import (
    HOLD_SECONDS,
    REGISTRATION_SECONDS,
    DeviceEvent,
    DomainError,
)


class DemoClock:
    def __init__(self):
        self.offset = 0.0

    def __call__(self):
        return time.time() + self.offset


def session():
    return int(uuid4().hex[:8], 16)


class Simulator:
    def __init__(self, service, poll_seconds=5, double_ms=1000, staff_poll_seconds=2):
        self.service = service
        self.poll_seconds, self.double_ms = poll_seconds, double_ms
        self.retry_seconds = 1.0
        self.connected = True
        self.nodes = {}
        self.fault = "none"
        self.fault_node = None  # None: the next frame from any table
        self.delay = 0
        self.lock = threading.RLock()
        self.staff = VirtualStaffHub(service, staff_poll_seconds, "simulator")
        # Rehydrate only active requests: nodes kept their session and reconcile by polling.
        now = service.clock()
        for r in service.snapshot()["requests"]:
            c = service.store.read(
                "SELECT * FROM correlations WHERE request_id=? ORDER BY rowid DESC LIMIT 1",
                (r["id"],),
            )[0]
            try:
                n = self.node(c["node_id"])
            except DomainError:
                continue
            n.update(
                boot_id=c["boot_id"],
                call_token=c["call_token"],
                request_id=r["id"],
                category=r["category"],
                phase="active",
                attempt_at=now,
                last_ok=now,
            )

    def node(self, node_id):
        if not self.service.store.read(
            "SELECT id FROM tables WHERE node_id=? AND enabled=1", (node_id,)
        ):
            raise DomainError("Bàn không tồn tại hoặc bị tắt", 422)
        if node_id not in self.nodes:
            self.nodes[node_id] = dict(
                node_id=node_id,
                boot_id=session(),
                call_token=0,
                request_id=None,
                category=None,
                led="OFF",
                revision=0,
                phase="sleep",
                hold_at=None,
                hold_category=None,
                press_at=None,
                pending=None,
                next_poll=0.0,
                attempt_at=None,
                last_ok=None,
                applied=None,
                battery_low=False,
                battery_mv=None,
                error=None,
            )
        return self.nodes[node_id]

    # ------------------------------------------------------------ guest controls
    def press(self, node_id, down, category="SERVICE"):
        with self.lock:
            n = self.node(node_id)
            if down:
                # ER-F06: a hold while a request is active or unresolved creates nothing.
                # The first control held wins; a second control pressed meanwhile is ignored.
                if n["phase"] == "sleep":
                    n.update(
                        phase="holding",
                        hold_at=self.service.clock(),
                        hold_category=category,
                        error=None,
                    )
            elif n["phase"] == "holding" and n["hold_category"] == category:
                # Evaluate elapsed time before the release so an exact 5 s hold counts.
                self.tick()
                if n["phase"] == "holding":
                    n.update(phase="sleep", hold_at=None, hold_category=None)
            return dict(n)

    def hidden_press(self, node_id):
        """Recessed staff control: two presses inside the window complete the active request."""
        with self.lock:
            n, now = self.node(node_id), self.service.clock()
            if n["phase"] != "active" or n["request_id"] is None:
                # ER-F09: no registered active request, no completion event.
                n["press_at"] = None
            elif (
                n["press_at"] is not None
                and 0 <= now - n["press_at"] <= self.double_ms / 1000
            ):
                n.update(
                    press_at=None,
                    pending="DONE",
                    phase="completing",
                    attempt_at=now,
                    next_poll=now,
                )
                self.tick()
            else:
                n["press_at"] = now
            return dict(n)

    def restart(self, node_id):
        """Power cycle or battery replacement: RAM is lost, the node reconciles first (ER-F05)."""
        with self.lock:
            n, now = self.node(node_id), self.service.clock()
            n.update(
                boot_id=session(),
                request_id=None,
                category=None,
                led="OFF",
                revision=0,
                phase="reconciling",
                hold_at=None,
                hold_category=None,
                press_at=None,
                pending="NODE_HELLO",
                next_poll=now,
                attempt_at=now,
                last_ok=None,
                applied=None,
                error=None,
            )
            self.tick()
            return dict(n)

    def battery(self, node_id, low):
        """Simulated telemetry only; not a measured cell voltage."""
        with self.lock:
            n = self.node(node_id)
            n.update(battery_low=low, battery_mv=2150 if low else 3000)
            self.exchange(n, "DEVICE_STATUS")
            return dict(n)

    # ------------------------------------------------------------------ transport
    def exchange(self, n, kind):
        """One radio/USB round trip. True only when an application-level reply arrived."""
        now = self.service.clock()
        payload = {}
        if kind == "CALL":
            payload["category"] = n["category"]
        if n["battery_mv"] is not None:
            payload.update(battery_mv=n["battery_mv"], battery_low=n["battery_low"])
        event = DeviceEvent(
            venue_id=self.service.venue_id,
            message_type=kind,
            event_id=str(uuid4()),
            node_id=n["node_id"],
            boot_id=n["boot_id"],
            call_token=n["call_token"],
            request_id=None
            if kind in ("NODE_HELLO", "DEVICE_STATUS")
            else n["request_id"],
            payload=payload,
        )
        if not self.connected:
            return False
        # A fault armed for one table must not be used up by another table's routine poll.
        fault = (
            self.fault
            if self.fault_node is None or self.fault_node == n["node_id"]
            else "none"
        )
        if fault != "none":
            self.fault, self.fault_node = "none", None
        if fault == "drop_event":
            return False
        frames = self.service.exchange(event, "simulator")
        if fault == "duplicate":
            frames = self.service.exchange(event, "simulator")
        if fault == "drop_receipt":
            return False
        replied = False
        for frame in frames:
            if frame["node_id"] != n["node_id"]:
                continue
            replied = True
            if frame["message_type"] == "ERROR":
                n["error"] = frame["payload"]["reason"]
                if kind == "DONE":
                    n.update(pending=None, phase="active")
                continue
            self.apply(n, frame)
        if replied:
            n["last_ok"] = now
        return replied

    def apply(self, n, frame):
        payload = frame["payload"]
        if (
            frame.get("boot_id") != n["boot_id"]
            or frame.get("call_token") != n["call_token"]
        ):
            return  # another session or another call: never applied
        if frame["request_id"] is None:
            # Centre holds no active request for this table (answer to NODE_HELLO).
            if n["phase"] == "reconciling":
                n.update(
                    phase="sleep",
                    pending=None,
                    led="OFF",
                    request_id=None,
                    category=None,
                    error=None,
                )
            return
        if payload["revision"] < n["revision"]:
            return
        closed = frame["message_type"] == "DONE_RECEIPT" or payload["led"] == "OFF"
        if closed:
            n.update(
                request_id=frame["request_id"],
                revision=payload["revision"],
                led="OFF",
                phase="sleep",
                pending=None,
                hold_at=None,
                press_at=None,
                error=None,
            )
        elif n["phase"] == "completing":
            # ER-F10: only the centre's completion confirmation ends a pending completion.
            n.update(revision=payload["revision"], led=payload["led"])
            return
        else:
            n.update(
                request_id=frame["request_id"],
                revision=payload["revision"],
                led=payload["led"],
                category=payload.get("category") or n["category"],
                phase="active",
                pending=None,
                error=None,
            )
        state = (frame["request_id"], payload["revision"], payload["led"])
        if n["applied"] != state:
            n["applied"] = state
            try:
                self.service.event(
                    DeviceEvent(
                        venue_id=self.service.venue_id,
                        message_type="STATUS_APPLIED",
                        event_id=str(uuid4()),
                        node_id=n["node_id"],
                        boot_id=n["boot_id"],
                        call_token=n["call_token"],
                        request_id=frame["request_id"],
                        payload=dict(led=payload["led"], revision=payload["revision"]),
                    ),
                    "simulator",
                )
            except DomainError as error:
                n["error"] = error.reason
                n["applied"] = None
        if closed:
            n["category"] = None

    def tick(self):
        with self.lock:
            now = self.service.clock()
            for n in list(self.nodes.values()):
                if n["phase"] == "holding" and now - n["hold_at"] >= HOLD_SECONDS:
                    # Exactly one attempt per valid hold; continued holding adds nothing.
                    n.update(
                        phase="registering",
                        category=n["hold_category"],
                        call_token=(n["call_token"] + 1) % 4294967296,
                        request_id=None,
                        revision=0,
                        led="OFF",
                        applied=None,
                        pending="CALL",
                        attempt_at=now,
                        next_poll=now + self.delay,
                        hold_at=None,
                        hold_category=None,
                    )
                if (n["pending"] or n["phase"] == "active") and now >= n["next_poll"]:
                    self.exchange(n, n["pending"] or "STATUS_POLL")
                    # A transaction that is still unresolved retries quickly inside the 5 s
                    # outcome window, then falls back to the active poll period. Once it is
                    # confirmed the node polls at the normal period; idle nodes never transmit.
                    urgent = (
                        n["pending"] is not None
                        and now - n["attempt_at"] < REGISTRATION_SECONDS
                    )
                    n["next_poll"] = now + (
                        self.retry_seconds if urgent else self.poll_seconds
                    )
            self.staff.tick(self.connected)

    # ------------------------------------------------------------------ reporting
    def pattern(self, n, now):
        phase, unresolved = n["phase"], self.service.unresolved_seconds
        if phase == "holding":
            return "hold"
        if phase == "registering":
            fresh = now - n["attempt_at"] < REGISTRATION_SECONDS
            return "pending" if fresh and not n["error"] else "unconfirmed"
        if phase == "reconciling":
            return "reconciling" if now - n["attempt_at"] < unresolved else "unconfirmed"
        if phase == "completing":
            return "completing"
        if phase == "active":
            if n["last_ok"] is not None and now - n["last_ok"] >= unresolved:
                return "unconfirmed"  # contact lost; the stored state is kept for recovery
            return {"RED": "red", "GREEN": "green"}.get(n["led"], "reconciling")
        return "off"

    def public(self, n, now):
        return dict(
            node_id=n["node_id"],
            phase=n["phase"],
            pattern=self.pattern(n, now),
            led=n["led"],
            category=n["category"] or n["hold_category"],
            hold_at=n["hold_at"],
            request_id=n["request_id"],
            pending=n["pending"],
            press_armed=n["press_at"] is not None
            and now - n["press_at"] <= self.double_ms / 1000,
            battery_low=n["battery_low"],
            error=n["error"],
        )

    def reset(self):
        with self.lock:
            self.nodes.clear()
            self.staff.reset()
            self.fault, self.fault_node, self.delay, self.connected = "none", None, 0, True

    def snapshot(self):
        with self.lock:
            self.tick()  # settle due exchanges first so time-based patterns do not flicker
            now = self.service.clock()
            return dict(
                connected=self.connected,
                fault=self.fault,
                fault_node=self.fault_node,
                delay=self.delay,
                poll_seconds=self.poll_seconds,
                double_ms=self.double_ms,
                nodes=[self.public(n, now) for n in self.nodes.values()],
                staff_devices=self.staff.snapshot(),
            )
