from pydantic import BaseModel, Field


class SeasonResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    series_id: int
    number: int
    is_active: bool
    episode_count: int = 0


class SeriesResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    description: str | None
    is_active: bool


class SeriesWithSeasonsResponse(SeriesResponse):
    seasons: list[SeasonResponse]


class SeriesCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class SeriesUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class SeasonCreateRequest(BaseModel):
    number: int = Field(gt=0)
