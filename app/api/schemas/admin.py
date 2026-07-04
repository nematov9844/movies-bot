from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import AdminRole


class AdminResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    role: AdminRole
    is_active: bool
    created_at: datetime


class AdminCreateRequest(BaseModel):
    user_id: int
    role: AdminRole
    password: str = Field(min_length=6)
