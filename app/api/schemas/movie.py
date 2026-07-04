from datetime import datetime

from pydantic import BaseModel, Field


class MovieResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    code: str
    title: str
    description: str | None
    file_id: str
    quality: str | None
    duration: int | None
    file_size: int | None
    year: int | None
    is_premium: bool
    is_active: bool
    view_count: int
    created_at: datetime
    updated_at: datetime


class MovieCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    file_id: str = Field(min_length=1)
    file_unique_id: str | None = None
    storage_message_id: int | None = None
    duration: int | None = None
    file_size: int | None = None
    quality: str | None = None
    year: int | None = None
    is_premium: bool = False
    category_ids: list[int] | None = None


class MovieUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_premium: bool | None = None
    is_active: bool | None = None
    category_ids: list[int] | None = None
