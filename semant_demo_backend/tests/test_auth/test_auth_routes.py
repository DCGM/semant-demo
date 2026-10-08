"""
Tests for user authentication routes (register, login, current user, logout).
Each test uses a fresh app with its own temporary SQLite database (see conftest.client).
"""
from httpx import AsyncClient

from tests.auth_support import LOGOUT_URL, ME_URL, auth_headers, login, register

TEST_EMAIL = "testuser@example.com"
TEST_PASSWORD = "StrongPassw0rd!"

TEST_USERNAME = "jannovak"
TEST_NAME = "Jan Novák"
TEST_INSTITUTION = "Masarykova univerzita"
TEST_EMAIL2 = "jan.novak@example.com"
TEST_PASSWORD2 = "AnotherStr0ng!"


async def register_basic_user(client: AsyncClient):
    response = await register(client, email=TEST_EMAIL, password=TEST_PASSWORD)
    assert response.status_code == 201, response.text
    return response


async def register_user_with_profile(client: AsyncClient):
    response = await register(
        client,
        email=TEST_EMAIL2,
        password=TEST_PASSWORD2,
        username=TEST_USERNAME,
        name=TEST_NAME,
        institution=TEST_INSTITUTION,
    )
    assert response.status_code == 201, response.text
    return response


async def test_register(client: AsyncClient):
    response = await register(client, email=TEST_EMAIL, password=TEST_PASSWORD)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["email"] == TEST_EMAIL
    assert data["is_active"] is True
    assert "id" in data
    assert "hashed_password" not in data


async def test_register_duplicate_email(client: AsyncClient):
    await register_basic_user(client)

    response = await register(client, email=TEST_EMAIL, password=TEST_PASSWORD)
    assert response.status_code == 400


async def test_login(client: AsyncClient):
    await register_basic_user(client)

    response = await login(client, TEST_EMAIL, TEST_PASSWORD)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client: AsyncClient):
    await register_basic_user(client)

    response = await login(client, TEST_EMAIL, "wrongpassword")
    assert response.status_code == 400


async def test_current_user(client: AsyncClient):
    await register_basic_user(client)
    headers = await auth_headers(client, TEST_EMAIL, TEST_PASSWORD)

    response = await client.get(ME_URL, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["email"] == TEST_EMAIL


async def test_current_user_unauthenticated(client: AsyncClient):
    response = await client.get(ME_URL)
    assert response.status_code == 401


async def test_logout(client: AsyncClient):
    await register_basic_user(client)
    headers = await auth_headers(client, TEST_EMAIL, TEST_PASSWORD)

    response = await client.post(LOGOUT_URL, headers=headers)
    # JWT bearer logout returns 204 No Content (stateless, token is discarded client-side)
    assert response.status_code == 204


# -------------------------------------------------------------------
# Tests for username, name, institution fields
# -------------------------------------------------------------------

async def test_register_with_extra_fields(client: AsyncClient):
    """Registering with username, name and institution should succeed and return those fields."""
    response = await register_user_with_profile(client)
    data = response.json()
    assert data["email"] == TEST_EMAIL2
    assert data["username"] == TEST_USERNAME
    assert data["name"] == TEST_NAME
    assert data["institution"] == TEST_INSTITUTION


async def test_login_with_username(client: AsyncClient):
    """Login using username instead of email should return a valid token."""
    await register_user_with_profile(client)

    response = await login(client, TEST_USERNAME, TEST_PASSWORD2)
    assert response.status_code == 200, response.text
    assert "access_token" in response.json()


async def test_current_user_has_extra_fields(client: AsyncClient):
    """GET /api/users/me should return username, name and institution."""
    await register_user_with_profile(client)
    headers = await auth_headers(client, TEST_USERNAME, TEST_PASSWORD2)

    response = await client.get(ME_URL, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["username"] == TEST_USERNAME
    assert data["name"] == TEST_NAME
    assert data["institution"] == TEST_INSTITUTION


async def test_patch_user_name_and_institution(client: AsyncClient):
    """PATCH /api/users/me should update name and institution."""
    await register_user_with_profile(client)
    headers = await auth_headers(client, TEST_USERNAME, TEST_PASSWORD2)

    new_name = "Jan Novák Jr."
    new_institution = "VUT v Brně"
    response = await client.patch(
        ME_URL,
        json={"name": new_name, "institution": new_institution},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == new_name
    assert data["institution"] == new_institution

    # The change is persisted, not only echoed back.
    response = await client.get(ME_URL, headers=headers)
    assert response.json()["name"] == new_name
    assert response.json()["institution"] == new_institution


async def test_duplicate_username(client: AsyncClient):
    """Registering a second account with the same username should return 400."""
    await register_user_with_profile(client)

    response = await register(
        client,
        email="another@example.com",
        password=TEST_PASSWORD2,
        username=TEST_USERNAME,  # already taken
    )
    assert response.status_code == 400
