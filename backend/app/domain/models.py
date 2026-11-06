from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Payload(Strict):
    led: Literal["OFF", "RED", "GREEN"] | None = None
    revision: int | None = Field(default=None, ge=1)
    battery_mv: int | None = Field(default=None, ge=0, le=10000)


class DeviceEvent(Strict):
    protocol_version: Literal[1] = 1
    message_type: Literal[
        "CALL", "DONE", "STATUS_POLL", "STATUS_APPLIED", "DEVICE_STATUS", "COMMAND_ACK"
    ]
    event_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.:-]+$")
    node_id: int = Field(ge=1, le=65535)
    boot_id: int = Field(ge=0, le=4294967295)
    call_token: int = Field(ge=0, le=4294967295)
    request_id: str | None = Field(default=None, max_length=36)
    command_id: str | None = Field(default=None, max_length=36)
    payload: Payload = Field(default_factory=Payload)


class Action(Strict):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    staff_id: int | None = Field(default=None, ge=1)
    revision: int | None = Field(default=None, ge=1)
    confirm_reassign: bool = False


class DomainError(Exception):
    def __init__(self, reason: str, status: int = 409):
        self.reason, self.status = reason, status
        super().__init__(reason)
