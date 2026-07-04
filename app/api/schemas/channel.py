from datetime import datetime, time

from pydantic import BaseModel, Field


class ChannelResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    channel_id: int
    username: str | None
    title: str
    invite_link: str | None
    priority: int
    is_active: bool
    is_required: bool
    start_date: datetime | None
    expire_date: datetime | None
    daily_start_time: time | None
    daily_end_time: time | None
    join_limit: int | None
    current_joins: int
    created_at: datetime


class ChannelCreateRequest(BaseModel):
    channel_id: int
    title: str = Field(min_length=1, max_length=255)
    username: str | None = None
    invite_link: str | None = None
    priority: int = 0
    join_limit: int | None = None
    start_date: datetime | None = None
    expire_date: datetime | None = None
    daily_start_time: time | None = None
    daily_end_time: time | None = None


class ChannelUpdateRequest(BaseModel):
    priority: int | None = None
    join_limit: int | None = None
    start_date: datetime | None = None
    expire_date: datetime | None = None
    daily_start_time: time | None = None
    daily_end_time: time | None = None
    is_required: bool | None = None
