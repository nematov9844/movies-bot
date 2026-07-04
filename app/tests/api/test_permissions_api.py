"""Per the TZ: "permission tekshiruvlari (moderator settings o'zgartira olmasligi)"."""

from httpx import AsyncClient

from app.core.constants import AdminRole
from app.database.repositories.setting_repository import SettingRepository
from app.tests.conftest import DEFAULT_TEST_PASSWORD


async def _login(client: AsyncClient, make_admin, session, user_id: int, role: AdminRole) -> dict:
    await make_admin(user_id, role=role)
    await session.commit()
    login = await client.post(
        "/api/auth/login", json={"user_id": user_id, "password": DEFAULT_TEST_PASSWORD}
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_moderator_cannot_change_settings(client: AsyncClient, make_admin, session) -> None:
    await SettingRepository(session).create(key="maintenance_mode", value="false", type="bool")
    await session.commit()
    headers = await _login(client, make_admin, session, 930001, AdminRole.MODERATOR)

    r = await client.patch(
        "/api/settings/maintenance_mode", json={"value": "true"}, headers=headers
    )

    assert r.status_code == 403


async def test_admin_can_change_settings(client: AsyncClient, make_admin, session) -> None:
    await SettingRepository(session).create(key="maintenance_mode", value="false", type="bool")
    await session.commit()
    headers = await _login(client, make_admin, session, 930002, AdminRole.ADMIN)

    r = await client.patch(
        "/api/settings/maintenance_mode", json={"value": "true"}, headers=headers
    )

    assert r.status_code == 200
    assert r.json()["value"] == "true"


async def test_moderator_can_manage_movies(client: AsyncClient, make_admin, session) -> None:
    headers = await _login(client, make_admin, session, 930003, AdminRole.MODERATOR)

    r = await client.post(
        "/api/movies", json={"code": "mod-test", "title": "Mod Test", "file_id": "f1"}, headers=headers
    )

    assert r.status_code == 201


async def test_moderator_cannot_manage_admins(client: AsyncClient, make_admin, session) -> None:
    headers = await _login(client, make_admin, session, 930004, AdminRole.MODERATOR)

    r = await client.get("/api/admins", headers=headers)

    assert r.status_code == 403


async def test_owner_can_manage_admins(client: AsyncClient, make_admin, session) -> None:
    headers = await _login(client, make_admin, session, 930005, AdminRole.OWNER)

    r = await client.get("/api/admins", headers=headers)

    assert r.status_code == 200
