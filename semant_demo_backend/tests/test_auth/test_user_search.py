"""
Tests for GET /api/users/search (user search by username substring).
Each test uses a fresh app with its own temporary SQLite database (see conftest.client).
"""
import pytest
from httpx import AsyncClient

from tests.auth_support import auth_headers, register

SEARCH_URL = "/api/users/search"

# Users registered for these tests
USERS = [
    {"email": "alice@example.com", "password": "AlicePass1!", "username": "alice_wonder"},
    {"email": "bob@example.com",   "password": "BobPass1!",   "username": "bobby_tables"},
    {"email": "carol@example.com", "password": "CarolPass1!", "username": "carol_king"},
    {"email": "dave@example.com",  "password": "DavePass1!",  "username": "davealice"},
    {"email": "eve@example.com",   "password": "EvePass1!",   "username": "eve_smith"},
]


async def register_all(client: AsyncClient, users: list[dict]) -> None:
    for user in users:
        response = await register(client, **user)
        assert response.status_code == 201, response.text


@pytest.fixture
async def headers(client: AsyncClient) -> dict[str, str]:
    """Register all test users and return auth headers for the first one."""
    await register_all(client, USERS)
    return await auth_headers(client, USERS[0]["email"], USERS[0]["password"])


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

async def test_search_requires_auth(client: AsyncClient):
    """Search endpoint must return 401 when no token is provided."""
    response = await client.get(SEARCH_URL, params={"q": "ali"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Minimum length validation
# ---------------------------------------------------------------------------

async def test_search_query_too_short_rejected(client: AsyncClient, headers: dict[str, str]):
    """Query with fewer than 3 characters must be rejected with 422."""
    for short_q in ("", "a", "al"):
        response = await client.get(SEARCH_URL, params={"q": short_q}, headers=headers)
        assert response.status_code == 422, f"Expected 422 for q={short_q!r}, got {response.status_code}"


# ---------------------------------------------------------------------------
# Basic substring match
# ---------------------------------------------------------------------------

async def test_search_finds_matching_users(client: AsyncClient, headers: dict[str, str]):
    """Substring 'ali' should match 'alice_wonder' and 'davealice'."""
    response = await client.get(SEARCH_URL, params={"q": "ali"}, headers=headers)
    assert response.status_code == 200, response.text
    usernames = [u["username"] for u in response.json()]
    assert "alice_wonder" in usernames
    assert "davealice" in usernames


async def test_search_no_results(client: AsyncClient, headers: dict[str, str]):
    """Substring that matches nothing should return an empty list."""
    response = await client.get(SEARCH_URL, params={"q": "zzz"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == []


# ---------------------------------------------------------------------------
# Case-insensitive matching
# ---------------------------------------------------------------------------

async def test_search_case_insensitive(client: AsyncClient, headers: dict[str, str]):
    """Search should be case-insensitive: 'ALI' must match 'alice_wonder'."""
    response = await client.get(SEARCH_URL, params={"q": "ALI"}, headers=headers)
    assert response.status_code == 200, response.text
    usernames = [u["username"] for u in response.json()]
    assert "alice_wonder" in usernames


# ---------------------------------------------------------------------------
# Result count cap
# ---------------------------------------------------------------------------

async def test_search_limit_4(client: AsyncClient, headers: dict[str, str]):
    """Search must return at most 4 results even when more matches exist."""
    await register_all(client, [
        {"email": f"lt{i}@example.com", "password": "LimitPass1!", "username": f"limit_test_{i}"}
        for i in range(5)
    ])

    response = await client.get(SEARCH_URL, params={"q": "limit_test"}, headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 4


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

async def test_search_response_schema(client: AsyncClient, headers: dict[str, str]):
    """Each result must have 'id' and 'username'; must NOT expose email or hashed_password."""
    response = await client.get(SEARCH_URL, params={"q": "ali"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()
    for item in response.json():
        assert "id" in item
        assert "username" in item
        assert "email" not in item
        assert "hashed_password" not in item
