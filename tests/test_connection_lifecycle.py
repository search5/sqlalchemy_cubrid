"""Connection lifecycle tests for 0.6.4 features.

Tests isolation levels, on_connect, do_ping, and reflection cache.

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import create_engine, inspect, text, MetaData, Table, Column, Integer, String

import os
CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def setup_table(engine):
    """Create a test table for reflection cache tests."""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_lifecycle"))
        conn.execute(text(
            "CREATE TABLE test_lifecycle ("
            "  id INTEGER AUTO_INCREMENT PRIMARY KEY,"
            "  name VARCHAR(50)"
            ")"
        ))
        conn.commit()
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_lifecycle"))
        conn.commit()


class TestIsolationLevel:
    def test_get_default_isolation_level(self, engine):
        raw_conn = engine.raw_connection()
        try:
            assert engine.dialect.get_default_isolation_level(raw_conn) == "READ COMMITTED"
        finally:
            raw_conn.close()

    def test_get_isolation_level_values(self, engine):
        raw_conn = engine.raw_connection()
        try:
            values = engine.dialect.get_isolation_level_values(raw_conn)
            assert "READ COMMITTED" in values
            assert "REPEATABLE READ" in values
            assert "SERIALIZABLE" in values
        finally:
            raw_conn.close()

    def test_get_isolation_level(self, engine):
        """Can read current isolation level from a live connection."""
        raw_conn = engine.raw_connection()
        try:
            level = engine.dialect.get_isolation_level(raw_conn)
            assert level in ("READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE")
        finally:
            raw_conn.close()

    def test_set_isolation_level(self, engine):
        """Can change isolation level on a raw connection."""
        raw_conn = engine.raw_connection()
        try:
            engine.dialect.set_isolation_level(raw_conn, "REPEATABLE READ")
            level = engine.dialect.get_isolation_level(raw_conn)
            assert level == "REPEATABLE READ"

            engine.dialect.set_isolation_level(raw_conn, "READ COMMITTED")
            level = engine.dialect.get_isolation_level(raw_conn)
            assert level == "READ COMMITTED"
        finally:
            raw_conn.close()

    def test_set_invalid_isolation_level(self, engine):
        raw_conn = engine.raw_connection()
        try:
            with pytest.raises(ValueError, match="Invalid isolation level"):
                engine.dialect.set_isolation_level(raw_conn, "READ UNCOMMITTED")
        finally:
            raw_conn.close()

    def test_engine_isolation_level_param(self):
        """Engine accepts isolation_level parameter."""
        eng = create_engine(CUBRID_URL, isolation_level="REPEATABLE READ")
        try:
            with eng.connect() as conn:
                # SA sets isolation level on the pooled connection;
                # verify via a fresh read of the dbapi connection state.
                dbapi_conn = conn.connection.dbapi_connection
                level = eng.dialect.get_isolation_level(dbapi_conn)
                assert level == "REPEATABLE READ"
        finally:
            eng.dispose()

    def test_connection_execution_options(self, engine):
        """Connection-level isolation level via execution_options."""
        with engine.connect().execution_options(
            isolation_level="SERIALIZABLE"
        ) as conn:
            raw = conn.connection.dbapi_connection
            level = engine.dialect.get_isolation_level(raw)
            assert level == "SERIALIZABLE"


class TestOnConnect:
    def test_autocommit_disabled(self, engine):
        """on_connect sets autocommit to False."""
        raw_conn = engine.raw_connection()
        try:
            assert raw_conn.autocommit is False
        finally:
            raw_conn.close()


class TestDoPing:
    def test_ping_success(self, engine):
        """do_ping returns True for a healthy connection."""
        raw_conn = engine.raw_connection()
        try:
            result = engine.dialect.do_ping(raw_conn)
            assert result is True
        finally:
            raw_conn.close()

    def test_pool_pre_ping(self):
        """pool_pre_ping uses do_ping to validate connections."""
        eng = create_engine(CUBRID_URL, pool_pre_ping=True)
        try:
            with eng.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
        finally:
            eng.dispose()


class TestReflectionCache:
    def test_inspector_caches_table_names(self, engine, setup_table):
        """Repeated get_table_names calls use cache."""
        insp = inspect(engine)
        names1 = insp.get_table_names()
        names2 = insp.get_table_names()
        assert "test_lifecycle" in names1
        assert names1 == names2

    def test_inspector_caches_columns(self, engine, setup_table):
        """Repeated get_columns calls use cache."""
        insp = inspect(engine)
        cols1 = insp.get_columns("test_lifecycle")
        cols2 = insp.get_columns("test_lifecycle")
        assert len(cols1) == 2
        assert cols1[0]["name"] == cols2[0]["name"]

    def test_inspector_caches_pk(self, engine, setup_table):
        insp = inspect(engine)
        pk1 = insp.get_pk_constraint("test_lifecycle")
        pk2 = insp.get_pk_constraint("test_lifecycle")
        assert pk1 == pk2
        assert "id" in pk1["constrained_columns"]

    def test_metadata_reflect(self, engine, setup_table):
        """Full metadata.reflect() works with cached introspection."""
        meta = MetaData()
        meta.reflect(bind=engine)
        assert "test_lifecycle" in meta.tables
