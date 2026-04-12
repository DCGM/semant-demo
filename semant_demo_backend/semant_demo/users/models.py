from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from semant_demo.schemas import TasksBase


class User(SQLAlchemyBaseUserTableUUID, TasksBase):
    __tablename__ = "user"
