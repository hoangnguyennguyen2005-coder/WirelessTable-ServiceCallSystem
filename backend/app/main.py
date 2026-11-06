import asyncio
import csv
import io
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, field_validator
from app.config import Config
from app.db.store import Store
from app.domain.models import Strict, Action, DomainError, DeviceEvent
from app.domain.service import Service, uid
from app.adapters.serial_gateway import SerialGateway
from app.adapters.simulator import DemoClock, Simulator
from app.adapters.staff import PrototypeStaffAdapter

log = logging.getLogger(__name__)


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


class SimAction(Strict):
    action: Literal[
        "press",
        "release",
        "hidden",
        "connection",
        "fault",
        "advance",
        "burst",
        "delay",
        "reset",
    ]
    node_id: int = Field(default=1, ge=1, le=65535)
    enabled: bool = True
    fault: Literal["none", "drop_event", "drop_receipt", "duplicate"] = "none"
    seconds: float = Field(default=0, ge=0, le=3600)
    confirm: str = ""


def create_app(config: Config | None = None):
    config = config or Config.environment()
    store = Store(config.database, config.mode == "simulation")
    clock = DemoClock() if config.mode == "simulation" else time.time
    service = Service(store, clock)
    staff_adapter = PrototypeStaffAdapter(service)
    sim = (
        Simulator(service, config.poll_seconds, config.double_ms)
        if config.mode == "simulation"
        else None
    )
    gateway = SerialGateway(service, config.serial_port, config.serial_baud)

    async def worker():
        while True:
            try:
                service.remind()
                service.commands(
                    0, contact=False
                )  # expire commands, never send idle-node radio
                if sim:
                    sim.tick()
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

    app = FastAPI(title="PBL4 — Gọi phục vụ", version="1.0.0", lifespan=lifespan)
    app.state.service, app.state.simulator, app.state.config = service, sim, config

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

    def identity(request: Request, requested: int):
        if sim:
            return requested
        token = request.headers.get("x-staff-token", "")
        if (
            not config.staff_token
            or not secrets.compare_digest(token, config.staff_token)
            or requested != config.staff_id
        ):
            raise HTTPException(403, "Thiết bị nhân viên chưa xác thực")
        return config.staff_id

    def connection():
        return (
            dict(
                connected=sim.connected,
                error=None if sim.connected else "Gateway mô phỏng đã ngắt",
            )
            if sim
            else gateway.status()
        )

    @app.get("/api/health")
    def health():
        return dict(
            status="ok",
            mode=config.mode,
            gateway=connection(),
            schema=1,
            poll_seconds=config.poll_seconds,
            double_ms=config.double_ms,
        )

    @app.get("/api/snapshot")
    def snapshot():
        data = service.snapshot()
        data.update(
            mode=config.mode,
            gateway=connection(),
            simulator=sim.snapshot() if sim else None,
        )
        counts = store.read(
            "SELECT COUNT(*) AS completed,AVG(completed_at-received_at) AS average_seconds FROM requests WHERE state='COMPLETED'"
        )[0]
        data["stats"] = counts
        return data

    @app.get("/api/requests/{request_id}")
    def detail(request_id: str):
        return service.detail(request_id)

    @app.post("/api/requests/{request_id}/ack")
    def ack(request_id: str, body: Action):
        return service.action(request_id, "ack", body)

    @app.post("/api/requests/{request_id}/assign")
    def assign(request_id: str, body: Action):
        return service.action(request_id, "assign", body)

    @app.post("/api/requests/{request_id}/accept")
    def accept(request_id: str, body: Action, request: Request):
        if body.staff_id is None:
            raise HTTPException(422, "Thiếu staff_id")
        return staff_adapter.accept(request_id, identity(request, body.staff_id), body)

    @app.get("/api/staff/{staff_id}/inbox")
    def inbox(staff_id: int, request: Request):
        return staff_adapter.inbox(identity(request, staff_id))

    @app.get("/api/events")
    async def events(request: Request):
        async def stream():
            # Reconnect always emits snapshot; no unbounded subscriber queues.
            yield "event: snapshot\ndata: {}\n\n"
            last = ""
            while not await request.is_disconnected():
                marker = store.read("SELECT COALESCE(MAX(id),0) AS id FROM events")[0][
                    "id"
                ]
                current = json.dumps(
                    [marker, connection(), sim.snapshot() if sim else None],
                    sort_keys=True,
                )
                if current != last:
                    yield f"event: snapshot\ndata: {json.dumps({'cursor': marker})}\n\n"
                    last = current
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def history_rows(
        table_id=None,
        staff_id=None,
        state=None,
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
        ]:
            if value is not None:
                conditions.append(f"{column}=?")
                args.append(value)
        for operator, value in [(">=", start), ("<=", end)]:
            if value is not None:
                conditions.append(f"r.received_at{operator}?")
                args.append(value)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        total = store.read("SELECT COUNT(*) AS n FROM requests r" + where, args)[0]["n"]
        rows = store.read(
            "SELECT r.*,t.name AS table_name,s.name AS staff_name FROM requests r JOIN tables t ON t.id=r.table_id LEFT JOIN staff s ON s.id=r.staff_id"
            + where
            + " ORDER BY r.received_at DESC LIMIT ? OFFSET ?",
            [*args, limit, offset],
        )
        return dict(items=rows, total=total)

    @app.get("/api/event-log")
    def event_log(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return dict(
            items=store.read(
                "SELECT * FROM events ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ),
            total=store.read("SELECT COUNT(*) AS n FROM events")[0]["n"],
        )

    @app.get("/api/history")
    def history(
        table_id: int | None = None,
        staff_id: int | None = None,
        state: str | None = None,
        start: float | None = None,
        end: float | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return history_rows(table_id, staff_id, state, start, end, limit, offset)

    @app.get("/api/export.csv")
    def export(
        table_id: int | None = None,
        staff_id: int | None = None,
        state: str | None = None,
        start: float | None = None,
        end: float | None = None,
    ):
        def generate():
            columns = [
                "id",
                "table_name",
                "state",
                "staff_name",
                "received_at",
                "acknowledged_at",
                "completed_at",
                "closed_from",
            ]
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(columns)
            yield "\ufeff" + output.getvalue()
            offset = 0
            while True:
                rows = history_rows(table_id, staff_id, state, start, end, 200, offset)[
                    "items"
                ]
                if not rows:
                    break
                for row in rows:
                    values = []
                    for key in columns:
                        value = "" if row[key] is None else str(row[key])
                        if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                            value = "'" + value
                        values.append(value)
                    output.seek(0)
                    output.truncate(0)
                    writer.writerow(values)
                    yield output.getvalue()
                offset += len(rows)

        return StreamingResponse(
            generate(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="pbl4-history.csv"'},
        )

    @app.post("/api/config/tables")
    def table_config(body: TableConfig):
        import sqlite3

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
                db.execute(
                    "INSERT INTO tables VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET node_id=excluded.node_id,name=excluded.name,enabled=excluded.enabled",
                    (body.id, body.node_id, body.name.strip(), body.enabled),
                )
                service.log(db, uid(), "TABLE_CONFIG", "web", "manager", None)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "node_id đã được sử dụng")
        return dict(ok=True)

    @app.post("/api/config/staff")
    def staff_config(body: StaffConfig):
        with store.transaction() as db:
            db.execute(
                "INSERT INTO staff VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,active=excluded.active,available=excluded.available",
                (body.id, body.name.strip(), body.active, body.available),
            )
            service.log(db, uid(), "STAFF_CONFIG", "web", "manager", None)
        return dict(ok=True)

    if sim:

        @app.post("/api/sim/event")
        def simulate_event(body: DeviceEvent):
            return service.event(body, "simulator")

        @app.post("/api/sim/action")
        def simulate_action(body: SimAction):
            with sim.lock:
                if body.action in ("press", "release"):
                    sim.press(body.node_id, body.action == "press")
                elif body.action == "hidden":
                    sim.hidden_press(body.node_id)
                elif body.action == "connection":
                    sim.connected = body.enabled
                elif body.action == "fault":
                    sim.fault = body.fault
                elif body.action == "delay":
                    sim.delay = body.seconds
                elif body.action == "advance":
                    clock.offset += body.seconds
                    sim.tick()
                    service.remind()
                elif body.action == "burst":
                    for node_id in (1, 2, 3, 4):
                        n = sim.node(node_id)
                        if n["phase"] == "sleep":
                            sim.press(node_id, True)
                            n["hold_at"] -= 5
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
                            "assignments",
                            "correlations",
                            "requests",
                        ):
                            db.execute(f"DELETE FROM {table}")
                    sim.nodes.clear()
                    clock.offset = 0
                    sim.fault, sim.delay = "none", 0
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
