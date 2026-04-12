"""
Tests for user authentication routes (register, login, current user, logout).
Uses an in-memory SQLite database so no external services are needed.
"""
import os
# Use in-memory SQLite for tests
os.environ.setdefault("JWT_SECRET", "test-secret-key-long-enough-for-hmac-sha256-32bytes")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager


@pytest.fixture(scope="module", autouse=True)
def set_test_db(tmp_path_factory):
    """Point SQL_DB_URL to a temporary file so tests are isolated."""
    tmp = tmp_path_factory.mktemp("db")
    db_path = str(tmp / "test_auth.db")
    os.environ["SQL_DB_URL_OVERRIDE"] = f"sqlite+aiosqlite:///{db_path}"
    yield
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest_asyncio.fixture(scope="module")
async def client():
    # Patch DB URL before importing app
    from semant_demo import config as cfg_module
    cfg_module.config.SQL_DB_URL = os.environ.get(
        "SQL_DB_URL_OVERRIDE", "sqlite+aiosqlite:///test_auth_fallback.db"
    )
    # Re-import routes/dependencies with the patched config
    import importlib
    import semant_demo.routes.dependencies as dep
    importlib.reload(dep)

    from semant_demo.main import app
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/jwt/login"
ME_URL = "/api/users/me"
LOGOUT_URL = "/api/auth/jwt/logout"

TEST_EMAIL = "testuser@example.com"
TEST_PASSWORD = "StrongPassw0rd!"


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    response = await client.post(
        REGISTER_URL,
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["email"] == TEST_EMAIL
    assert data["is_active"] is True
    assert "id" in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    response = await client.post(
        REGISTER_URL,
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    response = await client.post(
        LOGIN_URL,
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    response = await client.post(
        LOGIN_URL,
        data={"username": TEST_EMAIL, "password": "wrongpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_current_user(client: AsyncClient):
    # First log in to get a token
    login_response = await client.post(
        LOGIN_URL,
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_response.json()["access_token"]

    response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == TEST_EMAIL


@pytest.mark.asyncio
async def test_current_user_unauthenticated(client: AsyncClient):
    response = await client.get(ME_URL)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    login_response = await client.post(
        LOGIN_URL,
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_response.json()["access_token"]

    response = await client.post(LOGOUT_URL, headers={"Authorization": f"Bearer {token}"})
    # JWT bearer logout returns 204 No Content (stateless, token is discarded client-side)
    assert response.status_code == 204
