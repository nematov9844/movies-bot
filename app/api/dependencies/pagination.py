"""Shared ``?page=&size=`` query-parameter dependency for every list endpoint.

Per the TZ: ``?page=1&size=20``, response ``{items, total, page, size}`` —
``PageParams.offset``/``.limit`` are what repository methods take;
``page``/``size`` themselves are echoed back into the response envelope
(``app.api.schemas.common.Page``) unchanged.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query

MAX_PAGE_SIZE = 100


@dataclass(slots=True)
class PageParams:
    page: int
    size: int

    @property
    def limit(self) -> int:
        return self.size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def get_page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> PageParams:
    return PageParams(page=page, size=size)


Pagination = Annotated[PageParams, Depends(get_page_params)]
