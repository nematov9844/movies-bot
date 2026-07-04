from httpx import AsyncClient

from app.core.constants import AdminRole
from app.tests.conftest import DEFAULT_TEST_PASSWORD


async def test_login_success(client: AsyncClient, make_admin, session) -> None:
    await make_admin(910001, role=AdminRole.ADMIN)
    await session.commit()

    r = await client.post(
        "/api/auth/login", json={"user_id": 910001, "password": DEFAULT_TEST_PASSWORD}
    )

    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_login_wrong_password(client: AsyncClient, make_admin, session) -> None:
    await make_admin(910002, role=AdminRole.ADMIN)
    await session.commit()

    r = await client.post("/api/auth/login", json={"user_id": 910002, "password": "wrong"})

    assert r.status_code == 401


async def test_login_unknown_user(client: AsyncClient) -> None:
    r = await client.post("/api/auth/login", json={"user_id": 999999999, "password": "x"})
    assert r.status_code == 401


async def test_refresh_issues_new_token_pair(client: AsyncClient, make_admin, session) -> None:
    await make_admin(910003, role=AdminRole.ADMIN)
    await session.commit()

    login = await client.post(
        "/api/auth/login", json={"user_id": 910003, "password": DEFAULT_TEST_PASSWORD}
    )
    refresh_token = login.json()["refresh_token"]

    r = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    assert "access_token" in r.json()


async def test_me_requires_valid_token(client: AsyncClient) -> None:
    r = await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


async def test_me_returns_current_admin(client: AsyncClient, make_admin, session) -> None:
    await make_admin(910004, role=AdminRole.OWNER)
    await session.commit()

    login = await client.post(
        "/api/auth/login", json={"user_id": 910004, "password": DEFAULT_TEST_PASSWORD}
    )
    token = login.json()["access_token"]

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"user_id": 910004, "role": "owner"}
