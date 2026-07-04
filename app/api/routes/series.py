"""Web panel Series page: series/season CRUD. Episodes stay plain ``Movie`` rows —
edit/delete an individual episode through the existing ``/api/movies/{id}`` routes;
bulk-adding episodes stays bot-only (forwarding videos needs Telegram, which the web panel doesn't have).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import CurrentAdmin, require_permission
from app.api.dependencies.db import DbSession
from app.api.dependencies.pagination import Pagination
from app.api.schemas.common import Page
from app.api.schemas.movie import MovieResponse
from app.api.schemas.series import (
    SeasonCreateRequest,
    SeasonResponse,
    SeriesCreateRequest,
    SeriesResponse,
    SeriesUpdateRequest,
    SeriesWithSeasonsResponse,
)
from app.core.permissions import Permission
from app.database.models import Admin, Season
from app.services.audit.audit_service import AuditService
from app.services.series.series_service import SeriesService

router = APIRouter(prefix="/api/series", tags=["series"])

_SERIES_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Serial topilmadi")
_SEASON_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fasl topilmadi")

ManageMoviesAdmin = Annotated[Admin, Depends(require_permission(Permission.MANAGE_MOVIES))]


async def _season_response(service: SeriesService, season: Season) -> SeasonResponse:
    episode_count = await service.count_episodes(season.id)
    return SeasonResponse(
        id=season.id, series_id=season.series_id, number=season.number, is_active=season.is_active,
        episode_count=episode_count,
    )


@router.get("", response_model=Page[SeriesResponse])
async def list_series(
    session: DbSession, _current_admin: CurrentAdmin, pagination: Pagination, q: str = ""
) -> Page[SeriesResponse]:
    service = SeriesService(session)
    if q:
        series_list, total = await service.search_series(q, pagination.limit, pagination.offset)
    else:
        series_list = await service.list_all_series(pagination.limit, pagination.offset)
        total = await service.count_all_series()
    return Page(
        items=[SeriesResponse.model_validate(s) for s in series_list],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get("/{series_id}", response_model=SeriesWithSeasonsResponse)
async def get_series(series_id: int, session: DbSession, _current_admin: CurrentAdmin) -> SeriesWithSeasonsResponse:
    service = SeriesService(session)
    series = await service.get_series_with_seasons(series_id)
    if series is None:
        raise _SERIES_NOT_FOUND
    seasons = [await _season_response(service, season) for season in series.seasons]
    return SeriesWithSeasonsResponse(
        id=series.id,
        title=series.title,
        description=series.description,
        poster_file_id=series.poster_file_id,
        is_active=series.is_active,
        seasons=seasons,
    )


@router.post("", response_model=SeriesResponse, status_code=status.HTTP_201_CREATED)
async def create_series(
    body: SeriesCreateRequest, request: Request, session: DbSession, current_admin: ManageMoviesAdmin
) -> SeriesResponse:
    series = await SeriesService(session).create_series(body.title, body.description, body.poster_file_id)
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="series_create",
        entity="series",
        entity_id=str(series.id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return SeriesResponse.model_validate(series)


@router.patch("/{series_id}", response_model=SeriesResponse)
async def update_series(
    series_id: int,
    body: SeriesUpdateRequest,
    request: Request,
    session: DbSession,
    current_admin: ManageMoviesAdmin,
) -> SeriesResponse:
    fields = body.model_dump(exclude_unset=True)
    series = await SeriesService(session).update_series(series_id, **fields)
    if series is None:
        raise _SERIES_NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="series_update",
        entity="series",
        entity_id=str(series_id),
        payload=fields,
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return SeriesResponse.model_validate(series)


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_series(
    series_id: int, request: Request, session: DbSession, current_admin: ManageMoviesAdmin
) -> None:
    deleted = await SeriesService(session).delete_series(series_id)
    if not deleted:
        raise _SERIES_NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="series_delete",
        entity="series",
        entity_id=str(series_id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()


@router.post("/{series_id}/seasons", response_model=SeasonResponse, status_code=status.HTTP_201_CREATED)
async def create_season(
    series_id: int,
    body: SeasonCreateRequest,
    request: Request,
    session: DbSession,
    current_admin: ManageMoviesAdmin,
) -> SeasonResponse:
    service = SeriesService(session)
    series = await service.get_series(series_id)
    if series is None:
        raise _SERIES_NOT_FOUND
    if await service.season_number_taken(series_id, body.number):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu raqamli fasl allaqachon mavjud")

    season = await service.create_season(series_id, body.number)
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="season_create",
        entity="season",
        entity_id=str(season.id),
        payload={"series_id": series_id, "number": body.number},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return await _season_response(service, season)


@router.patch("/seasons/{season_id}", response_model=SeasonResponse)
async def update_season(
    season_id: int,
    body: SeasonCreateRequest,
    request: Request,
    session: DbSession,
    current_admin: ManageMoviesAdmin,
) -> SeasonResponse:
    service = SeriesService(session)
    season = await service.get_season(season_id)
    if season is None:
        raise _SEASON_NOT_FOUND
    if await service.season_number_taken(season.series_id, body.number, exclude_season_id=season_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu raqamli fasl allaqachon mavjud")

    updated = await service.update_season(season_id, body.number)
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="season_update",
        entity="season",
        entity_id=str(season_id),
        payload={"number": body.number},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return await _season_response(service, updated)


@router.delete("/seasons/{season_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_season(
    season_id: int, request: Request, session: DbSession, current_admin: ManageMoviesAdmin
) -> None:
    deleted = await SeriesService(session).delete_season(season_id)
    if not deleted:
        raise _SEASON_NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="season_delete",
        entity="season",
        entity_id=str(season_id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()


@router.get("/seasons/{season_id}/episodes", response_model=Page[MovieResponse])
async def list_episodes(
    season_id: int, session: DbSession, _current_admin: CurrentAdmin, pagination: Pagination
) -> Page[MovieResponse]:
    service = SeriesService(session)
    if await service.get_season(season_id) is None:
        raise _SEASON_NOT_FOUND

    episodes, total = await service.list_episodes(season_id, pagination.limit, pagination.offset)
    return Page(
        items=[MovieResponse.model_validate(e) for e in episodes],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )
