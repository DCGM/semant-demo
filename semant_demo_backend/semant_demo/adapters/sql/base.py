"""Declarative base of the application's SQL tables (database at ``SQL_DB_URL``)."""
from sqlalchemy.orm import declarative_base

Base = declarative_base()
