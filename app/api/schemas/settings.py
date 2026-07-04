from datetime import datetime

from pydantic import BaseModel


class SettingResponse(BaseModel):
    model_config = {"from_attributes": True}

    key: str
    value: str
    type: str
    description: str | None
    updated_at: datetime


class SettingUpdateRequest(BaseModel):
    value: str
