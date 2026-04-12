import uuid

from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy

from semant_demo.users.models import User
from semant_demo.users.manager import get_user_manager
from semant_demo.users.schemas import UserRead, UserCreate, UserUpdate
from semant_demo.config import config

# JWT Bearer transport – token returned as JSON body on login
bearer_transport = BearerTransport(tokenUrl="/api/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    # 7-day lifetime; rotate secret via JWT_SECRET env var
    return JWTStrategy(secret=config.JWT_SECRET, lifetime_seconds=60 * 60 * 24 * 7)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

# Dependency shortcuts
current_active_user = fastapi_users.current_user(active=True)
current_active_optional_user = fastapi_users.current_user(active=True, optional=True)

# Routers (mounted in main.py)
auth_router = fastapi_users.get_auth_router(auth_backend)
register_router = fastapi_users.get_register_router(UserRead, UserCreate)
users_router = fastapi_users.get_users_router(UserRead, UserUpdate)
