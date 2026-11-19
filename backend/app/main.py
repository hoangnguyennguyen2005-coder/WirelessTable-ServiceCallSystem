import asyncio
import csv
import io
import json
import logging
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, field_validator

from app.adapters.serial_gateway import SerialGateway
from app.adapters.simulator import DemoClock, Simulator
from app.adapters.staff import VirtualStaffHub
from app.config import Config
from app.db.store import SCHEMA_VERSION, Store
from app.domain.models import (
    HOLD_SECONDS,
    PROTOCOL_VERSION,
    Action,
    Category,
    DeviceEvent,
    DomainError,
    Strict,
)
from app.domain.service import Service, iso

log = logging.getLogger(__name__)

EVENT_COLUMNS = [
    "id",
    "time",
    "epoch",
    "event",
    "table_id",
    "table_name",
    "category",
    "request_seq",
    "request_id",
    "staff_id",
    "staff_name",
    "source",
    "actor",
    "detail",
]
HISTORY_COLUMNS = [
    "seq",
    "id",
    "table_name",
    "category",
    "state",
    "staff_name",
    "registered_at",
    "acknowledged_at",
    "dispatched_at",
    "delivered_at",
    "accepted_at",
    "completed_at",
    "overdue_at",
    "wait_seconds",
    "closed_from",
]


class NamedConfig(Strict):
    @field_validator("name", check_fields=False)
    @classmethod
    def non_blank(cls, value: str):
        if not value.strip():
            raise ValueError("Tên không được để trống")
        return value.strip()


class TableConfig(NamedConfig):
    id: int = Field(ge=1, le=65535)
    node_id: int = Field(ge=1, le=65535)
    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True


class StaffConfig(NamedConfig):
    id: int = Field(ge=1, le=65535)
    name: str = Field(min_length=1, max_length=80)
    active: bool = True
    available: bool = True
    device_id: int | None = Field(default=None, ge=1, le=65535)


class StaffPress(Strict):
    request_id: str = Field(min_length=1, max_length=36)


class SimAction(Strict):
    action: Literal[
        "press",
        "release",
        "hidden",
        "restart",
        "battery",
        "staff_power",
        "connection",
        "fault",
        "advance",
        "burst",
        "delay",
        "reset",
    ]
    node_id: int = Field(default=1, ge=1, le=65535)
    staff_id: int = Field(default=1, ge=1, le=65535)
    category: Category = "SERVICE"
    enabled: bool = True
    fault: Literal["none", "drop_event", "drop_receipt", "duplicate"] = "none"
    seconds: float = Field(default=0, ge=0, le=3600)
    confirm: str = ""


def safe_cell(value):
    """CSV text that a spreadsheet will not evaluate as a formula."""
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def csv_response(columns, rows, filename):
    def generate():
        output = io.StringIO()
        writer = csv.writer(output)  # RFC 4180: comma separated, CRLF, quoted when needed
        writer.writerow(columns)
        yield "﻿" + output.getvalue()
        for row in rows:
            output.seek(0)
            output.truncate(0)
            writer.writerow([safe_cell(value) for value in row])
            yield output.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def create_app(config: Config | None = None):
    config = config or Config.environment()
    opened = time.perf_counter()
    store = Store(config.database, config.mode == "simulation", config.venue_id)
    clock = DemoClock() if config.mode == "simulation" else time.time
    service = Service(
        store,
        clock,
        config.reminder_seconds,
        unresolved_seconds=config.unresolved_seconds,
        poll_seconds=config.poll_seconds,
        staff_poll_seconds=config.staff_poll_seconds,
        low_battery_mv=config.low_battery_mv,
        retention_days=config.retention_days,
    )
    sim = (
        Simulator(
            service, config.poll_seconds, config.double_ms, config.staff_poll_seconds
        )
        if config.mode == "simulation"
        else None
    )
    # Hardware profile: dedicated staff devices arrive through the gateway. A virtual device is
    # hosted only when a token is configured, as a labelled bench stub for integration work.
    stub = (
        VirtualStaffHub(service, config.staff_poll_seconds, "stub", config.staff_id)
        if not sim and config.staff_token
        else None
    )
    gateway = SerialGateway(service, config.serial_port, config.serial_baud)
    # ER-R04: every request whose registered indication was authorised is back after a restart.
    recovered = len(service.snapshot()["requests"])
    startup = dict(
        recovered_active=recovered,
        recovery_ms=round((time.perf_counter() - opened) * 1000, 1),
        started_at=clock(),
    )
    service.note(
        "CENTRE_START", f"active={recovered};recovery_ms={startup['recovery_ms']}"
    )

    async def worker():
        beat, pruned = 0, float("-inf")
        while True:
            try:
                if sim:
                    sim.tick()
                elif stub:
                    stub.tick()
                beat += 1
                if beat % 5 == 0:
                    with sim.lock if sim else nullcontext():
                        service.remind()
                        # Expire/fail stored commands; nothing is ever radioed to idle nodes.
                        service.commands(0, contact=False)
                        service.watch()
                if time.monotonic() - pruned > 3600:
                    pruned = time.monotonic()
                    service.prune()
            except Exception:
                log.exception("Worker iteration failed")
            await asyncio.sleep(0.1)

    @asynccontextmanager
    async def lifespan(app):
        if not sim:
            gateway.start()
        task = asyncio.create_task(worker())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        gateway.stop()

    app = FastAPI(title="PBL4 — Gọi phục vụ", version="2.0.0", lifespan=lifespan)
    app.state.service, app.state.simulator, app.state.config = service, sim, config
    app.state.staff_stub = stub

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse(status_code=error.status, content=dict(detail=error.reason))

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        # LAN unsupported deliberately. Uvicorn must also bind loopback.
        host = request.url.hostname
        if host not in ("localhost", "127.0.0.1", "::1", "testserver"):
            return JSONResponse(
                status_code=403, content=dict(detail="Chỉ hỗ trợ truy cập loopback")
            )
        if request.client and request.client.host not in (
            "127.0.0.1",
            "::1",
            "testclient",
        ):
            return JSONResponse(
                status_code=403, content=dict(detail="LAN chưa được bật")
            )
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            allowed = {
                str(request.base_url).rstrip("/"),
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            }
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin and origin not in allowed
            ):
                return JSONResponse(
                    status_code=403, content=dict(detail="Origin không hợp lệ")
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    def staff_hub(request: Request, staff_id: int):
        """Virtual staff device host for this request, with the lock that guards it."""
        if sim:
            return sim.staff, sim.lock, sim.connected
        if stub is None:
            raise HTTPException(
                404, "Chế độ phần cứng dùng thiết bị nhân viên chuyên dụng qua gateway"
            )
        token = request.headers.get("x-staff-token", "")
        if (
            not secrets.compare_digest(token.encode(), config.staff_token.encode())
            or staff_id != config.staff_id
        ):
            raise HTTPException(403, "Thiết bị nhân viên chưa xác thực")
        return stub, stub.lock, True

    def connection():
        return (
            dict(
                connected=sim.connected,
                error=None if sim.connected else "Gateway mô phỏng đã ngắt",
            )
            if sim
            else gateway.status()
        )

    def ui_state():
        if sim:
            return sim.snapshot()
        return stub.snapshot() if stub else None

    @app.get("/api/health")
    def health():
        return dict(
            status="ok",
            mode=config.mode,
            venue_id=config.venue_id,
            schema=SCHEMA_VERSION,
            protocol_version=PROTOCOL_VERSION,
            gateway=connection(),
            limits=service.limits(),
            poll_seconds=config.poll_seconds,
            double_ms=config.double_ms,
            low_battery_mv=config.low_battery_mv,
            staff_stub=stub is not None,
            startup=startup,
        )

    @app.get("/api/snapshot")
    def snapshot():
        simulator = sim.snapshot() if sim else None
        data = service.snapshot()
        data.update(
            mode=config.mode,
            gateway=connection(),
            simulator=simulator,
            staff_stub=stub is not None,
            double_ms=config.double_ms,
            # Changes whenever the store commits; lists outside the snapshot reload on it.
            generation=store.generation,
        )
        data["stats"] = store.read(
            "SELECT COUNT(*) AS completed,AVG(completed_at-received_at) AS average_seconds FROM requests WHERE state='COMPLETED'"
        )[0]
        return data

    @app.get("/api/requests/{request_id}")
    def detail(request_id: str):
        return service.detail(request_id)

    @app.post("/api/requests/{request_id}/ack")
    def ack(request_id: str, body: Action):
        return service.action(request_id, "ack", body)

    @app.post("/api/requests/{request_id}/dispatch")
    def dispatch(request_id: str, body: Action):
        return service.action(request_id, "dispatch", body)

    @app.post("/api/requests/{request_id}/cancel-dispatch")
    def cancel_dispatch(request_id: str, body: Action):
        return service.action(request_id, "cancel_dispatch", body)

    @app.post("/api/requests/{request_id}/retry-dispatch")
    def retry_dispatch(request_id: str, body: Action):
        return service.action(request_id, "retry_dispatch", body)

    # No completion endpoint exists: a request closes only by the double press at the table.

    @app.get("/api/staff-device/{staff_id}")
    def staff_device(staff_id: int, request: Request):
        hub, lock, _ = staff_hub(request, staff_id)
        with lock:
            return hub.device(staff_id).snapshot(service.clock())

    @app.post("/api/staff-device/{staff_id}/accept")
    def staff_accept(staff_id: int, body: StaffPress, request: Request):
        hub, lock, link_up = staff_hub(request, staff_id)
        with lock:
            device = hub.device(staff_id)
            device.accept(body.request_id, service.clock(), link_up)
            return device.snapshot(service.clock())

    @app.get("/api/events")
    async def events(request: Request):
        async def stream():
            # Reconnect always emits snapshot; no unbounded subscriber queues.
            yield "event: snapshot\ndata: {}\n\n"
            last, idle = None, 0
            while not await request.is_disconnected():
                link = connection()
                current = json.dumps(
                    [store.generation, link["connected"], link["error"], ui_state()],
                    sort_keys=True,
                )
                if current != last:
                    yield f"event: snapshot\ndata: {json.dumps({'cursor': store.generation})}\n\n"
                    last, idle = current, 0
                else:
                    idle += 1
                    if idle % 4 == 0:
                        yield ": keepalive\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/event-log")
    def event_log(
        kind: str | None = Query(None, alias="type"),
        table_id: int | None = None,
        start: float | None = None,
        end: float | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return service.event_log(kind, table_id, start, end, limit, offset)

    @app.get("/api/events.csv")
    def events_csv(
        kind: str | None = Query(None, alias="type"),
        table_id: int | None = None,
        start: float | None = None,
        end: float | None = None,
    ):
        """ER-F11 event record: central ISO 8601 time, no guest identifiers."""

        def rows():
            after = 0
            while True:
                items = service.event_log(
                    kind, table_id, start, end, 200, 0, ascending=True, after_id=after
                )["items"]
                if not items:
                    break
                for e in items:
                    yield [
                        e["id"],
                        iso(e["received_at"]),
                        e["received_at"],
                        e["type"],
                        e["table_id"],
                        e["table_name"],
                        e["category"],
                        e["request_seq"],
                        e["request_id"],
                        e["staff_id"],
                        e["staff_name"],
                        e["source"],
                        e["actor"],
                        e["reason"],
                    ]
                after = items[-1]["id"]

        return csv_response(EVENT_COLUMNS, rows(), "pbl4-events.csv")

    @app.get("/api/history")
    def history(
        table_id: int | None = None,
        staff_id: int | None = None,
        state: str | None = None,
        category: str | None = None,
        start: float | None = None,
        end: float | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return service.history(
            table_id, staff_id, state, category, start, end, limit, offset
        )

    @app.get("/api/export.csv")
    def export(
        table_id: int | None = None,
        staff_id: int | None = None,
        state: str | None = None,
        category: str | None = None,
        start: float | None = None,
        end: float | None = None,
    ):
        def rows():
            offset = 0
            while True:
                items = service.history(
                    table_id, staff_id, state, category, start, end, 200, offset
                )["items"]
                if not items:
                    break
                for r in items:
                    closed = r["completed_at"]
                    yield [
                        r["seq"],
                        r["id"],
                        r["table_name"],
                        r["category"],
                        r["state"],
                        r["staff_name"],
                        iso(r["received_at"]),
                        iso(r["acknowledged_at"]),
                        iso(r["dispatched_at"]),
                        iso(r["delivered_at"]),
                        iso(r["accepted_at"]),
                        iso(closed),
                        iso(r["reminded_at"]),
                        "" if closed is None else round(closed - r["received_at"], 1),
                        r["closed_from"],
                    ]
                offset += len(items)

        return csv_response(HISTORY_COLUMNS, rows(), "pbl4-history.csv")

    @app.post("/api/config/tables")
    def table_config(body: TableConfig):
        try:
            with store.transaction() as db:
                old = db.execute(
                    "SELECT node_id FROM tables WHERE id=?", (body.id,)
                ).fetchone()
                active = db.execute(
                    "SELECT id FROM requests WHERE table_id=? AND state!='COMPLETED'",
                    (body.id,),
                ).fetchone()
                if active and (not body.enabled or old["node_id"] != body.node_id):
                    raise DomainError("Không đổi node/tắt bàn đang có yêu cầu")
                if db.execute(
                    "SELECT 1 FROM staff WHERE device_id=?", (body.node_id,)
                ).fetchone():
                    raise DomainError("ID này đang là thiết bị nhân viên")
                db.execute(
                    "INSERT INTO tables(id,node_id,name,enabled) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET node_id=excluded.node_id,name=excluded.name,enabled=excluded.enabled",
                    (body.id, body.node_id, body.name.strip(), body.enabled),
                )
                service.log(
                    db,
                    "CONFIG",
                    source="web",
                    actor="manager",
                    table_id=body.id,
                    reason=f"table={body.id};node={body.node_id};enabled={int(body.enabled)}",
                )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "node_id đã được sử dụng")
        return dict(ok=True)

    @app.post("/api/config/staff")
    def staff_config(body: StaffConfig):
        try:
            with store.transaction() as db:
                old = db.execute(
                    "SELECT device_id FROM staff WHERE id=?", (body.id,)
                ).fetchone()
                busy = db.execute(
                    "SELECT 1 FROM requests WHERE staff_id=? AND state!='COMPLETED'",
                    (body.id,),
                ).fetchone()
                if busy and (
                    not body.active or (old and old["device_id"] != body.device_id)
                ):
                    raise DomainError(
                        "Không đổi thiết bị/tắt nhân viên đang có việc được giao"
                    )
                if (
                    body.device_id is not None
                    and db.execute(
                        "SELECT 1 FROM tables WHERE node_id=?", (body.device_id,)
                    ).fetchone()
                ):
                    raise DomainError("ID thiết bị trùng node_id của một bàn")
                db.execute(
                    "INSERT INTO staff(id,name,active,available,device_id) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,active=excluded.active,available=excluded.available,device_id=excluded.device_id",
                    (
                        body.id,
                        body.name.strip(),
                        body.active,
                        body.available,
                        body.device_id,
                    ),
                )
                service.log(
                    db,
                    "CONFIG",
                    source="web",
                    actor="manager",
                    staff_id=body.id,
                    reason=f"staff={body.id};device={body.device_id};active={int(body.active)}",
                )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "ID thiết bị đã gán cho nhân viên khác")
        return dict(ok=True)

    if sim:

        @app.post("/api/sim/event")
        def simulate_event(body: DeviceEvent):
            return service.event(body, "simulator")

        @app.post("/api/sim/action")
        def simulate_action(body: SimAction):
            with sim.lock:
                if body.action in ("press", "release"):
                    sim.press(body.node_id, body.action == "press", body.category)
                elif body.action == "hidden":
                    sim.hidden_press(body.node_id)
                elif body.action == "restart":
                    sim.restart(body.node_id)
                elif body.action == "battery":
                    sim.battery(body.node_id, body.enabled)
                elif body.action == "staff_power":
                    sim.staff.power(body.staff_id, body.enabled, clock())
                elif body.action == "connection":
                    sim.connected = body.enabled
                elif body.action == "fault":
                    sim.fault = body.fault
                    # With node_id the fault waits for that table's next frame.
                    sim.fault_node = (
                        body.node_id
                        if body.fault != "none" and "node_id" in body.model_fields_set
                        else None
                    )
                elif body.action == "delay":
                    sim.delay = body.seconds
                elif body.action == "advance":
                    clock.offset += body.seconds
                    sim.tick()
                    service.remind()
                elif body.action == "burst":
                    for index, node_id in enumerate((1, 2, 3, 4)):
                        n = sim.node(node_id)
                        if n["phase"] == "sleep":
                            sim.press(
                                node_id, True, "BILL" if index % 2 else "SERVICE"
                            )
                            n["hold_at"] -= HOLD_SECONDS
                    sim.tick()
                elif body.action == "reset":
                    if body.confirm != "RESET DEMO":
                        raise HTTPException(422, "Cần xác nhận RESET DEMO")
                    with store.transaction() as db:
                        for table in (
                            "outbox",
                            "processed",
                            "actions",
                            "events",
                            "observations",
                            "staff_observations",
                            "assignments",
                            "correlations",
                            "requests",
                        ):
                            db.execute(f"DELETE FROM {table}")
                    sim.reset()
                    service.forget()
                    clock.offset = 0
            return sim.snapshot()

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        @app.get("/staff")
        def frontend():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
