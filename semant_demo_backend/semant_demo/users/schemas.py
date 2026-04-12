import uuid
from typing import Optional
from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    username: Optional[str] = None
    name: Optional[str] = None
    institution: Optional[str] = None


class UserCreate(schemas.BaseUserCreate):
    username: Optional[str] = None
    name: Optional[str] = None
    institution: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    username: Optional[str] = None
    name: Optional[str] = None
    institution: Optional[str] = None
