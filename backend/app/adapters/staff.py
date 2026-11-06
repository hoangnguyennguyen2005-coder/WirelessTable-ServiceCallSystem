from typing import Protocol
from app.domain.models import Action


class StaffDeviceAdapter(Protocol):
    def inbox(self, staff_id: int) -> list[dict]: ...
    def accept(self, request_id: str, staff_id: int, action: Action) -> dict: ...


class PrototypeStaffAdapter:
    def __init__(self, service):
        self.service = service

    def inbox(self, staff_id):
        with self.service.store.transaction() as db:
            db.execute(
                "UPDATE assignments SET delivered_at=COALESCE(delivered_at,?) WHERE staff_id=? AND revoked_at IS NULL",
                (self.service.clock(), staff_id),
            )
            rows = db.execute(
                "SELECT * FROM requests WHERE staff_id=? AND state IN ('ASSIGNED','ACCEPTED')",
                (staff_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def accept(self, request_id, staff_id, action):
        # Identity was resolved at HTTP boundary; caller payload cannot override it.
        if action.staff_id != staff_id:
            from app.domain.models import DomainError

            raise DomainError("Sai nhân viên", 403)
        return self.service.action(request_id, "accept", action, f"staff:{staff_id}")
