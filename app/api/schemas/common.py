from pydantic import BaseModel


class Page[ItemT](BaseModel):
    """The ``{items, total, page, size}`` envelope every list endpoint returns, per the TZ."""

    items: list[ItemT]
    total: int
    page: int
    size: int
