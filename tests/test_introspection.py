"""Introspection tests for sqlalchemy-cubrid dialect (0.1.1).

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import create_engine, inspect, text

import os
CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def setup_tables(engine):
    """Create test tables before each test, drop after."""
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS t_alpha (id INT PRIMARY KEY, name VARCHAR(100))"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS t_beta (id INT PRIMARY KEY, amount DOUBLE)"))
        conn.commit()
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_alpha"))
        conn.execute(text("DROP TABLE IF EXISTS t_beta"))
        conn.commit()


class TestHasTable:
    def test_existing_table(self, engine):
        insp = inspect(engine)
        assert insp.has_table("t_alpha") is True

    def test_nonexistent_table(self, engine):
        insp = inspect(engine)
        assert insp.has_table("no_such_table") is False

    def test_case_insensitive(self, engine):
        """CUBRID table names are case-insensitive."""
        insp = inspect(engine)
        assert insp.has_table("T_ALPHA") is True


class TestGetTableNames:
    def test_returns_list(self, engine):
        insp = inspect(engine)
        tables = insp.get_table_names()
        assert isinstance(tables, list)

    def test_contains_created_tables(self, engine):
        insp = inspect(engine)
        tables = insp.get_table_names()
        assert "t_alpha" in tables
        assert "t_beta" in tables

    def test_excludes_system_tables(self, engine):
        insp = inspect(engine)
        tables = insp.get_table_names()
        assert "db_class" not in tables
