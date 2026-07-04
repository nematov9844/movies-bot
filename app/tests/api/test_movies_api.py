from httpx import AsyncClient

from app.core.constants import AdminRole
from app.tests.conftest import DEFAULT_TEST_PASSWORD


async def _auth_headers(client: AsyncClient, make_admin, session, user_id: int, role: AdminRole) -> dict:
    await make_admin(user_id, role=role)
    await session.commit()
    login = await client.post(
        "/api/auth/login", json={"user_id": user_id, "password": DEFAULT_TEST_PASSWORD}
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_list_movies_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/movies")
    assert r.status_code == 401  # HTTPBearer's own missing-credentials response


async def test_create_list_get_update_delete_movie(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 920001, AdminRole.ADMIN)

    create = await client.post(
        "/api/movies",
        json={"code": "api-test-1", "title": "API Test Movie", "file_id": "f1"},
        headers=headers,
    )
    assert create.status_code == 201
    movie = create.json()
    assert movie["code"] == "api-test-1"

    listed = await client.get("/api/movies", params={"q": "API Test"}, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    got = await client.get(f"/api/movies/{movie['id']}", headers=headers)
    assert got.status_code == 200
    assert got.json()["title"] == "API Test Movie"

    updated = await client.patch(
        f"/api/movies/{movie['id']}", json={"title": "Updated Title"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated Title"

    deleted = await client.delete(f"/api/movies/{movie['id']}", headers=headers)
    assert deleted.status_code == 204

    after_delete = await client.get(f"/api/movies/{movie['id']}", headers=headers)
    assert after_delete.status_code == 200
    assert after_delete.json()["is_active"] is False  # soft delete, row still exists


async def test_get_missing_movie_returns_404(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 920002, AdminRole.ADMIN)
    r = await client.get("/api/movies/99999999", headers=headers)
    assert r.status_code == 404
