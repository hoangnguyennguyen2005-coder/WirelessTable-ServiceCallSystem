"""Central workflow authority.

Implements the closed-loop workflow of the ECE411 logbook (Step 1 §1.5.2, constraint C-01):
registered → manager acknowledged → completed drive the table indication, while dispatch,
delivery and staff acceptance are separate tracked attributes (Step 5 "request state and fault
rules"). Radio delivery, durable registration, manager acknowledgement, staff acceptance and
confirmed completion are never inferred from one another.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.store import Store
from app.domain.models import (
    HOLD_SECONDS,
    PROTOCOL_VERSION,
    REGISTRATION_SECONDS,
    STAFF_EVENTS,
    Action,
    DeviceEvent,
    DomainError,
)

LOCAL_TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh, no daylight saving
# A frame of these types is a contact opportunity: replies may be returned to the endpoint.
CONTACT_EVENTS = frozenset(
    ("CALL", "DONE", "STATUS_POLL", "NODE_HELLO", "STAFF_POLL", "STAFF_ACCEPT")
)
DEDUP_EVENTS = frozenset(("CALL", "DONE", "NODE_HELLO", "STAFF_ACCEPT"))
LIVE = "('pending','gateway_received')"
OPEN = "('pending','gateway_received','failed')"
COMMAND_TTL = 120
MAX_ATTEMPTS = 5
FAILURE_REPEAT_SECONDS = 30
STAFF_COMMANDS = {
    "DISPATCH": "SHOWN",
    "ACCEPT_RECEIPT": "ACCEPTED",
    "DISPATCH_CANCEL": "CLEARED",
}
TASK_COMMANDS = {task: kind for kind, task in STAFF_COMMANDS.items()}


def uid():
    return str(uuid4())


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def iso(timestamp):
    """ISO 8601 with the venue offset; the central clock is the only time base (ER-F11)."""
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, LOCAL_TZ).isoformat(timespec="milliseconds")


class Service:
    def __init__(
        self,
        store: Store,
        clock=time.time,
        reminder_seconds=300,
        *,
        unresolved_seconds=10,
        poll_seconds=5,
        staff_poll_seconds=2,
        low_battery_mv=0,
        retention_days=90,
    ):
        self.store, self.clock = store, clock
        self.venue_id = store.venue_id
        self.reminder_seconds = reminder_seconds
        self.unresolved_seconds = unresolved_seconds
        self.poll_seconds = poll_seconds
        self.staff_poll_seconds = staff_poll_seconds
        # ER-R03: an unresolved state must be visible on the manager screen within the
        # unresolved interval (10 s). Each timer starts at or before the fault (last contact,
        # ACK, dispatch), so flag 2 s early: up to 0.5 s until the next watch() and up to about
        # 1 s until the screen has reloaded. Never flag before one full poll period of the
        # device concerned plus margin, so an on-time poll is not mistaken for a fault.
        # The table limit also covers "state not shown at the table" (it follows the next
        # table poll); the staff limit also covers "dispatch not delivered".
        self.table_contact_seconds = max(poll_seconds + 2, unresolved_seconds - 2)
        self.staff_contact_seconds = max(staff_poll_seconds + 2, unresolved_seconds - 2)
        self.low_battery_mv = low_battery_mv
        self.retention_days = max(30, retention_days)  # ER-F11: never below 30 days
        self._recent = {}
        self._flags = set()

    def limits(self):
        return dict(
            hold_seconds=HOLD_SECONDS,
            registration_seconds=REGISTRATION_SECONDS,
            reminder_seconds=self.reminder_seconds,
            unresolved_seconds=self.unresolved_seconds,
            table_contact_seconds=self.table_contact_seconds,
            staff_contact_seconds=self.staff_contact_seconds,
            poll_seconds=self.poll_seconds,
            staff_poll_seconds=self.staff_poll_seconds,
            retention_days=self.retention_days,
        )

    # ------------------------------------------------------------------ helpers
    def log(
        self,
        db,
        kind,
        *,
        source,
        actor=None,
        request=None,
        table_id=None,
        category=None,
        staff_id=None,
        reason=None,
        event_id=None,
    ):
        """Append to the event record. Only facts the centre itself observed are logged."""
        result = {"DUPLICATE": "duplicate", "FAILURE": "failed"}.get(kind, "accepted")
        db.execute(
            "INSERT INTO events(event_id,type,source,actor,request_id,request_seq,table_id,category,staff_id,received_at,result,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id or uid(),
                kind,
                source,
                None if actor is None else str(actor),
                request["id"] if request else None,
                request["seq"] if request else None,
                request["table_id"] if request else table_id,
                request["category"] if request else category,
                staff_id,
                self.clock(),
                result,
                reason,
            ),
        )

    def request(self, db, request_id):
        row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if not row:
            raise DomainError("Không tìm thấy yêu cầu", 404)
        return dict(row)

    @staticmethod
    def led(request):
        """Table indication: steady red = registered, steady green = manager acknowledged."""
        return {"REGISTERED": "RED", "ACKNOWLEDGED": "GREEN"}.get(
            request["state"], "OFF"
        )

    @staticmethod
    def stage(request):
        """Dispatch attribute, independent from the lifecycle state."""
        if request["staff_id"] is None:
            return "NONE"
        if request["accepted_at"] is not None:
            return "ACCEPTED"
        if request["delivered_at"] is not None:
            return "DELIVERED"
        return "DISPATCHED"

    def frame(
        self,
        kind,
        target,
        *,
        command_id=None,
        request_id=None,
        boot_id=None,
        call_token=None,
        payload=None,
    ):
        data = dict(
            protocol_version=PROTOCOL_VERSION,
            venue_id=self.venue_id,
            message_type=kind,
            command_id=command_id,
            node_id=target,
            request_id=request_id,
            payload=payload or {},
        )
        if boot_id is not None:
            data.update(boot_id=boot_id, call_token=call_token)
        return data

    def error_frame(self, event, reason):
        return dict(
            protocol_version=PROTOCOL_VERSION,
            venue_id=self.venue_id,
            message_type="ERROR",
            event_id=event.event_id,
            node_id=event.node_id,
            payload=dict(reason=reason),
        )

    def _table_frame(self, kind, node, request, boot_id, call_token, command_id=None):
        return self.frame(
            kind,
            node,
            command_id=command_id,
            request_id=request["id"],
            boot_id=boot_id,
            call_token=call_token,
            payload=dict(
                led=self.led(request),
                revision=request["led_revision"],
                category=request["category"],
                request_seq=request["seq"],
            ),
        )

    def _store_command(self, db, frame, channel, revision, now):
        db.execute(
            "INSERT INTO outbox(command_id,target,request_id,type,payload,revision,next_at,expires_at,channel,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                frame["command_id"],
                frame["node_id"],
                frame["request_id"],
                frame["message_type"],
                encode(frame),
                revision,
                now,
                now + COMMAND_TTL,
                channel,
                now,
            ),
        )

    def _correlation(self, db, request, node):
        """Session the node used most recently for this request."""
        seen = db.execute(
            "SELECT o.boot_id,o.call_token FROM observations o JOIN correlations c ON c.node_id=o.node_id AND c.boot_id=o.boot_id AND c.call_token=o.call_token WHERE o.node_id=? AND c.request_id=?",
            (node, request["id"]),
        ).fetchone()
        if seen:
            return dict(seen)
        return dict(
            db.execute(
                "SELECT boot_id,call_token FROM correlations WHERE request_id=? ORDER BY rowid DESC LIMIT 1",
                (request["id"],),
            ).fetchone()
        )

    def queue(self, db, request, kind, correlation=None):
        """Tracked table command carrying the current indication; a live one is reused."""
        node = db.execute(
            "SELECT node_id FROM tables WHERE id=?", (request["table_id"],)
        ).fetchone()[0]
        now = self.clock()
        if correlation is not None and not isinstance(correlation, dict):
            correlation = dict(
                boot_id=correlation.boot_id, call_token=correlation.call_token
            )
        existing = db.execute(
            f"SELECT * FROM outbox WHERE request_id=? AND channel='table' AND type=? AND revision=? AND status IN {LIVE} AND attempts<? AND expires_at>? ORDER BY rowid DESC LIMIT 1",
            (request["id"], kind, request["led_revision"], MAX_ATTEMPTS, now),
        ).fetchone()
        if existing:
            cached = json.loads(existing["payload"])
            if correlation is None or (
                cached["boot_id"] == correlation["boot_id"]
                and cached["call_token"] == correlation["call_token"]
            ):
                return cached
        db.execute(
            f"UPDATE outbox SET status='superseded' WHERE request_id=? AND channel='table' AND type=? AND status IN {OPEN}",
            (request["id"], kind),
        )
        if correlation is None:
            correlation = self._correlation(db, request, node)
        frame = self._table_frame(
            kind,
            node,
            request,
            correlation["boot_id"],
            correlation["call_token"],
            uid(),
        )
        self._store_command(db, frame, "table", request["led_revision"], now)
        return frame

    def desired(self, db, request):
        """The indication changed: drop older table commands and queue the current one."""
        db.execute(
            f"UPDATE outbox SET status='superseded' WHERE request_id=? AND channel='table' AND status IN {OPEN}",
            (request["id"],),
        )
        return self.queue(
            db,
            request,
            "DONE_RECEIPT" if request["state"] == "COMPLETED" else "SET_REQUEST_STATUS",
        )

    def _status(self, db, request, kind, e):
        """Reply to a node contact. Untracked once the node confirmed the current indication."""
        seen = db.execute(
            "SELECT request_id,revision FROM observations WHERE node_id=?",
            (e.node_id,),
        ).fetchone()
        if (
            seen
            and seen["request_id"] == request["id"]
            and seen["revision"] == request["led_revision"]
        ):
            return self._table_frame(kind, e.node_id, request, e.boot_id, e.call_token)
        return self.queue(db, request, kind, e)

    def _queue_staff(self, db, device, request, revision, kind, reason=None):
        """Tracked command for a staff device; payload always carries the whole task."""
        now = self.clock()
        existing = db.execute(
            f"SELECT payload FROM outbox WHERE target=? AND channel='staff' AND request_id=? AND revision=? AND type=? AND status IN {LIVE} AND attempts<? AND expires_at>? ORDER BY rowid DESC LIMIT 1",
            (device, request["id"], revision, kind, MAX_ATTEMPTS, now),
        ).fetchone()
        if existing:
            return json.loads(existing[0])
        db.execute(
            f"UPDATE outbox SET status='superseded' WHERE target=? AND channel='staff' AND request_id=? AND revision=? AND type=? AND status IN {OPEN}",
            (device, request["id"], revision, kind),
        )
        table = db.execute(
            "SELECT id,name FROM tables WHERE id=?", (request["table_id"],)
        ).fetchone()
        payload = dict(
            table_id=table["id"],
            table_name=table["name"],
            category=request["category"],
            assignment_revision=revision,
            request_seq=request["seq"],
            task=STAFF_COMMANDS[kind],
        )
        if reason:
            payload["reason"] = reason
        frame = self.frame(
            kind, device, command_id=uid(), request_id=request["id"], payload=payload
        )
        self._store_command(db, frame, "staff", revision, now)
        return frame

    def _revoke(self, db, request, now, reason):
        """Close the current assignment and make its staff device drop the task."""
        current = db.execute(
            "SELECT * FROM assignments WHERE request_id=? AND revision=? AND revoked_at IS NULL",
            (request["id"], request["assignment_revision"]),
        ).fetchone()
        if not current:
            return None
        db.execute(
            "UPDATE assignments SET revoked_at=?,revoke_reason=? WHERE id=?",
            (now, reason, current["id"]),
        )
        db.execute(
            f"UPDATE outbox SET status='superseded' WHERE request_id=? AND channel='staff' AND revision=? AND type IN ('DISPATCH','ACCEPT_RECEIPT') AND status IN {OPEN}",
            (request["id"], current["revision"]),
        )
        if current["device_id"] is not None:
            self._queue_staff(
                db,
                current["device_id"],
                request,
                current["revision"],
                "DISPATCH_CANCEL",
                reason,
            )
        return dict(current)

    # ------------------------------------------------------------ device events
    @staticmethod
    def fingerprint(event):
        """Identity of a frame; volatile telemetry is excluded so a retry is not a collision."""
        payload = event.payload
        return encode(
            [
                event.message_type,
                event.venue_id,
                event.node_id,
                event.boot_id,
                event.call_token,
                event.request_id,
                payload.category,
                payload.assignment_revision,
                payload.request_seq,
            ]
        )

    def event(self, event: DeviceEvent, source="gateway"):
        fingerprint = self.fingerprint(event)
        failure = None
        response = {}
        with self.store.transaction() as db:
            try:
                if event.venue_id != self.venue_id:
                    raise DomainError("wrong_venue", 422)
                if event.message_type in DEDUP_EVENTS:
                    previous = db.execute(
                        "SELECT fingerprint FROM processed WHERE event_id=?",
                        (event.event_id,),
                    ).fetchone()
                    if previous and previous[0] != fingerprint:
                        raise DomainError("event_id_collision")
                if event.message_type in STAFF_EVENTS:
                    response = self._staff_event(db, event, source)
                elif event.message_type == "COMMAND_ACK":
                    response = self._command_ack(db, event)
                else:
                    response = self._table_event(db, event, source)
                if event.message_type in DEDUP_EVENTS:
                    db.execute(
                        "INSERT OR REPLACE INTO processed(event_id,fingerprint,response,at) VALUES(?,?,?,?)",
                        (
                            event.event_id,
                            fingerprint,
                            encode(response.get("request_id")),
                            self.clock(),
                        ),
                    )
            except DomainError as error:
                # Contact observations written before the rejection are kept on purpose.
                failure = error
                self._reject(db, event, source, error)
        if failure:
            raise failure
        return response

    def exchange(self, event: DeviceEvent, source="gateway"):
        """Process one device frame and return every frame owed to that endpoint now.

        An application-level reply is returned on every contact so a node can tell a live
        centre from a mere radio acknowledgement (ER-F03, ER-R03).
        """
        frames, result = [], {}
        try:
            result = self.event(event, source)
        except DomainError as error:
            frames.append(self.error_frame(event, error.reason))
        if event.message_type in CONTACT_EVENTS:
            released = self.commands(event.node_id)
            frames.extend(released)
            echo = result.get("command")
            if echo and not released:
                frames.append({**echo, "command_id": None})
        return frames

    def _reject(self, db, e, source, error):
        now = self.clock()
        key = (e.node_id, e.message_type, error.reason)
        if now - self._recent.get(key, float("-inf")) < FAILURE_REPEAT_SECONDS:
            return
        if len(self._recent) > 500:
            self._recent.clear()
        self._recent[key] = now
        request, table_id, staff_id = None, None, None
        if e.message_type in STAFF_EVENTS:
            staff = db.execute(
                "SELECT id FROM staff WHERE device_id=?", (e.node_id,)
            ).fetchone()
            staff_id = staff[0] if staff else None
            row = None
            if e.request_id:
                row = db.execute(
                    "SELECT * FROM requests WHERE id=?", (e.request_id,)
                ).fetchone()
            elif e.payload.request_seq is not None:
                row = db.execute(
                    "SELECT * FROM requests WHERE seq=?", (e.payload.request_seq,)
                ).fetchone()
            request = dict(row) if row else None
        else:
            table = db.execute(
                "SELECT id FROM tables WHERE node_id=?", (e.node_id,)
            ).fetchone()
            table_id = table[0] if table else None
            mapped = db.execute(
                "SELECT request_id FROM correlations WHERE node_id=? AND boot_id=? AND call_token=?",
                (e.node_id, e.boot_id, e.call_token),
            ).fetchone()
            request = self.request(db, mapped[0]) if mapped else None
        self.log(
            db,
            "FAILURE",
            source=source,
            actor=f"device:{e.node_id}",
            request=request,
            table_id=table_id,
            staff_id=staff_id,
            reason=f"{e.message_type}:{error.reason}",
            event_id=e.event_id,
        )

    def _battery(self, e):
        """True/False when this frame says something about the battery, else None."""
        if e.payload.battery_low is not None:
            return e.payload.battery_low
        if e.payload.battery_mv is not None and self.low_battery_mv > 0:
            return e.payload.battery_mv < self.low_battery_mv
        return None

    @staticmethod
    def _battery_text(e):
        mv = e.payload.battery_mv
        return f"{mv} mV" if mv is not None else "device_flag"

    def _observe(self, db, e, table, now, source):
        before = db.execute(
            "SELECT battery_low FROM observations WHERE node_id=?", (e.node_id,)
        ).fetchone()
        was_low = bool(before and before[0])
        db.execute(
            "INSERT INTO observations(node_id,last_seen,boot_id,call_token) VALUES(?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET last_seen=excluded.last_seen,boot_id=excluded.boot_id,call_token=excluded.call_token",
            (e.node_id, now, e.boot_id, e.call_token),
        )
        low = self._battery(e)
        if e.payload.battery_mv is not None or low is not None:
            db.execute(
                "UPDATE observations SET battery_mv=COALESCE(?,battery_mv),battery_low=COALESCE(?,battery_low) WHERE node_id=?",
                (e.payload.battery_mv, None if low is None else int(low), e.node_id),
            )
        if low and not was_low:
            self.log(
                db,
                "BATTERY_LOW",
                source=source,
                actor=f"device:{e.node_id}",
                table_id=table["id"],
                reason=self._battery_text(e),
            )

    def _register(self, db, table, category, now):
        request_id = uid()
        # Monotonic acceptance sequence: FIFO never depends on timestamp ties (ER-P03).
        seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM requests").fetchone()[0]
        db.execute(
            "INSERT INTO requests(id,seq,table_id,category,state,received_at,led_changed_at) VALUES(?,?,?,?,'REGISTERED',?,?)",
            (request_id, seq, table["id"], category, now, now),
        )
        return self.request(db, request_id)

    def _complete(self, db, request, now, source, e):
        closed_from = f"{request['state']}/{self.stage(request)}"
        db.execute(
            "UPDATE requests SET closed_from=?,state='COMPLETED',completed_at=?,version=version+1,led_revision=led_revision+1,led_changed_at=? WHERE id=?",
            (closed_from, now, now, request["id"]),
        )
        if request["staff_id"] is not None:
            self._revoke(db, request, now, "completed")
        db.execute(
            f"UPDATE outbox SET status='superseded' WHERE request_id=? AND channel='table' AND status IN {OPEN}",
            (request["id"],),
        )
        request = self.request(db, request["id"])
        self.log(
            db,
            "COMPLETED",
            source=source,
            actor=f"device:{e.node_id}",
            request=request,
            staff_id=request["staff_id"],
            reason=f"closed_from={closed_from}",
            event_id=e.event_id,
        )
        return request

    def _table_event(self, db, e, source):
        table = db.execute(
            "SELECT * FROM tables WHERE node_id=?", (e.node_id,)
        ).fetchone()
        if not table:
            raise DomainError("unknown_node", 422)
        now, kind = self.clock(), e.message_type
        actor = f"device:{e.node_id}"
        self._observe(db, e, table, now, source)
        mapped = db.execute(
            "SELECT request_id FROM correlations WHERE node_id=? AND boot_id=? AND call_token=?",
            (e.node_id, e.boot_id, e.call_token),
        ).fetchone()
        request = self.request(db, mapped[0]) if mapped else None
        if e.request_id and (not request or e.request_id != request["id"]):
            raise DomainError("correlation_mismatch")
        active = db.execute(
            "SELECT * FROM requests WHERE table_id=? AND state!='COMPLETED'",
            (table["id"],),
        ).fetchone()
        frame = None
        if kind == "CALL":
            if request is not None:
                # Same attempt again: the node did not see our registration confirmation.
                self.log(
                    db,
                    "DUPLICATE",
                    source=source,
                    actor=actor,
                    request=request,
                    reason="CALL:registration_retry",
                    event_id=e.event_id,
                )
            elif active:
                # ER-F06: one active request per table; category and age are never replaced.
                request = dict(active)
                db.execute(
                    "INSERT INTO correlations VALUES(?,?,?,?)",
                    (e.node_id, e.boot_id, e.call_token, request["id"]),
                )
                ignored = (
                    ""
                    if e.payload.category == request["category"]
                    else f":ignored_{e.payload.category}"
                )
                self.log(
                    db,
                    "DUPLICATE",
                    source=source,
                    actor=actor,
                    request=request,
                    reason=f"CALL:active_request_exists{ignored}",
                    event_id=e.event_id,
                )
            else:
                if not table["enabled"]:
                    raise DomainError("disabled_node", 422)
                request = self._register(db, table, e.payload.category, now)
                db.execute(
                    "INSERT INTO correlations VALUES(?,?,?,?)",
                    (e.node_id, e.boot_id, e.call_token, request["id"]),
                )
                self.log(
                    db,
                    "REGISTERED",
                    source=source,
                    actor=actor,
                    request=request,
                    event_id=e.event_id,
                )
            frame = self._status(
                db,
                request,
                "DONE_RECEIPT" if request["state"] == "COMPLETED" else "CALL_RECEIPT",
                e,
            )
        elif kind == "NODE_HELLO":
            # ER-F05: a restarted node reconciles before it admits a new request.
            if active:
                active = dict(active)
                if request is not None and request["id"] != active["id"]:
                    raise DomainError("correlation_mismatch")
                if request is None:
                    db.execute(
                        "INSERT INTO correlations VALUES(?,?,?,?)",
                        (e.node_id, e.boot_id, e.call_token, active["id"]),
                    )
                    self.log(
                        db,
                        "RECONCILED",
                        source=source,
                        actor=actor,
                        request=active,
                        reason="node_restart",
                        event_id=e.event_id,
                    )
                request = active
                frame = self._status(db, request, "SET_REQUEST_STATUS", e)
            else:
                request = None
                frame = self.frame(
                    "SET_REQUEST_STATUS",
                    e.node_id,
                    boot_id=e.boot_id,
                    call_token=e.call_token,
                    payload=dict(led="OFF", revision=0),
                )
        elif kind in ("DONE", "STATUS_POLL", "STATUS_APPLIED"):
            if request is None:
                # ER-F09: presses without a registered active request create no completion.
                raise DomainError("no_request_for_correlation")
            if kind == "DONE":
                if request["state"] != "COMPLETED":
                    # Valid from any registered active state, before or after ACK/acceptance.
                    request = self._complete(db, request, now, source, e)
                else:
                    self.log(
                        db,
                        "DUPLICATE",
                        source=source,
                        actor=actor,
                        request=request,
                        reason="DONE:completion_retry",
                        event_id=e.event_id,
                    )
                frame = self._status(db, request, "DONE_RECEIPT", e)
            elif kind == "STATUS_APPLIED":
                if e.payload.revision != request[
                    "led_revision"
                ] or e.payload.led != self.led(request):
                    raise DomainError("stale_device_status")
                if active and active["id"] != request["id"]:
                    raise DomainError("stale_device_status")
                db.execute(
                    "UPDATE observations SET led=?,request_id=?,revision=? WHERE node_id=?",
                    (e.payload.led, request["id"], e.payload.revision, e.node_id),
                )
                db.execute(
                    f"UPDATE outbox SET status='applied',error=NULL,applied_at=? WHERE request_id=? AND channel='table' AND revision=? AND status IN {OPEN}",
                    (now, request["id"], request["led_revision"]),
                )
            else:
                frame = self._status(
                    db,
                    request,
                    "DONE_RECEIPT"
                    if request["state"] == "COMPLETED"
                    else "SET_REQUEST_STATUS",
                    e,
                )
        # DEVICE_STATUS is telemetry only and never proves an applied indication.
        return dict(
            request_id=request["id"] if request else None,
            request=request,
            command=frame,
        )

    def _command_ack(self, db, e):
        """USB gateway received a command. Never a manager acknowledgement or completion."""
        changed = db.execute(
            "UPDATE outbox SET status='gateway_received' WHERE command_id=? AND target=? AND status='pending'",
            (e.command_id, e.node_id),
        ).rowcount
        if (
            not changed
            and not db.execute(
                "SELECT 1 FROM outbox WHERE command_id=? AND target=?",
                (e.command_id, e.node_id),
            ).fetchone()
        ):
            raise DomainError("unknown_command")
        return dict(request_id=None, request=None, command=None)

    # ------------------------------------------------------------- staff device
    def _observe_staff(self, db, e, staff, now, source):
        before = db.execute(
            "SELECT boot_id,battery_low FROM staff_observations WHERE device_id=?",
            (e.node_id,),
        ).fetchone()
        rebooted = before is None or before["boot_id"] != e.boot_id
        was_low = bool(before and before["battery_low"])
        db.execute(
            "INSERT INTO staff_observations(device_id,last_seen,boot_id,boot_at) VALUES(?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET last_seen=excluded.last_seen,"
            "boot_at=CASE WHEN staff_observations.boot_id IS excluded.boot_id THEN staff_observations.boot_at ELSE excluded.boot_at END,boot_id=excluded.boot_id",
            (e.node_id, now, e.boot_id, now),
        )
        low = self._battery(e)
        if e.payload.battery_mv is not None or low is not None:
            db.execute(
                "UPDATE staff_observations SET battery_mv=COALESCE(?,battery_mv),battery_low=COALESCE(?,battery_low) WHERE device_id=?",
                (e.payload.battery_mv, None if low is None else int(low), e.node_id),
            )
        if low and not was_low:
            self.log(
                db,
                "BATTERY_LOW",
                source=source,
                actor=f"device:{e.node_id}",
                staff_id=staff["id"],
                reason=self._battery_text(e),
            )
        return rebooted

    def _resolve(self, db, e):
        row = None
        if e.request_id:
            row = db.execute(
                "SELECT * FROM requests WHERE id=?", (e.request_id,)
            ).fetchone()
        elif e.payload.request_seq is not None:
            row = db.execute(
                "SELECT * FROM requests WHERE seq=?", (e.payload.request_seq,)
            ).fetchone()
        if not row:
            raise DomainError("unknown_request")
        if (
            e.request_id
            and e.payload.request_seq is not None
            and row["seq"] != e.payload.request_seq
        ):
            raise DomainError("correlation_mismatch")
        return dict(row)

    @staticmethod
    def _is_current(request, staff, revision):
        return (
            request["state"] != "COMPLETED"
            and request["staff_id"] == staff["id"]
            and request["assignment_revision"] == revision
        )

    def _staff_event(self, db, e, source):
        staff = db.execute(
            "SELECT * FROM staff WHERE device_id=? AND active=1", (e.node_id,)
        ).fetchone()
        if not staff:
            raise DomainError("unknown_staff_device", 422)
        staff, now, device = dict(staff), self.clock(), e.node_id
        rebooted = self._observe_staff(db, e, staff, now, source)
        request, frame = None, None
        if e.message_type != "STAFF_POLL":
            request = self._resolve(db, e)
            if e.message_type == "STAFF_APPLIED":
                self._staff_applied(db, e, staff, request, now, source)
            else:
                frame = self._staff_accept(db, e, staff, request, now, source)
                request = self.request(db, request["id"])
        open_tasks = self._staff_sync(db, staff, device, now, rebooted)
        if frame is None:
            frame = self.frame(
                "STAFF_STATUS", device, payload=dict(open_tasks=open_tasks)
            )
        return dict(
            request_id=request["id"] if request else None,
            request=request,
            command=frame,
        )

    def _staff_applied(self, db, e, staff, request, now, source):
        """The device reports what it shows. SHOWN is the delivery receipt, not acceptance."""
        task, revision, device = e.payload.task, e.payload.assignment_revision, e.node_id
        db.execute(
            f"UPDATE outbox SET status='applied',error=NULL,applied_at=? WHERE target=? AND channel='staff' AND request_id=? AND revision=? AND type=? AND status IN {OPEN}",
            (now, device, request["id"], revision, TASK_COMMANDS[task]),
        )
        if task == "CLEARED":
            db.execute(
                "UPDATE assignments SET cleared_at=? WHERE request_id=? AND revision=? AND staff_id=? AND revoked_at IS NOT NULL AND cleared_at IS NULL",
                (now, request["id"], revision, staff["id"]),
            )
        elif not self._is_current(request, staff, revision):
            # The device still shows a task that is no longer assigned to it.
            self._queue_staff(db, device, request, revision, "DISPATCH_CANCEL", "stale")
        elif request["delivered_at"] is None:
            db.execute(
                "UPDATE assignments SET delivered_at=? WHERE request_id=? AND revision=?",
                (now, request["id"], revision),
            )
            db.execute(
                "UPDATE requests SET delivered_at=? WHERE id=?", (now, request["id"])
            )
            self.log(
                db,
                "DELIVERED",
                source=source,
                actor=f"device:{device}",
                request=request,
                staff_id=staff["id"],
                reason=f"revision={revision}",
                event_id=e.event_id,
            )

    def _staff_accept(self, db, e, staff, request, now, source):
        """Explicit human acceptance. It never completes the request or changes the table LED."""
        revision, device = e.payload.assignment_revision, e.node_id
        if not self._is_current(request, staff, revision):
            # Reassigned, cancelled or closed: the old acceptance must not overwrite anything.
            self._queue_staff(db, device, request, revision, "DISPATCH_CANCEL", "stale")
            raise DomainError("stale_assignment")
        if request["accepted_at"] is None:
            db.execute(
                "UPDATE assignments SET accepted_at=?,delivered_at=COALESCE(delivered_at,?) WHERE request_id=? AND revision=?",
                (now, now, request["id"], revision),
            )
            db.execute(
                "UPDATE requests SET accepted_at=?,delivered_at=COALESCE(delivered_at,?),version=version+1 WHERE id=?",
                (now, now, request["id"]),
            )
            db.execute(
                f"UPDATE outbox SET status='superseded' WHERE request_id=? AND channel='staff' AND revision=? AND type='DISPATCH' AND status IN {OPEN}",
                (request["id"], revision),
            )
            request = self.request(db, request["id"])
            self.log(
                db,
                "ACCEPTED",
                source=source,
                actor=f"staff:{staff['id']}",
                request=request,
                staff_id=staff["id"],
                reason=f"revision={revision}",
                event_id=e.event_id,
            )
        else:
            self.log(
                db,
                "DUPLICATE",
                source=source,
                actor=f"staff:{staff['id']}",
                request=request,
                staff_id=staff["id"],
                reason="STAFF_ACCEPT:acceptance_retry",
                event_id=e.event_id,
            )
        return self._queue_staff(db, device, request, revision, "ACCEPT_RECEIPT")

    def _staff_sync(self, db, staff, device, now, rebooted):
        """Converge the device with the centre on every contact; returns its open task count."""
        if rebooted:
            # A restarted device shows nothing: old cancels are moot, current tasks go out again.
            # Commands up to boot_mark belong to the previous session, whatever the clock says.
            db.execute(
                "UPDATE assignments SET cleared_at=? WHERE device_id=? AND revoked_at IS NOT NULL AND cleared_at IS NULL",
                (now, device),
            )
            db.execute(
                f"UPDATE outbox SET status='superseded' WHERE target=? AND channel='staff' AND status IN {OPEN}",
                (device,),
            )
            db.execute(
                "UPDATE staff_observations SET boot_mark=(SELECT COALESCE(MAX(rowid),0) FROM outbox) WHERE device_id=?",
                (device,),
            )
        boot_mark = db.execute(
            "SELECT boot_mark FROM staff_observations WHERE device_id=?", (device,)
        ).fetchone()[0]
        current = db.execute(
            "SELECT r.* FROM requests r JOIN assignments a ON a.request_id=r.id AND a.revision=r.assignment_revision WHERE r.state!='COMPLETED' AND r.staff_id=? AND a.revoked_at IS NULL AND a.device_id=? ORDER BY r.seq",
            (staff["id"], device),
        ).fetchall()
        for row in current:
            request = dict(row)
            kind = "ACCEPT_RECEIPT" if request["accepted_at"] is not None else "DISPATCH"
            latest = db.execute(
                "SELECT rowid,status FROM outbox WHERE target=? AND channel='staff' AND request_id=? AND revision=? AND type=? AND status!='superseded' ORDER BY rowid DESC LIMIT 1",
                (device, request["id"], request["assignment_revision"], kind),
            ).fetchone()
            # Applied during the device's current session: nothing to resend.
            if latest and latest["status"] == "applied" and latest["rowid"] > boot_mark:
                continue
            self._queue_staff(db, device, request, request["assignment_revision"], kind)
        stale = db.execute(
            "SELECT * FROM assignments WHERE device_id=? AND revoked_at IS NOT NULL AND cleared_at IS NULL AND revoked_at>?",
            (device, now - 86400),
        ).fetchall()
        for assignment in stale:
            self._queue_staff(
                db,
                device,
                self.request(db, assignment["request_id"]),
                assignment["revision"],
                "DISPATCH_CANCEL",
                assignment["revoke_reason"],
            )
        return len(current)

    # ---------------------------------------------------------- manager actions
    def action(self, request_id: str, kind: str, action: Action, actor="manager"):
        fingerprint = encode(
            dict(request_id=request_id, kind=kind, actor=actor, **action.model_dump())
        )
        handlers = dict(
            ack=self._ack,
            dispatch=self._dispatch,
            cancel_dispatch=self._cancel_dispatch,
            retry_dispatch=self._retry_dispatch,
        )
        failure = None
        with self.store.transaction() as db:
            prior = db.execute(
                "SELECT * FROM actions WHERE key=?", (action.idempotency_key,)
            ).fetchone()
            request = None
            try:
                if prior:
                    if prior["fingerprint"] != fingerprint:
                        raise DomainError("idempotency_key_reused")
                    return json.loads(prior["response"])
                if kind not in handlers:
                    raise DomainError("Thao tác không hợp lệ", 422)
                request = self.request(db, request_id)
                result = handlers[kind](db, request, action, actor, self.clock())
                db.execute(
                    "INSERT INTO actions(key,fingerprint,response,at) VALUES(?,?,?,?)",
                    (action.idempotency_key, fingerprint, encode(result), self.clock()),
                )
            except DomainError as error:
                self.log(
                    db,
                    "FAILURE",
                    source="web",
                    actor=actor,
                    request=request,
                    reason=f"{kind}:{error.reason}",
                    event_id=action.idempotency_key,
                )
                failure = error
                result = {}
        if failure:
            raise failure
        return result

    @staticmethod
    def _check_version(request, action):
        if request["version"] != action.expected_version:
            raise DomainError("Dữ liệu đã thay đổi. Đã tải lại, vui lòng thử lại.")

    def _ack(self, db, r, action, actor, now):
        """Manager acknowledgement: the only event that turns the table green (ER-F04)."""
        if r["state"] == "ACKNOWLEDGED":
            return r
        if r["state"] != "REGISTERED":
            raise DomainError("Yêu cầu đã hoàn tất")
        self._check_version(r, action)
        db.execute(
            "UPDATE requests SET state='ACKNOWLEDGED',acknowledged_at=?,version=version+1,led_revision=led_revision+1,led_changed_at=? WHERE id=?",
            (now, now, r["id"]),
        )
        r = self.request(db, r["id"])
        self.desired(db, r)
        self.log(
            db,
            "ACKNOWLEDGED",
            source="web",
            actor=actor,
            request=r,
            event_id=action.idempotency_key,
        )
        return r

    def _dispatch(self, db, r, action, actor, now):
        """Send table/category/request to a staff device. Independent from acknowledgement."""
        if r["state"] == "COMPLETED":
            raise DomainError("Yêu cầu đã hoàn tất")
        self._check_version(r, action)
        if action.staff_id is None:
            raise DomainError("Thiếu staff_id", 422)
        staff = db.execute(
            "SELECT * FROM staff WHERE id=? AND active=1 AND available=1",
            (action.staff_id,),
        ).fetchone()
        if not staff:
            raise DomainError("Nhân viên không khả dụng", 422)
        if staff["device_id"] is None:
            raise DomainError("Nhân viên chưa được gán thiết bị", 422)
        previous = None
        if r["staff_id"] is not None:
            if r["staff_id"] == staff["id"]:
                raise DomainError(
                    "Yêu cầu đang giao cho nhân viên này. Dùng “Gửi lại” nếu thiết bị chưa nhận."
                )
            if r["accepted_at"] is not None and not action.confirm:
                raise DomainError("Cần xác nhận giao lại việc đã nhận")
            # Reassignment invalidates the old assignment; its acceptance becomes stale.
            previous = self._revoke(db, r, now, "reassigned")
        revision = r["assignment_revision"] + 1
        db.execute(
            "INSERT INTO assignments(request_id,staff_id,revision,assigned_at,actor,device_id) VALUES(?,?,?,?,?,?)",
            (r["id"], staff["id"], revision, now, actor, staff["device_id"]),
        )
        db.execute(
            "UPDATE requests SET staff_id=?,assignment_revision=?,dispatched_at=?,delivered_at=NULL,accepted_at=NULL,version=version+1 WHERE id=?",
            (staff["id"], revision, now, r["id"]),
        )
        r = self.request(db, r["id"])
        self._queue_staff(db, staff["device_id"], r, revision, "DISPATCH")
        self.log(
            db,
            "DISPATCHED",
            source="web",
            actor=actor,
            request=r,
            staff_id=staff["id"],
            reason=f"revision={revision}"
            + (f";reassigned_from={previous['staff_id']}" if previous else ""),
            event_id=action.idempotency_key,
        )
        return r

    def _cancel_dispatch(self, db, r, action, actor, now):
        """Explicit cancellation; until then a missing acceptance stays pending (ER-R03)."""
        if r["state"] == "COMPLETED":
            raise DomainError("Yêu cầu đã hoàn tất")
        self._check_version(r, action)
        if r["staff_id"] is None:
            raise DomainError("Yêu cầu chưa được giao")
        if r["accepted_at"] is not None and not action.confirm:
            raise DomainError("Cần xác nhận thu hồi việc đã nhận")
        staff_id = r["staff_id"]
        self._revoke(db, r, now, "cancelled")
        db.execute(
            "UPDATE requests SET staff_id=NULL,dispatched_at=NULL,delivered_at=NULL,accepted_at=NULL,version=version+1 WHERE id=?",
            (r["id"],),
        )
        r = self.request(db, r["id"])
        self.log(
            db,
            "DISPATCH_CANCELLED",
            source="web",
            actor=actor,
            request=r,
            staff_id=staff_id,
            reason=f"revision={r['assignment_revision']}",
            event_id=action.idempotency_key,
        )
        return r

    def _retry_dispatch(self, db, r, action, actor, now):
        """Manager retries an undelivered or unaccepted dispatch with the same assignment."""
        if r["state"] == "COMPLETED":
            raise DomainError("Yêu cầu đã hoàn tất")
        if r["staff_id"] is None:
            raise DomainError("Yêu cầu chưa được giao")
        if r["accepted_at"] is not None:
            raise DomainError("Nhân viên đã nhận việc")
        device = db.execute(
            "SELECT device_id FROM staff WHERE id=?", (r["staff_id"],)
        ).fetchone()[0]
        if device is None:
            raise DomainError("Nhân viên chưa được gán thiết bị", 422)
        db.execute(
            f"UPDATE outbox SET status='superseded' WHERE request_id=? AND channel='staff' AND revision=? AND type='DISPATCH' AND status IN {OPEN}",
            (r["id"], r["assignment_revision"]),
        )
        self._queue_staff(db, device, r, r["assignment_revision"], "DISPATCH")
        self.log(
            db,
            "DISPATCHED",
            source="web",
            actor=actor,
            request=r,
            staff_id=r["staff_id"],
            reason=f"revision={r['assignment_revision']};retry",
            event_id=action.idempotency_key,
        )
        return r

    # ------------------------------------------------------------- housekeeping
    def remind(self):
        """Overdue once the request is incomplete at ≥ reminder_seconds after registration.

        Acknowledged or accepted requests are included; age and arrival order are untouched.
        """
        with self.store.transaction() as db:
            rows = db.execute(
                "SELECT * FROM requests WHERE state!='COMPLETED' AND reminded_at IS NULL AND received_at<=?",
                (self.clock() - self.reminder_seconds,),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE requests SET reminded_at=? WHERE id=?",
                    (self.clock(), row["id"]),
                )
                self.log(
                    db,
                    "OVERDUE",
                    source="worker",
                    actor="system",
                    request=dict(row),
                    staff_id=row["staff_id"],
                    reason=f"state={row['state']};dispatch={self.stage(row)}",
                )
        return len(rows)

    def watch(self):
        """Record, once per episode, the unresolved conditions the centre can observe."""
        now, found = self.clock(), set()
        rows = self.store.read(
            "SELECT r.*,o.last_seen,o.request_id AS observed_request_id,o.revision AS observed_revision FROM requests r JOIN tables t ON t.id=r.table_id LEFT JOIN observations o ON o.node_id=t.node_id WHERE r.state!='COMPLETED'"
        )
        for r in rows:
            applied = (
                r["observed_request_id"] == r["id"]
                and r["observed_revision"] == r["led_revision"]
            )
            if not applied and now - r["led_changed_at"] > self.table_contact_seconds:
                found.add((("sync", r["id"], r["led_revision"]), r["id"], "table_state_not_applied"))
            if (
                r["last_seen"] is not None
                and now - r["last_seen"] > self.table_contact_seconds
            ):
                found.add((("contact", r["id"]), r["id"], "table_contact_lost"))
            if (
                r["staff_id"] is not None
                and r["delivered_at"] is None
                and r["dispatched_at"] is not None
                and now - r["dispatched_at"] > self.staff_contact_seconds
            ):
                found.add((("delivery", r["id"], r["assignment_revision"]), r["id"], "dispatch_not_delivered"))
        for s in self.store.read(
            "SELECT s.id,o.last_seen,(SELECT MIN(r.id) FROM requests r WHERE r.staff_id=s.id AND r.state!='COMPLETED') AS request_id FROM staff s LEFT JOIN staff_observations o ON o.device_id=s.device_id"
        ):
            # A device that was never seen is covered by dispatch_not_delivered.
            if (
                s["request_id"]
                and s["last_seen"] is not None
                and now - s["last_seen"] > self.staff_contact_seconds
            ):
                found.add((("staff", s["id"]), s["request_id"], "staff_device_contact_lost"))
        keys = {item[0] for item in found}
        fresh = [item for item in found if item[0] not in self._flags]
        if fresh:
            with self.store.transaction() as db:
                for _key, request_id, reason in fresh:
                    row = db.execute(
                        "SELECT * FROM requests WHERE id=?", (request_id,)
                    ).fetchone()
                    if row:
                        self.log(
                            db,
                            "FAILURE",
                            source="worker",
                            actor="system",
                            request=dict(row),
                            staff_id=row["staff_id"],
                            reason=reason,
                        )
        self._flags = keys
        return len(fresh)

    def prune(self):
        """Delete records older than the retention period; never younger than 30 days."""
        cutoff = self.clock() - self.retention_days * 86400
        with self.store.transaction() as db:
            removed = db.execute(
                "DELETE FROM events WHERE received_at<?", (cutoff,)
            ).rowcount
            db.execute("DELETE FROM processed WHERE at<?", (cutoff,))
            db.execute("DELETE FROM actions WHERE at<?", (cutoff,))
            db.execute(
                "DELETE FROM outbox WHERE created_at<? AND request_id IN (SELECT id FROM requests WHERE state='COMPLETED')",
                (cutoff,),
            )
        return removed

    def commands(self, target, contact=True):
        """Release only on endpoint contact; retries are bounded and persisted across restart."""
        now = self.clock()
        frames = []
        with self.store.transaction() as db:
            for row in db.execute(
                f"SELECT * FROM outbox WHERE expires_at<=? AND status IN {LIVE}", (now,)
            ).fetchall():
                self._close_command(db, row, "expired", "Hết thời hạn")
            for row in db.execute(
                f"SELECT * FROM outbox WHERE attempts>=? AND next_at<=? AND status IN {LIVE}",
                (MAX_ATTEMPTS, now),
            ).fetchall():
                self._close_command(db, row, "failed", "Đã hết số lần thử")
            if contact:
                rows = db.execute(
                    f"SELECT * FROM outbox WHERE target=? AND status IN {LIVE} AND attempts<? AND next_at<=? ORDER BY rowid LIMIT 12",
                    (target, MAX_ATTEMPTS, now),
                ).fetchall()
                for row in rows:
                    if not self._releasable(db, row):
                        db.execute(
                            "UPDATE outbox SET status='superseded' WHERE command_id=?",
                            (row["command_id"],),
                        )
                        continue
                    db.execute(
                        "UPDATE outbox SET attempts=attempts+1,next_at=? WHERE command_id=?",
                        (now + 2 ** row["attempts"], row["command_id"]),
                    )
                    frames.append(json.loads(row["payload"]))
                    if len(frames) == 4:
                        break
        return frames

    def _close_command(self, db, row, status, text):
        db.execute(
            "UPDATE outbox SET status=?,error=? WHERE command_id=?",
            (status, text, row["command_id"]),
        )
        if row["type"] == "DISPATCH_CANCEL":
            return
        request = self.request(db, row["request_id"])
        self.log(
            db,
            "FAILURE",
            source="worker",
            actor="system",
            request=request,
            staff_id=request["staff_id"] if row["channel"] == "staff" else None,
            reason=f"{row['type']}:command_{status}",
        )

    @staticmethod
    def _releasable(db, row):
        """A stored command is sent only while it still describes the current state."""
        r = db.execute(
            "SELECT state,staff_id,assignment_revision,led_revision FROM requests WHERE id=?",
            (row["request_id"],),
        ).fetchone()
        if row["channel"] == "table":
            return r["led_revision"] == row["revision"]
        if row["type"] == "DISPATCH_CANCEL":
            return True
        if (
            r["state"] == "COMPLETED"
            or r["staff_id"] is None
            or r["assignment_revision"] != row["revision"]
        ):
            return False
        device = db.execute(
            "SELECT device_id FROM staff WHERE id=?", (r["staff_id"],)
        ).fetchone()
        return bool(device) and device[0] == row["target"]

    def transport_error(self, command_id, reason):
        with self.store.transaction() as db:
            db.execute(
                "UPDATE outbox SET error=? WHERE command_id=?",
                (reason[:200], command_id),
            )

    def note(self, kind, reason, source="system"):
        """System-level entry in the event record (centre start, gateway link)."""
        with self.store.transaction() as db:
            self.log(db, kind, source=source, actor="system", reason=reason)

    def forget(self):
        """Drop in-memory episode markers (demo reset only)."""
        self._flags.clear()
        self._recent.clear()

    # ------------------------------------------------------------------ queries
    def snapshot(self):
        requests = self.store.read(
            "SELECT * FROM requests WHERE state!='COMPLETED' ORDER BY seq"
        )
        latest = {}
        for row in self.store.read(
            "SELECT o.request_id,o.channel,o.type,o.status,o.attempts,o.error,o.applied_at FROM outbox o JOIN requests r ON r.id=o.request_id "
            "WHERE r.state!='COMPLETED' AND o.status!='superseded' AND (o.channel='table' OR (o.type!='DISPATCH_CANCEL' AND o.revision=r.assignment_revision)) ORDER BY o.rowid"
        ):
            latest[(row["request_id"], row["channel"])] = dict(
                type=row["type"],
                status=row["status"],
                attempts=row["attempts"],
                error=row["error"],
                applied_at=row["applied_at"],
            )
        for r in requests:
            r["table_command"] = latest.get((r["id"], "table"))
            r["staff_command"] = (
                latest.get((r["id"], "staff")) if r["staff_id"] is not None else None
            )
        return dict(
            venue_id=self.venue_id,
            tables=self.store.read(
                "SELECT t.*,o.last_seen,o.led,o.battery_mv,COALESCE(o.battery_low,0) AS battery_low,o.request_id AS observed_request_id,o.revision AS observed_revision FROM tables t LEFT JOIN observations o ON t.node_id=o.node_id ORDER BY t.id"
            ),
            staff=self.store.read(
                "SELECT s.*,o.last_seen,o.battery_mv,COALESCE(o.battery_low,0) AS battery_low FROM staff s LEFT JOIN staff_observations o ON o.device_id=s.device_id ORDER BY s.id"
            ),
            requests=requests,
            limits=self.limits(),
            now=self.clock(),
        )

    def detail(self, request_id):
        db = self.store.connect()
        try:
            r = self.request(db, request_id)
        finally:
            db.close()
        return dict(
            request=r,
            events=self.store.read(
                "SELECT e.*,s.name AS staff_name FROM events e LEFT JOIN staff s ON s.id=e.staff_id WHERE e.request_id=? ORDER BY e.id",
                (request_id,),
            ),
            assignments=self.store.read(
                "SELECT a.*,s.name AS staff_name FROM assignments a JOIN staff s ON s.id=a.staff_id WHERE a.request_id=? ORDER BY a.revision",
                (request_id,),
            ),
            commands=self.store.read(
                "SELECT * FROM outbox WHERE request_id=? ORDER BY rowid DESC LIMIT 40",
                (request_id,),
            ),
        )

    def history(
        self,
        table_id=None,
        staff_id=None,
        state=None,
        category=None,
        start=None,
        end=None,
        limit=50,
        offset=0,
    ):
        conditions, args = [], []
        for column, value in [
            ("r.table_id", table_id),
            ("r.staff_id", staff_id),
            ("r.state", state),
            ("r.category", category),
        ]:
            if value is not None:
                conditions.append(f"{column}=?")
                args.append(value)
        for operator, value in [(">=", start), ("<=", end)]:
            if value is not None:
                conditions.append(f"r.received_at{operator}?")
                args.append(value)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        total = self.store.read("SELECT COUNT(*) AS n FROM requests r" + where, args)[
            0
        ]["n"]
        rows = self.store.read(
            "SELECT r.*,t.name AS table_name,s.name AS staff_name FROM requests r JOIN tables t ON t.id=r.table_id LEFT JOIN staff s ON s.id=r.staff_id"
            + where
            + " ORDER BY r.seq DESC LIMIT ? OFFSET ?",
            [*args, limit, offset],
        )
        return dict(items=rows, total=total)

    def event_log(
        self,
        kind=None,
        table_id=None,
        start=None,
        end=None,
        limit=50,
        offset=0,
        ascending=False,
        after_id=None,
    ):
        conditions, args = [], []
        for column, value in [("e.type", kind), ("e.table_id", table_id)]:
            if value is not None:
                conditions.append(f"{column}=?")
                args.append(value)
        if after_id is not None:
            conditions.append("e.id>?")
            args.append(after_id)
        for operator, value in [(">=", start), ("<=", end)]:
            if value is not None:
                conditions.append(f"e.received_at{operator}?")
                args.append(value)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        total = self.store.read("SELECT COUNT(*) AS n FROM events e" + where, args)[0][
            "n"
        ]
        rows = self.store.read(
            "SELECT e.*,t.name AS table_name,s.name AS staff_name FROM events e LEFT JOIN tables t ON t.id=e.table_id LEFT JOIN staff s ON s.id=e.staff_id"
            + where
            + f" ORDER BY e.id {'ASC' if ascending else 'DESC'} LIMIT ? OFFSET ?",
            [*args, limit, offset],
        )
        return dict(items=rows, total=total)
