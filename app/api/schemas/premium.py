from datetime import datetime

from pydantic import BaseModel, Field


class PremiumPlanResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    days: int
    price: int
    is_active: bool


class PremiumPlanCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    days: int = Field(gt=0)
    price: int = Field(ge=0)


class PremiumPlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    days: int | None = Field(default=None, gt=0)
    price: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class PremiumUserResponse(BaseModel):
    id: int
    user_id: int
    username: str | None
    plan_id: int
    plan_name: str
    starts_at: datetime
    expires_at: datetime
    payment_method: str | None


class PremiumGrantRequest(BaseModel):
    user_id: int
    plan_id: int
    payment_method: str | None = None
