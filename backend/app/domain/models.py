"""Wire and action models. Names follow the ECE411 logbook (Step 1 workflow, Step 3 ER set)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROTOCOL_VERSION = 2
# Fixed by the Step 1 workflow (C-01) and ER-P02; not operator-configurable.
HOLD_SECONDS = 5.0
REGISTRATION_SECONDS = 5.0

Category = Literal["SERVICE", "BILL"]
Led = Literal["OFF", "RED", "GREEN"]
TaskState = Literal["SHOWN", "ACCEPTED", "CLEARED"]

TABLE_EVENTS = (
    "CALL",
    "DONE",
    "STATUS_POLL",
    "STATUS_APPLIED",
    "DEVICE_STATUS",
    "NODE_HELLO",
)
STAFF_EVENTS = ("STAFF_POLL", "STAFF_APPLIED", "STAFF_ACCEPT")

# ER-F11: the eight observable event types, followed by auxiliary audit types.
EVENT_TYPES = (
    "REGISTERED",
    "ACKNOWLEDGED",
    "DISPATCHED",
    "ACCEPTED",
    "OVERDUE",
    "COMPLETED",
    "DUPLICATE",
    "FAILURE",
    "DELIVERED",
    "DISPATCH_CANCELLED",
    "RECONCILED",
    "BATTERY_LOW",
    "CONFIG",
    "CENTRE_START",
    "GATEWAY_CONNECTED",
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Payload(Strict):
    category: Category | None = None
    led: Led | None = None
    revision: int | None = Field(default=None, ge=0, le=4294967295)
    battery_mv: int | None = Field(default=None, ge=0, le=10000)
    battery_low: bool | None = None
    assignment_revision: int | None = Field(default=None, ge=1, le=4294967295)
    request_seq: int | None = Field(default=None, ge=1, le=4294967295)
    task: TaskState | None = None


class DeviceEvent(Strict):
    """One frame from the USB gateway. node_id is the sending endpoint: table node or staff device."""

    protocol_version: Literal[2] = PROTOCOL_VERSION
    venue_id: int = Field(ge=1, le=65535)
    message_type: Literal[
        "CALL",
        "DONE",
        "STATUS_POLL",
        "STATUS_APPLIED",
        "DEVICE_STATUS",
        "NODE_HELLO",
        "COMMAND_ACK",
        "STAFF_POLL",
        "STAFF_APPLIED",
        "STAFF_ACCEPT",
    ]
    event_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.:-]+$")
    node_id: int = Field(ge=1, le=65535)
    boot_id: int = Field(default=0, ge=0, le=4294967295)
    call_token: int = Field(default=0, ge=0, le=4294967295)
    request_id: str | None = Field(default=None, max_length=36)
    command_id: str | None = Field(default=None, max_length=36)
    payload: Payload = Field(default_factory=Payload)

    @model_validator(mode="after")
    def required_fields(self):
        kind, payload = self.message_type, self.payload
        if kind == "CALL" and payload.category is None:
            raise ValueError("CALL requires payload.category (SERVICE or BILL)")
        if kind == "STATUS_APPLIED" and (
            payload.led is None or payload.revision is None
        ):
            raise ValueError("STATUS_APPLIED requires payload.led and payload.revision")
        if kind == "COMMAND_ACK" and not self.command_id:
            raise ValueError("COMMAND_ACK requires command_id")
        if kind in ("STAFF_APPLIED", "STAFF_ACCEPT"):
            if payload.assignment_revision is None:
                raise ValueError(f"{kind} requires payload.assignment_revision")
            if self.request_id is None and payload.request_seq is None:
                raise ValueError(f"{kind} requires request_id or payload.request_seq")
        if kind == "STAFF_APPLIED" and payload.task is None:
            raise ValueError("STAFF_APPLIED requires payload.task")
        return self


class Action(Strict):
    """Manager action from the dashboard."""

    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    staff_id: int | None = Field(default=None, ge=1)
    confirm: bool = False


class DomainError(Exception):
    def __init__(self, reason: str, status: int = 409):
        self.reason, self.status = reason, status
        super().__init__(reason)
