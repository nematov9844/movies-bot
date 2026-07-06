from pydantic import BaseModel, Field


class CategoryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    slug: str
    is_active: bool


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    is_active: bool | None = None
