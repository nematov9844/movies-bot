from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language: str
    is_active: bool
    is_blocked: bool
    referrer_id: int | None
    last_seen_at: datetime | None
    created_at: datetime


class UserBlockRequest(BaseModel):
    blocked: bool
