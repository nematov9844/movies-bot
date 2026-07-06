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


async def test_list_categories_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/categories")
    assert r.status_code == 401


async def test_create_list_update_toggle_delete_category(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 940001, AdminRole.ADMIN)

    create = await client.post("/api/categories", json={"name": "API Jangari"}, headers=headers)
    assert create.status_code == 201
    category = create.json()
    assert category["name"] == "API Jangari"
    assert category["slug"] == "api-jangari"
    assert category["is_active"] is True

    listed = await client.get("/api/categories", headers=headers)
    assert listed.status_code == 200
    assert any(c["id"] == category["id"] for c in listed.json())

    updated = await client.patch(
        f"/api/categories/{category['id']}", json={"name": "API Jangari Kino"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["slug"] == "api-jangari-kino"

    toggled = await client.post(f"/api/categories/{category['id']}/toggle", headers=headers)
    assert toggled.status_code == 200
    assert toggled.json()["is_active"] is False

    deleted = await client.delete(f"/api/categories/{category['id']}", headers=headers)
    assert deleted.status_code == 204

    after_delete = await client.get("/api/categories", headers=headers)
    assert all(c["id"] != category["id"] for c in after_delete.json())


async def test_create_category_rejects_duplicate_name(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 940002, AdminRole.ADMIN)

    await client.post("/api/categories", json={"name": "Dublikat"}, headers=headers)
    duplicate = await client.post("/api/categories", json={"name": "Dublikat"}, headers=headers)
    assert duplicate.status_code == 409


async def test_update_missing_category_returns_404(client: AsyncClient, make_admin, session) -> None:
    headers = await _auth_headers(client, make_admin, session, 940003, AdminRole.ADMIN)
    r = await client.patch("/api/categories/99999999", json={"name": "Yangi"}, headers=headers)
    assert r.status_code == 404
