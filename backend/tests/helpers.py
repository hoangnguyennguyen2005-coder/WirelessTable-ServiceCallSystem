"""Shared builders for device frames and manager actions."""

from uuid import uuid4

from app.domain.models import Action, DeviceEvent

STAFF_DEVICE = {1: 101, 2: 102}  # demo seed: staff id → device id


def event(kind="CALL", token=1, node_id=1, boot_id=123, category="SERVICE", **kwargs):
    payload = dict(kwargs.pop("payload", {}))
    if kind == "CALL":
        payload.setdefault("category", category)
    return DeviceEvent(
        venue_id=kwargs.pop("venue_id", 1),
        message_type=kind,
        event_id=kwargs.pop("event_id", str(uuid4())),
        node_id=node_id,
        boot_id=boot_id,
        call_token=token,
        payload=payload,
        **kwargs,
    )


def staff_event(kind="STAFF_POLL", staff_id=1, boot_id=777, request=None, **payload):
    """Frame from the staff device of a seeded staff member."""
    if request is not None:
        payload.setdefault("assignment_revision", request["assignment_revision"])
    return DeviceEvent(
        venue_id=1,
        message_type=kind,
        event_id=str(uuid4()),
        node_id=STAFF_DEVICE[staff_id],
        boot_id=boot_id,
        request_id=request["id"] if request else None,
        payload=payload,
    )


def act(version, **kwargs):
    return Action(expected_version=version, idempotency_key=str(uuid4()), **kwargs)


def kinds(service, request_id=None):
    """Event record types in order, optionally for one request."""
    items = service.event_log(limit=200, ascending=True)["items"]
    return [e["type"] for e in items if request_id is None or e["request_id"] == request_id]


def deliver(service, request, staff_id=1, boot_id=777):
    """Staff device polls, receives the dispatch and reports it as shown."""
    frames = service.exchange(staff_event("STAFF_POLL", staff_id, boot_id))
    shown = [f for f in frames if f["message_type"] == "DISPATCH"]
    for frame in shown:
        service.event(
            staff_event(
                "STAFF_APPLIED",
                staff_id,
                boot_id,
                request=dict(
                    id=frame["request_id"],
                    assignment_revision=frame["payload"]["assignment_revision"],
                ),
                task="SHOWN",
            )
        )
    return frames


def accept(service, request, staff_id=1, boot_id=777):
    return service.exchange(staff_event("STAFF_ACCEPT", staff_id, boot_id, request=request))
