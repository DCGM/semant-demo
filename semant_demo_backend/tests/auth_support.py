"""Fixtures and helpers for tests that need an app with registered users.

Every test gets a fresh app and SQLite database, so tests create the users they need
and can run alone or in any order.
"""
from httpx import AsyncClient

REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/jwt/login"
ME_URL = "/api/users/me"
LOGOUT_URL = "/api/auth/jwt/logout"


async def register(client: AsyncClient, **user):
    return await client.post(REGISTER_URL, json=user)


async def login(client: AsyncClient, username: str, password: str):
    return await client.post(
        LOGIN_URL,
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


async def auth_headers(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    response = await login(client, username, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
