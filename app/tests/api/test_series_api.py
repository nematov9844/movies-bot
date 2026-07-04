from httpx import AsyncClient

from app.core.constants import AdminRole
from app.services.series.series_service import SeriesService
from app.tests.conftest import DEFAULT_TEST_PASSWORD


async def _auth_headers(client: AsyncClient, make_admin, session, user_id: int, role: AdminRole) -> dict:
    await make_admin(user_id, role=role)
    await session.commit()
    login = await client.post(
        "/api/auth/login", json={"user_id": user_id, "password": DEFAULT_TEST_PASSWORD}
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_list_series_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/series")
    assert r.status_code == 401


async def test_create_list_get_update_delete_series(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 930001, AdminRole.ADMIN)

    create = await client.post(
        "/api/series", json={"title": "API Naruto", "description": "Anime"}, headers=headers
    )
    assert create.status_code == 201
    series = create.json()
    assert series["title"] == "API Naruto"

    listed = await client.get("/api/series", params={"q": "API Naruto"}, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    got = await client.get(f"/api/series/{series['id']}", headers=headers)
    assert got.status_code == 200
    assert got.json()["seasons"] == []

    updated = await client.patch(
        f"/api/series/{series['id']}", json={"title": "Renamed"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Renamed"

    deleted = await client.delete(f"/api/series/{series['id']}", headers=headers)
    assert deleted.status_code == 204

    after_delete = await client.get(f"/api/series/{series['id']}", headers=headers)
    assert after_delete.status_code == 404


async def test_get_missing_series_returns_404(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 930002, AdminRole.ADMIN)
    r = await client.get("/api/series/99999999", headers=headers)
    assert r.status_code == 404


async def test_create_season_and_reject_duplicate_number(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 930003, AdminRole.ADMIN)

    series = (await client.post("/api/series", json={"title": "Bleach"}, headers=headers)).json()

    created = await client.post(
        f"/api/series/{series['id']}/seasons", json={"number": 1}, headers=headers
    )
    assert created.status_code == 201
    assert created.json()["episode_count"] == 0

    duplicate = await client.post(
        f"/api/series/{series['id']}/seasons", json={"number": 1}, headers=headers
    )
    assert duplicate.status_code == 409

    with_seasons = await client.get(f"/api/series/{series['id']}", headers=headers)
    assert len(with_seasons.json()["seasons"]) == 1


async def test_update_season_number_and_reject_duplicate(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 930006, AdminRole.ADMIN)

    series = (await client.post("/api/series", json={"title": "Attack on Titan"}, headers=headers)).json()
    season_1 = (
        await client.post(f"/api/series/{series['id']}/seasons", json={"number": 1}, headers=headers)
    ).json()
    await client.post(f"/api/series/{series['id']}/seasons", json={"number": 2}, headers=headers)

    renamed = await client.patch(
        f"/api/series/seasons/{season_1['id']}", json={"number": 5}, headers=headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["number"] == 5

    # Renumbering to itself (no-op) must not spuriously conflict.
    unchanged = await client.patch(
        f"/api/series/seasons/{season_1['id']}", json={"number": 5}, headers=headers
    )
    assert unchanged.status_code == 200

    conflict = await client.patch(
        f"/api/series/seasons/{season_1['id']}", json={"number": 2}, headers=headers
    )
    assert conflict.status_code == 409


async def test_list_episodes_and_delete_season(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 930004, AdminRole.ADMIN)

    series = (await client.post("/api/series", json={"title": "One Piece"}, headers=headers)).json()
    season = (
        await client.post(f"/api/series/{series['id']}/seasons", json={"number": 1}, headers=headers)
    ).json()

    service = SeriesService(session)
    episode = await service.add_episode(
        season_id=season["id"],
        series_title="One Piece",
        season_number=1,
        file_id="f1",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
    )
    await session.commit()

    episodes = await client.get(f"/api/series/seasons/{season['id']}/episodes", headers=headers)
    assert episodes.status_code == 200
    assert episodes.json()["total"] == 1
    assert episodes.json()["items"][0]["code"] == episode.code

    deleted_season = await client.delete(f"/api/series/seasons/{season['id']}", headers=headers)
    assert deleted_season.status_code == 204

    # The episode itself must survive as a standalone movie, editable via /api/movies/{id}.
    still_there = await client.get(f"/api/movies/{episode.id}", headers=headers)
    assert still_there.status_code == 200


async def test_missing_season_episodes_returns_404(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 930005, AdminRole.ADMIN)
    r = await client.get("/api/series/seasons/99999999/episodes", headers=headers)
    assert r.status_code == 404


async def test_create_and_update_series_poster(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 930007, AdminRole.ADMIN)

    create = await client.post(
        "/api/series", json={"title": "Poster Series", "poster_file_id": "poster-1"}, headers=headers
    )
    assert create.status_code == 201
    assert create.json()["poster_file_id"] == "poster-1"

    updated = await client.patch(
        f"/api/series/{create.json()['id']}", json={"poster_file_id": "poster-2"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["poster_file_id"] == "poster-2"

    fetched = await client.get(f"/api/series/{create.json()['id']}", headers=headers)
    assert fetched.json()["poster_file_id"] == "poster-2"
