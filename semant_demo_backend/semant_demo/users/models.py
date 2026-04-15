from sqlalchemy import Column, String
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from semant_demo.schemas import TasksBase


class User(SQLAlchemyBaseUserTableUUID, TasksBase):
    __tablename__ = "user"

    username = Column(String(100), unique=True, nullable=True, index=True)
    name = Column(String(200), nullable=True)
    institution = Column(String(300), nullable=True)
