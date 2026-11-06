import threading
import time
from uuid import uuid4
from app.domain.models import DeviceEvent, DomainError


class DemoClock:
    def __init__(self):
        self.offset = 0.0

    def __call__(self):
        return time.time() + self.offset


class Simulator:
    def __init__(self, service, poll_seconds=5, double_ms=600):
        self.service, self.poll_seconds, self.double_ms = (
            service,
            poll_seconds,
            double_ms,
        )
        self.connected = True
        self.nodes = {}
        self.fault = "none"
        self.delay = 0
        self.lock = threading.RLock()
        # Rehydrate only active correlations; no demo reset on restart.
        for r in service.snapshot()["requests"]:
            c = service.store.read(
                "SELECT * FROM correlations WHERE request_id=? LIMIT 1", (r["id"],)
            )[0]
            n = self.node(c["node_id"])
            n.update(
                boot_id=c["boot_id"],
                call_token=c["call_token"],
                request_id=r["id"],
                phase="sending",
                pending="CALL",
            )

    def node(self, node_id):
        if not self.service.store.read(
            "SELECT id FROM tables WHERE node_id=? AND enabled=1", (node_id,)
        ):
            raise DomainError("Bàn không tồn tại hoặc bị tắt", 422)
        if node_id not in self.nodes:
            self.nodes[node_id] = dict(
                node_id=node_id,
                boot_id=int(uuid4().hex[:8], 16),
                call_token=0,
                request_id=None,
                led="OFF",
                phase="sleep",
                hold_at=None,
                press_at=None,
                pending=None,
                next_poll=0,
                revision=0,
            )
        return self.nodes[node_id]

    def press(self, node_id, down):
        with self.lock:
            n = self.node(node_id)
            if down and n["phase"] == "sleep":
                n.update(phase="holding", hold_at=self.service.clock())
            elif not down and n["phase"] == "holding":
                # Evaluate elapsed before release so an exact 5s release counts.
                self.tick()
                if n["phase"] == "holding":
                    n.update(phase="sleep", hold_at=None, led="OFF")
            return dict(n)

    def hidden_press(self, node_id):
        with self.lock:
            n, now = self.node(node_id), self.service.clock()
            if (
                n["press_at"] is not None
                and 0 <= now - n["press_at"] <= self.double_ms / 1000
            ):
                n.update(press_at=None, pending="DONE", next_poll=now)
                self.tick()
            else:
                n["press_at"] = now
            return dict(n)

    def send(self, n, kind):
        event = DeviceEvent(
            message_type=kind,
            event_id=str(uuid4()),
            node_id=n["node_id"],
            boot_id=n["boot_id"],
            call_token=n["call_token"],
            request_id=n["request_id"],
        )
        if self.fault == "drop_event":
            self.fault = "none"
            return
        result = self.service.event(event, "simulator")
        if self.fault == "duplicate":
            self.fault = "none"
            self.service.event(event, "simulator")
        commands = self.service.commands(n["node_id"])
        if self.fault == "drop_receipt":
            self.fault = "none"
            return
        for command in commands:
            # Node only accepts its own session/token and nondecreasing revision.
            if (
                command["boot_id"] != n["boot_id"]
                or command["call_token"] != n["call_token"]
                or command["payload"]["revision"] < n["revision"]
            ):
                continue
            payload = command["payload"]
            n.update(
                request_id=command["request_id"],
                revision=payload["revision"],
                led=payload["led"],
            )
            if command["message_type"] == "DONE_RECEIPT" or payload["led"] == "OFF":
                n.update(phase="sleep", pending=None, hold_at=None)
            else:
                n.update(phase="active", pending=None)
            applied = DeviceEvent(
                message_type="STATUS_APPLIED",
                event_id=str(uuid4()),
                node_id=n["node_id"],
                boot_id=n["boot_id"],
                call_token=n["call_token"],
                request_id=n["request_id"],
                payload=payload,
            )
            self.service.event(applied, "simulator")
        return result

    def tick(self):
        with self.lock:
            now = self.service.clock()
            for n in self.nodes.values():
                if n["phase"] == "holding" and now - n["hold_at"] >= 5:
                    n.update(
                        phase="sending",
                        led="OFF",
                        call_token=(n["call_token"] + 1) % 4294967296,
                        request_id=None,
                        revision=0,
                        pending="CALL",
                        next_poll=now + self.delay,
                    )
                if (
                    self.connected
                    and (n["pending"] or n["phase"] == "active")
                    and now >= n["next_poll"]
                ):
                    n["next_poll"] = now + self.poll_seconds
                    try:
                        self.send(n, n["pending"] or "STATUS_POLL")
                    except DomainError as error:
                        n["error"] = error.reason
                        if n["pending"] == "DONE":
                            n["pending"] = None

    def snapshot(self):
        with self.lock:
            return dict(
                connected=self.connected,
                nodes=[dict(n) for n in self.nodes.values()],
                fault=self.fault,
                poll_seconds=self.poll_seconds,
                double_ms=self.double_ms,
                delay=self.delay,
            )
