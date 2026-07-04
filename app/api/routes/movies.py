"""Web panel Movies page: ``GET/POST /api/movies``, ``GET/PATCH/DELETE /api/movies/{id}``.

Thin wrappers over ``MovieService`` — the same service the bot's admin
movie-add/manage handlers use — so create/update/delete semantics (soft
delete via ``is_active``, category resolution, Redis cache invalidation)
stay identical between the bot and the web panel. Reads are open to any
active admin; mutations require ``MANAGE_MOVIES`` (moderator+, per the TZ
role table — the same threshold the bot side gates behind).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import CurrentAdmin, require_permission
from app.api.dependencies.db import DbSession
from app.api.dependencies.pagination import Pagination
from app.api.schemas.common import Page
from app.api.schemas.movie import MovieCreateRequest, MovieResponse, MovieUpdateRequest
from app.core.permissions import Permission
from app.database.models import Admin
from app.services.audit.audit_service import AuditService
from app.services.movie.movie_service import MovieService

router = APIRouter(prefix="/api/movies", tags=["movies"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kino topilmadi")

ManageMoviesAdmin = Annotated[Admin, Depends(require_permission(Permission.MANAGE_MOVIES))]


@router.get("", response_model=Page[MovieResponse])
async def list_movies(
    session: DbSession,
    _current_admin: CurrentAdmin,
    pagination: Pagination,
    q: str = "",
) -> Page[MovieResponse]:
    movies, total = await MovieService(session).search(q, pagination.page, pagination.size)
    return Page(
        items=[MovieResponse.model_validate(m) for m in movies],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get("/{movie_id}", response_model=MovieResponse)
async def get_movie(movie_id: int, session: DbSession, _current_admin: CurrentAdmin) -> MovieResponse:
    movie = await MovieService(session).get(movie_id)
    if movie is None:
        raise _NOT_FOUND
    return MovieResponse.model_validate(movie)


@router.post("", response_model=MovieResponse, status_code=status.HTTP_201_CREATED)
async def create_movie(
    body: MovieCreateRequest, request: Request, session: DbSession, current_admin: ManageMoviesAdmin
) -> MovieResponse:
    movie = await MovieService(session).create_movie(
        code=body.code,
        title=body.title,
        description=body.description,
        file_id=body.file_id,
        poster_file_id=body.poster_file_id,
        file_unique_id=body.file_unique_id,
        storage_message_id=body.storage_message_id,
        duration=body.duration,
        file_size=body.file_size,
        is_premium=body.is_premium,
        created_by=current_admin.id,
        category_ids=body.category_ids,
    )
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="movie_create",
        entity="movie",
        entity_id=str(movie.id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return MovieResponse.model_validate(movie)


@router.patch("/{movie_id}", response_model=MovieResponse)
async def update_movie(
    movie_id: int,
    body: MovieUpdateRequest,
    request: Request,
    session: DbSession,
    current_admin: ManageMoviesAdmin,
) -> MovieResponse:
    fields = body.model_dump(exclude_unset=True)
    movie = await MovieService(session).update_movie(movie_id, **fields)
    if movie is None:
        raise _NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="movie_update",
        entity="movie",
        entity_id=str(movie_id),
        payload=fields,
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return MovieResponse.model_validate(movie)


@router.delete("/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_movie(
    movie_id: int, request: Request, session: DbSession, current_admin: ManageMoviesAdmin
) -> None:
    movie = await MovieService(session).delete_movie(movie_id)
    if movie is None:
        raise _NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="movie_delete",
        entity="movie",
        entity_id=str(movie_id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
