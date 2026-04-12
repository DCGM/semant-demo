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


# -------------------------------------------------------------------
# Tests for username, name, institution fields
# -------------------------------------------------------------------

TEST_USERNAME = "jannovak"
TEST_NAME = "Jan Novák"
TEST_INSTITUTION = "Masarykova univerzita"
TEST_EMAIL2 = "jan.novak@example.com"
TEST_PASSWORD2 = "AnotherStr0ng!"


@pytest.mark.asyncio
async def test_register_with_extra_fields(client: AsyncClient):
    """Registering with username, name and institution should succeed and return those fields."""
    response = await client.post(
        REGISTER_URL,
        json={
            "email": TEST_EMAIL2,
            "password": TEST_PASSWORD2,
            "username": TEST_USERNAME,
            "name": TEST_NAME,
            "institution": TEST_INSTITUTION,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["email"] == TEST_EMAIL2
    assert data["username"] == TEST_USERNAME
    assert data["name"] == TEST_NAME
    assert data["institution"] == TEST_INSTITUTION


@pytest.mark.asyncio
async def test_login_with_username(client: AsyncClient):
    """Login using username instead of email should return a valid token."""
    response = await client.post(
        LOGIN_URL,
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD2},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_current_user_has_extra_fields(client: AsyncClient):
    """GET /api/users/me should return username, name and institution."""
    login_response = await client.post(
        LOGIN_URL,
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD2},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_response.json()["access_token"]

    response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["username"] == TEST_USERNAME
    assert data["name"] == TEST_NAME
    assert data["institution"] == TEST_INSTITUTION


@pytest.mark.asyncio
async def test_patch_user_name_and_institution(client: AsyncClient):
    """PATCH /api/users/me should update name and institution."""
    login_response = await client.post(
        LOGIN_URL,
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD2},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    new_name = "Jan Novák Jr."
    new_institution = "VUT v Brně"
    response = await client.patch(
        "/api/users/me",
        json={"name": new_name, "institution": new_institution},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == new_name
    assert data["institution"] == new_institution


@pytest.mark.asyncio
async def test_duplicate_username(client: AsyncClient):
    """Registering a second account with the same username should return 400."""
    response = await client.post(
        REGISTER_URL,
        json={
            "email": "another@example.com",
            "password": TEST_PASSWORD2,
            "username": TEST_USERNAME,  # already taken
        },
    )
    assert response.status_code == 400
