import json
import time
from uuid import uuid4
from app.domain.models import DomainError, DeviceEvent, Action
from app.db.store import Store


def uid():
    return str(uuid4())


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Service:
    def __init__(self, store: Store, clock=time.time, reminder_seconds=300):
        self.store, self.clock, self.reminder_seconds = store, clock, reminder_seconds

    def log(
        self,
        db,
        event_id,
        kind,
        source,
        actor,
        request_id,
        result="accepted",
        reason=None,
    ):
        db.execute(
            "INSERT INTO events(event_id,type,source,actor,request_id,received_at,result,reason) VALUES(?,?,?,?,?,?,?,?)",
            (
                event_id,
                kind,
                source,
                str(actor),
                request_id,
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
        return (
            "OFF"
            if request["state"] == "COMPLETED"
            else "RED"
            if request["state"] == "WAITING_ACK"
            else "GREEN"
        )

    def queue(self, db, request, kind, correlation=None):
        node = db.execute(
            "SELECT node_id FROM tables WHERE id=?", (request["table_id"],)
        ).fetchone()[0]
        existing = db.execute(
            "SELECT * FROM outbox WHERE request_id=? AND type=? AND revision=? AND status IN ('pending','gateway_received') AND attempts<5 AND expires_at>? ORDER BY rowid DESC LIMIT 1",
            (request["id"], kind, request["version"], self.clock()),
        ).fetchone()
        if existing:
            cached = json.loads(existing["payload"])
            if correlation is None or (
                cached["boot_id"] == correlation["boot_id"]
                and cached["call_token"] == correlation["call_token"]
            ):
                return cached
        db.execute(
            "UPDATE outbox SET status='superseded' WHERE request_id=? AND type=? AND status IN ('pending','gateway_received','failed')",
            (request["id"], kind),
        )
        if correlation is None:
            correlation = dict(
                db.execute(
                    "SELECT boot_id,call_token FROM correlations WHERE request_id=? LIMIT 1",
                    (request["id"],),
                ).fetchone()
            )
        command_id = uid()
        frame = dict(
            protocol_version=1,
            message_type=kind,
            command_id=command_id,
            node_id=node,
            request_id=request["id"],
            boot_id=correlation["boot_id"],
            call_token=correlation["call_token"],
            payload=dict(led=self.led(request), revision=request["version"]),
        )
        now = self.clock()
        db.execute(
            "INSERT INTO outbox(command_id,target,request_id,type,payload,revision,next_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                command_id,
                node,
                request["id"],
                kind,
                encode(frame),
                request["version"],
                now,
                now + 120,
            ),
        )
        return frame

    def desired(self, db, request):
        db.execute(
            "UPDATE outbox SET status='superseded' WHERE request_id=? AND status IN ('pending','gateway_received','failed')",
            (request["id"],),
        )
        self.queue(
            db,
            request,
            "DONE_RECEIPT" if request["state"] == "COMPLETED" else "SET_REQUEST_STATUS",
        )

    def event(self, event: DeviceEvent, source="gateway"):
        fingerprint = encode(event.model_dump())
        failure = None
        with self.store.transaction() as db:
            previous = db.execute(
                "SELECT * FROM processed WHERE event_id=?", (event.event_id,)
            ).fetchone()
            if previous and previous["fingerprint"] != fingerprint:
                self.log(
                    db,
                    event.event_id,
                    event.message_type,
                    source,
                    event.node_id,
                    None,
                    "rejected",
                    "event_id_collision",
                )
                failure = DomainError("event_id_collision")
                response = {}
            else:
                try:
                    response = self._event(db, event, previous)
                except DomainError as error:
                    mapped = db.execute(
                        "SELECT request_id FROM correlations WHERE node_id=? AND boot_id=? AND call_token=?",
                        (event.node_id, event.boot_id, event.call_token),
                    ).fetchone()
                    response = dict(
                        error=error.reason, request_id=mapped[0] if mapped else None
                    )
                    failure = error
                self.log(
                    db,
                    event.event_id,
                    event.message_type,
                    source,
                    event.node_id,
                    response.get("request_id"),
                    "rejected" if failure else "duplicate" if previous else "accepted",
                    failure.reason if failure else None,
                )
                # Rejected events may be retried after their prerequisite arrives.
                if not failure:
                    db.execute(
                        "INSERT OR REPLACE INTO processed VALUES(?,?,?)",
                        (event.event_id, fingerprint, encode(response)),
                    )
        if failure:
            raise failure
        return response

    def _event(self, db, e, previous):
        table = db.execute(
            "SELECT * FROM tables WHERE node_id=?", (e.node_id,)
        ).fetchone()
        if not table or (not table["enabled"] and e.message_type == "CALL"):
            raise DomainError("unknown_or_disabled_node", 422)
        now = self.clock()
        db.execute(
            "INSERT INTO observations(node_id,last_seen) VALUES(?,?) ON CONFLICT(node_id) DO UPDATE SET last_seen=excluded.last_seen",
            (e.node_id, now),
        )
        if e.payload.battery_mv is not None:
            db.execute(
                "UPDATE observations SET battery_mv=? WHERE node_id=?",
                (e.payload.battery_mv, e.node_id),
            )
        correlation = db.execute(
            "SELECT request_id FROM correlations WHERE node_id=? AND boot_id=? AND call_token=?",
            (e.node_id, e.boot_id, e.call_token),
        ).fetchone()
        request = self.request(db, correlation[0]) if correlation else None
        if e.request_id and (not request or e.request_id != request["id"]):
            raise DomainError("correlation_mismatch")
        if e.message_type == "CALL":
            if not request:
                active = db.execute(
                    "SELECT * FROM requests WHERE table_id=? AND state!='COMPLETED'",
                    (table["id"],),
                ).fetchone()
                if active:
                    request = dict(active)
                else:
                    request_id = uid()
                    db.execute(
                        "INSERT INTO requests(id,table_id,state,received_at) VALUES(?,?,'WAITING_ACK',?)",
                        (request_id, table["id"], now),
                    )
                    request = self.request(db, request_id)
                db.execute(
                    "INSERT INTO correlations VALUES(?,?,?,?)",
                    (e.node_id, e.boot_id, e.call_token, request["id"]),
                )
            frame = self.queue(db, request, "CALL_RECEIPT", e.model_dump())
        elif e.message_type in ("DONE", "STATUS_POLL", "STATUS_APPLIED"):
            if not request:
                raise DomainError("no_request_for_correlation")
            if e.message_type == "DONE":
                if request["state"] == "WAITING_ACK":
                    raise DomainError("done_before_ack")
                if request["state"] != "COMPLETED":
                    db.execute(
                        "UPDATE requests SET closed_from=state,state='COMPLETED',completed_at=?,version=version+1 WHERE id=?",
                        (now, request["id"]),
                    )
                    request = self.request(db, request["id"])
                    db.execute(
                        "UPDATE outbox SET status='superseded' WHERE request_id=? AND status IN ('pending','gateway_received','failed')",
                        (request["id"],),
                    )
                frame = self.queue(db, request, "DONE_RECEIPT", e.model_dump())
            elif e.message_type == "STATUS_APPLIED":
                if e.payload.revision != request[
                    "version"
                ] or e.payload.led != self.led(request):
                    raise DomainError("stale_device_status")
                active = db.execute(
                    "SELECT id FROM requests WHERE table_id=? AND state!='COMPLETED'",
                    (table["id"],),
                ).fetchone()
                if active and active[0] != request["id"]:
                    raise DomainError("stale_device_status")
                db.execute(
                    "UPDATE observations SET led=?,request_id=?,revision=? WHERE node_id=?",
                    (e.payload.led, request["id"], e.payload.revision, e.node_id),
                )
                db.execute(
                    "UPDATE outbox SET status='applied',error=NULL WHERE request_id=? AND revision=? AND status IN ('pending','gateway_received','failed')",
                    (request["id"], request["version"]),
                )
                frame = None
            else:
                frame = self.queue(
                    db,
                    request,
                    "DONE_RECEIPT"
                    if request["state"] == "COMPLETED"
                    else "SET_REQUEST_STATUS",
                    e.model_dump(),
                )
        elif e.message_type == "COMMAND_ACK":
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
            frame = None
        else:  # DEVICE_STATUS is telemetry, never authoritative applied LED.
            frame = None
        return dict(
            request_id=request["id"] if request else None,
            request=request,
            command=frame,
        )

    def action(self, request_id: str, kind: str, action: Action, actor="manager"):
        fingerprint = encode(
            dict(request_id=request_id, kind=kind, actor=actor, **action.model_dump())
        )
        failure = None
        with self.store.transaction() as db:
            prior = db.execute(
                "SELECT * FROM actions WHERE key=?", (action.idempotency_key,)
            ).fetchone()
            try:
                if prior:
                    if kind == "accept":
                        current = self.request(db, request_id)
                        if (
                            current["staff_id"] != action.staff_id
                            or current["assignment_revision"] != action.revision
                        ):
                            raise DomainError(
                                "Sai nhân viên hoặc phiên giao việc đã cũ"
                            )
                    if prior["fingerprint"] != fingerprint:
                        raise DomainError("idempotency_key_reused")
                    return json.loads(prior["response"])
                r = self.request(db, request_id)
                if kind == "accept" and (
                    r["staff_id"] != action.staff_id
                    or r["assignment_revision"] != action.revision
                ):
                    raise DomainError("Sai nhân viên hoặc phiên giao việc đã cũ")
                repeat = (
                    kind == "ack"
                    and r["state"] in ("ACKNOWLEDGED", "ASSIGNED", "ACCEPTED")
                ) or (kind == "accept" and r["state"] == "ACCEPTED")
                if not repeat:
                    if r["version"] != action.expected_version:
                        raise DomainError(
                            "Dữ liệu đã thay đổi. Đã tải lại, vui lòng thử lại."
                        )
                    now = self.clock()
                    if kind == "ack" and r["state"] == "WAITING_ACK":
                        db.execute(
                            "UPDATE requests SET state='ACKNOWLEDGED',acknowledged_at=?,version=version+1 WHERE id=?",
                            (now, request_id),
                        )
                    elif kind == "assign" and r["state"] in (
                        "ACKNOWLEDGED",
                        "ASSIGNED",
                        "ACCEPTED",
                    ):
                        staff = db.execute(
                            "SELECT * FROM staff WHERE id=? AND active=1 AND available=1",
                            (action.staff_id,),
                        ).fetchone()
                        if not staff:
                            raise DomainError("Nhân viên không khả dụng", 422)
                        if r["state"] == "ACCEPTED" and not action.confirm_reassign:
                            raise DomainError("Cần xác nhận giao lại việc đã nhận")
                        db.execute(
                            "UPDATE assignments SET revoked_at=? WHERE request_id=? AND revoked_at IS NULL",
                            (now, request_id),
                        )
                        revision = r["assignment_revision"] + 1
                        db.execute(
                            "INSERT INTO assignments(request_id,staff_id,revision,assigned_at,actor) VALUES(?,?,?,?,?)",
                            (request_id, action.staff_id, revision, now, actor),
                        )
                        db.execute(
                            "UPDATE requests SET state='ASSIGNED',staff_id=?,assignment_revision=?,accepted_at=NULL,version=version+1 WHERE id=?",
                            (action.staff_id, revision, request_id),
                        )
                    elif kind == "accept" and r["state"] == "ASSIGNED":
                        db.execute(
                            "UPDATE requests SET state='ACCEPTED',accepted_at=?,version=version+1 WHERE id=?",
                            (now, request_id),
                        )
                        db.execute(
                            "UPDATE assignments SET accepted_at=? WHERE request_id=? AND revision=?",
                            (now, request_id, action.revision),
                        )
                    else:
                        raise DomainError("Thao tác không hợp lệ ở trạng thái hiện tại")
                    r = self.request(db, request_id)
                    self.desired(db, r)
                self.log(
                    db, action.idempotency_key, kind.upper(), "web", actor, request_id
                )
                db.execute(
                    "INSERT INTO actions VALUES(?,?,?)",
                    (action.idempotency_key, fingerprint, encode(r)),
                )
            except DomainError as error:
                self.log(
                    db,
                    action.idempotency_key,
                    kind.upper(),
                    "web",
                    actor,
                    request_id,
                    "rejected",
                    error.reason,
                )
                failure = error
                r = {}
        if failure:
            raise failure
        return r

    def remind(self):
        with self.store.transaction() as db:
            rows = db.execute(
                "SELECT id FROM requests WHERE state!='COMPLETED' AND reminded_at IS NULL AND received_at<?",
                (self.clock() - self.reminder_seconds,),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE requests SET reminded_at=? WHERE id=?",
                    (self.clock(), row[0]),
                )
                self.log(db, uid(), "REMINDER", "worker", "system", row[0])
        return len(rows)

    def commands(self, node_id, contact=True):
        """Release only on node contact, retries bounded and persisted across restart."""
        now = self.clock()
        with self.store.transaction() as db:
            db.execute(
                "UPDATE outbox SET status='expired',error='Hết thời hạn' WHERE expires_at<=? AND status IN ('pending','gateway_received')",
                (now,),
            )
            db.execute(
                "UPDATE outbox SET status='failed',error='Đã hết số lần thử' WHERE attempts>=5 AND status IN ('pending','gateway_received')",
                (),
            )
            rows = (
                db.execute(
                    "SELECT o.* FROM outbox o JOIN requests r ON r.id=o.request_id WHERE o.target=? AND o.status IN ('pending','gateway_received') AND o.attempts<5 AND o.next_at<=? AND o.revision=r.version ORDER BY o.rowid LIMIT 4",
                    (node_id, now),
                ).fetchall()
                if contact
                else []
            )
            for row in rows:
                db.execute(
                    "UPDATE outbox SET attempts=attempts+1,next_at=? WHERE command_id=?",
                    (now + 2 ** row["attempts"], row["command_id"]),
                )
        return [json.loads(row["payload"]) for row in rows]

    def transport_error(self, command_id, reason):
        with self.store.transaction() as db:
            db.execute(
                "UPDATE outbox SET error=? WHERE command_id=?",
                (reason[:200], command_id),
            )

    def snapshot(self):
        return dict(
            tables=self.store.read(
                "SELECT t.*,o.last_seen,o.led,o.battery_mv,o.request_id AS observed_request_id,o.revision AS observed_revision FROM tables t LEFT JOIN observations o ON t.node_id=o.node_id ORDER BY t.id"
            ),
            staff=self.store.read("SELECT * FROM staff ORDER BY id"),
            requests=self.store.read(
                "SELECT * FROM requests WHERE state!='COMPLETED' ORDER BY reminded_at IS NULL,received_at"
            ),
            now=self.clock(),
        )

    def detail(self, request_id):
        with self.store.connect() as db:
            r = self.request(db, request_id)
        return dict(
            request=r,
            events=self.store.read(
                "SELECT * FROM events WHERE request_id=? ORDER BY id", (request_id,)
            ),
            assignments=self.store.read(
                "SELECT * FROM assignments WHERE request_id=? ORDER BY revision",
                (request_id,),
            ),
            commands=self.store.read(
                "SELECT * FROM outbox WHERE request_id=? ORDER BY rowid DESC LIMIT 40",
                (request_id,),
            ),
        )
