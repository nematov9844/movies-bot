from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    admin_id: int | None
    action: str
    entity: str
    entity_id: str | None
    payload: dict[str, Any] | None
    ip: str | None
    created_at: datetime
