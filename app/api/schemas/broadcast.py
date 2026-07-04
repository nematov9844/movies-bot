from datetime import datetime

from pydantic import BaseModel


class BroadcastResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    admin_id: int
    target: str
    status: str
    total: int
    sent: int
    failed: int
    blocked: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
