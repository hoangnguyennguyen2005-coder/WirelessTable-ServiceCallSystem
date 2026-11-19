"""Staff device boundary.

The product uses a dedicated portable device (logbook C-04/C-06: Pro Mini + nRF24L01+, display,
silent vibration, one accept control) that talks to the centre through the USB radio gateway.
Its firmware is not part of this repository, so this module provides a *virtual* device that
emits exactly the same device events (STAFF_POLL, STAFF_APPLIED, STAFF_ACCEPT) through the same
domain path. It backs the simulator and, when explicitly enabled, a labelled bench stub.

There is deliberately no completion action here: a request is closed only by the recessed
double press at the table (ER-F09).
"""

import threading
from uuid import uuid4

from app.domain.models import DeviceEvent, DomainError


class VirtualStaffDevice:
    def __init__(self, service, staff_id, device_id, poll_seconds=2, source="simulator"):
        self.service, self.source = service, source
        self.staff_id, self.device_id = staff_id, device_id
        self.poll_seconds = poll_seconds
        self.boot_id = int(uuid4().hex[:8], 16)
        self.powered = True
        self.tasks = {}
        self.next_poll = 0.0
        self.last_ok = None
        self.vibrate_at = None
        self.error = None

    def _send(self, kind, request_id=None, **payload):
        event = DeviceEvent(
            venue_id=self.service.venue_id,
            message_type=kind,
            event_id=str(uuid4()),
            node_id=self.device_id,
            boot_id=self.boot_id,
            request_id=request_id,
            payload=payload,
        )
        return self.service.exchange(event, self.source)

    def poll(self, now, link_up=True):
        self.next_poll = now + self.poll_seconds
        if not (self.powered and link_up):
            return
        self.apply(self._send("STAFF_POLL"), now)
        # An acceptance is retried until the centre confirms or cancels it (ER-R03).
        for task in list(self.tasks.values()):
            if task["state"] == "ACCEPTING":
                self._accept(task, now)

    def _accept(self, task, now):
        self.apply(
            self._send(
                "STAFF_ACCEPT",
                task["request_id"],
                assignment_revision=task["revision"],
            ),
            now,
        )

    def apply(self, frames, now):
        for frame in frames:
            if frame["node_id"] != self.device_id:
                continue
            kind, payload = frame["message_type"], frame["payload"]
            if kind == "ERROR":
                self.error = payload["reason"]
                continue
            self.last_ok = now
            if kind == "STAFF_STATUS":
                continue
            request_id, revision = frame["request_id"], payload["assignment_revision"]
            task = self.tasks.get(request_id)
            if kind == "DISPATCH_CANCEL":
                # Reassigned, cancelled or closed tasks must not stay actionable.
                if task and task["revision"] <= revision:
                    del self.tasks[request_id]
                state = "CLEARED"
            elif kind in ("DISPATCH", "ACCEPT_RECEIPT"):
                if task and task["revision"] > revision:
                    continue
                confirmed = kind == "ACCEPT_RECEIPT"
                if task is None or task["revision"] != revision:
                    task = dict(
                        request_id=request_id,
                        request_seq=payload["request_seq"],
                        table_id=payload["table_id"],
                        table_name=payload["table_name"],
                        category=payload["category"],
                        revision=revision,
                        state="ACCEPTED" if confirmed else "SHOWN",
                        shown_at=now,
                    )
                    self.tasks[request_id] = task
                    if not confirmed:
                        self.vibrate_at = now  # repeated frames never create another task
                elif confirmed:
                    task["state"] = "ACCEPTED"
                state = "ACCEPTED" if task["state"] == "ACCEPTED" else "SHOWN"
            else:
                continue
            self.error = None
            self._send(
                "STAFF_APPLIED", request_id, assignment_revision=revision, task=state
            )

    def accept(self, request_id, now, link_up=True):
        """The human pressed accept for the task currently shown."""
        task = self.tasks.get(request_id)
        if not self.powered or task is None:
            raise DomainError("Công việc không còn trên thiết bị", 409)
        if task["state"] == "SHOWN":
            task["state"] = "ACCEPTING"
            if link_up:
                self._accept(task, now)

    def power(self, on, now):
        """Power cycle: RAM is lost, the next boot gets a new session id."""
        if on and not self.powered:
            self.boot_id = int(uuid4().hex[:8], 16)
            self.next_poll = now
        if not on:
            self.tasks.clear()
            self.last_ok = None
            self.vibrate_at = None
        self.powered = on

    def snapshot(self, now):
        return dict(
            staff_id=self.staff_id,
            device_id=self.device_id,
            powered=self.powered,
            source=self.source,
            vibrating=self.vibrate_at is not None and now - self.vibrate_at < 3,
            link_lost=self.powered
            and (
                self.last_ok is None
                or now - self.last_ok > self.service.staff_contact_seconds
            ),
            error=self.error,
            tasks=[
                dict(task)
                for task in sorted(self.tasks.values(), key=lambda t: t["request_seq"])
            ],
        )


class VirtualStaffHub:
    """Virtual devices for staff rows that have a device_id.

    only_staff_id restricts the hub to one member (hardware bench stub).
    """

    def __init__(self, service, poll_seconds=2, source="simulator", only_staff_id=None):
        self.service, self.poll_seconds, self.source = service, poll_seconds, source
        self.only_staff_id = only_staff_id
        self.devices = {}
        self.lock = threading.RLock()
        self.next_sync = float("-inf")

    def sync(self):
        rows = self.service.store.read(
            "SELECT id,device_id FROM staff WHERE active=1 AND device_id IS NOT NULL"
        )
        wanted = {
            row["id"]: row["device_id"]
            for row in rows
            if self.only_staff_id is None or row["id"] == self.only_staff_id
        }
        for staff_id, device in list(self.devices.items()):
            if wanted.get(staff_id) != device.device_id:
                del self.devices[staff_id]
        off = self._off()
        for staff_id, device_id in wanted.items():
            if staff_id not in self.devices:
                device = VirtualStaffDevice(
                    self.service, staff_id, device_id, self.poll_seconds, self.source
                )
                # A device switched off stays off when only the centre restarts.
                device.powered = staff_id not in off
                self.devices[staff_id] = device

    def _off(self):
        row = self.service.store.read(
            "SELECT value FROM meta WHERE key=?", (f"{self.source}_staff_off",)
        )
        return {int(x) for x in row[0]["value"].split(",") if x} if row else set()

    def power(self, staff_id, on, now):
        with self.lock:
            self.device(staff_id).power(on, now)
            off = (self._off() - {staff_id}) | (set() if on else {staff_id})
            with self.service.store.transaction() as db:
                db.execute(
                    "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                    (f"{self.source}_staff_off", ",".join(map(str, sorted(off)))),
                )

    def tick(self, link_up=True):
        with self.lock:
            now = self.service.clock()
            if now >= self.next_sync or now < self.next_sync - 2:
                self.sync()
                self.next_sync = now + 1
            for device in list(self.devices.values()):
                if device.powered and now >= device.next_poll:
                    device.poll(now, link_up)

    def device(self, staff_id):
        with self.lock:
            self.sync()
            device = self.devices.get(staff_id)
            if device is None:
                raise DomainError("Nhân viên chưa có thiết bị", 404)
            return device

    def reset(self):
        with self.lock:
            self.devices.clear()
            self.next_sync = float("-inf")
            with self.service.store.transaction() as db:
                db.execute("DELETE FROM meta WHERE key=?", (f"{self.source}_staff_off",))

    def snapshot(self):
        with self.lock:
            now = self.service.clock()
            return [
                device.snapshot(now)
                for _, device in sorted(self.devices.items())
            ]
