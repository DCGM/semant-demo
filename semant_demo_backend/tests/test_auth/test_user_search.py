"""
Tests for GET /api/users/search (user search by username substring).
Uses an in-memory SQLite database so no external services are needed.
"""
import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-long-enough-for-hmac-sha256-32bytes")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager


REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/jwt/login"
SEARCH_URL = "/api/users/search"

# Users registered for these tests
USERS = [
    {"email": "alice@example.com", "password": "AlicePass1!", "username": "alice_wonder"},
    {"email": "bob@example.com",   "password": "BobPass1!",   "username": "bobby_tables"},
    {"email": "carol@example.com", "password": "CarolPass1!", "username": "carol_king"},
    {"email": "dave@example.com",  "password": "DavePass1!",  "username": "davealice"},
    {"email": "eve@example.com",   "password": "EvePass1!",   "username": "eve_smith"},
]


@pytest.fixture(scope="module", autouse=True)
def set_test_db(tmp_path_factory):
    """Point SQL_DB_URL to a fresh temporary file, isolated from other test modules."""
    tmp = tmp_path_factory.mktemp("db_search")
    db_path = str(tmp / "test_user_search.db")
    os.environ["SQL_DB_URL_OVERRIDE_SEARCH"] = f"sqlite+aiosqlite:///{db_path}"
    yield
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest_asyncio.fixture(scope="module")
async def client():
    from semant_demo import config as cfg_module
    cfg_module.config.SQL_DB_URL = os.environ.get(
        "SQL_DB_URL_OVERRIDE_SEARCH", "sqlite+aiosqlite:///test_search_fallback.db"
    )
    import importlib
    import semant_demo.routes.dependencies as dep
    importlib.reload(dep)

    from semant_demo.main import app
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture(scope="module")
async def auth_token(client: AsyncClient):
    """Register all test users and return a Bearer token for the first one."""
    for user in USERS:
        await client.post(REGISTER_URL, json=user)

    login = await client.post(
        LOGIN_URL,
        data={"username": USERS[0]["email"], "password": USERS[0]["password"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return login.json()["access_token"]


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_requires_auth(client: AsyncClient):
    """Search endpoint must return 401 when no token is provided."""
    response = await client.get(SEARCH_URL, params={"q": "ali"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Minimum length validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_query_too_short_rejected(client: AsyncClient, auth_token: str):
    """Query with fewer than 3 characters must be rejected with 422."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    for short_q in ("", "a", "al"):
        response = await client.get(SEARCH_URL, params={"q": short_q}, headers=headers)
        assert response.status_code == 422, f"Expected 422 for q={short_q!r}, got {response.status_code}"


# ---------------------------------------------------------------------------
# Basic substring match
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_finds_matching_users(client: AsyncClient, auth_token: str):
    """Substring 'ali' should match 'alice_wonder' and 'davealice'."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = await client.get(SEARCH_URL, params={"q": "ali"}, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    usernames = [u["username"] for u in data]
    assert "alice_wonder" in usernames
    assert "davealice" in usernames


@pytest.mark.asyncio
async def test_search_no_results(client: AsyncClient, auth_token: str):
    """Substring that matches nothing should return an empty list."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = await client.get(SEARCH_URL, params={"q": "zzz"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == []


# ---------------------------------------------------------------------------
# Case-insensitive matching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_case_insensitive(client: AsyncClient, auth_token: str):
    """Search should be case-insensitive: 'ALI' must match 'alice_wonder'."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = await client.get(SEARCH_URL, params={"q": "ALI"}, headers=headers)
    assert response.status_code == 200, response.text
    usernames = [u["username"] for u in response.json()]
    assert "alice_wonder" in usernames


# ---------------------------------------------------------------------------
# Result count cap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_limit_4(client: AsyncClient, auth_token: str):
    """Search must return at most 4 results even when more matches exist."""
    # Register 3 extra users all sharing the substring 'limit_test'
    extra_users = [
        {"email": f"lt{i}@example.com", "password": "LimitPass1!", "username": f"limit_test_{i}"}
        for i in range(3)
    ]
    for u in extra_users:
        await client.post(REGISTER_URL, json=u)

    headers = {"Authorization": f"Bearer {auth_token}"}
    # 'limit_test' matches all 3 extra + nothing else → ≤ 4, fine
    # Now register a 4th and 5th to exceed the cap
    for i in range(3, 5):
        await client.post(
            REGISTER_URL,
            json={"email": f"lt{i}@example.com", "password": "LimitPass1!", "username": f"limit_test_{i}"},
        )

    response = await client.get(SEARCH_URL, params={"q": "limit_test"}, headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.json()) <= 4


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_response_schema(client: AsyncClient, auth_token: str):
    """Each result must have 'id' and 'username'; must NOT expose email or hashed_password."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = await client.get(SEARCH_URL, params={"q": "ali"}, headers=headers)
    assert response.status_code == 200, response.text
    for item in response.json():
        assert "id" in item
        assert "username" in item
        assert "email" not in item
        assert "hashed_password" not in item
