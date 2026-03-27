"""Connection tests for sqlalchemy-cubrid dialect.

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import create_engine, text

CUBRID_URL = "cubrid://dba:@localhost:33000/testdb"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


class TestConnection:
    def test_connect_and_disconnect(self, engine):
        """Engine can connect to CUBRID and close cleanly."""
        with engine.connect() as conn:
            assert conn is not None

    def test_execute_raw_sql(self, engine):
        """Can execute a simple raw SQL query."""
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            assert row[0] == 1

    def test_server_version(self, engine):
        """Server version info is a tuple of integers."""
        with engine.connect() as conn:
            version = engine.dialect.server_version_info
            assert isinstance(version, tuple)
            assert all(isinstance(v, int) for v in version)
            assert version[0] >= 10
