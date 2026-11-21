"""The cheaper test-process defaults in conftest (#848) stay in effect, and stay scoped.

They patch library behavior, so a dependency upgrade could silently restore the slow
defaults or a marker could stop opting a durability test out.
"""
import sqlite3

import pytest
from fastapi_users.password import PasswordHelper
from sqlalchemy import create_engine, text


def _synchronous(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    try:
        with engine.connect() as conn:
            return conn.execute(text("PRAGMA synchronous")).scalar_one()
    finally:
        engine.dispose()


def _sqlite_default(tmp_path):
    with sqlite3.connect(tmp_path / "plain.sqlite") as conn:
        value = conn.execute("PRAGMA synchronous").fetchone()[0]
    conn.close()
    return value


def test_ordinary_test_databases_do_not_wait_for_the_disk(tmp_path):
    assert _synchronous(tmp_path) == 0  # OFF


@pytest.mark.sqlite_durable
def test_durable_tests_keep_sqlite_synchronization(tmp_path):
    assert _sqlite_default(tmp_path) != 0
    assert _synchronous(tmp_path) == _sqlite_default(tmp_path)


def test_passwords_are_hashed_with_the_minimal_argon2_work_factor():
    assert PasswordHelper().hash("secret").startswith("$argon2id$v=19$m=8,t=1,p=1$")
