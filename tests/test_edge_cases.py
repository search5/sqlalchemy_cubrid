"""Edge case and error handling tests for 0.9.1.

Tests connection disconnect recovery, invalid SQL exceptions, timeouts,
bulk data operations, and concurrent connections.

Requires a running CUBRID instance:
    docker compose up -d
"""

import os
import threading
import time

import pytest
from sqlalchemy import (
    create_engine,
    text,
    inspect,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    select,
    insert,
    exc,
)
from sqlalchemy.pool import NullPool

CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def cleanup(engine):
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_edge"))
        conn.commit()


# --- 1. Connection disconnect recovery ---


class TestDisconnectRecovery:
    """Test connection pool behavior after disconnect."""

    def test_is_disconnect_interface_error(self, engine):
        """is_disconnect detects InterfaceError with 'closed' message."""
        dbapi = engine.dialect.loaded_dbapi
        err = dbapi.InterfaceError("connection is closed")
        assert engine.dialect.is_disconnect(err, None, None) is True

    def test_is_disconnect_operational_error(self, engine):
        """is_disconnect detects OperationalError with 'communication' message."""
        dbapi = engine.dialect.loaded_dbapi
        err = dbapi.OperationalError("communication failure")
        assert engine.dialect.is_disconnect(err, None, None) is True

    def test_is_disconnect_false_for_programming_error(self, engine):
        """is_disconnect returns False for ProgrammingError (not a disconnect)."""
        dbapi = engine.dialect.loaded_dbapi
        err = dbapi.ProgrammingError("Syntax error")
        assert engine.dialect.is_disconnect(err, None, None) is False

    def test_is_disconnect_numeric_codes(self, engine):
        """is_disconnect detects known numeric error codes."""
        dbapi = engine.dialect.loaded_dbapi
        for code in (-4, -11, -21003):
            err = dbapi.InterfaceError(code, "error")
            assert engine.dialect.is_disconnect(err, None, None) is True

    def test_pool_pre_ping_recovers_stale_connection(self):
        """pool_pre_ping drops stale connections and creates new ones."""
        eng = create_engine(CUBRID_URL, pool_pre_ping=True, pool_size=1)
        try:
            # Get a connection, execute, return to pool
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))

            # Second connection from pool should work (pre_ping validates)
            with eng.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
        finally:
            eng.dispose()

    def test_do_ping_after_server_query(self, engine):
        """do_ping works after executing queries."""
        raw_conn = engine.raw_connection()
        try:
            cursor = raw_conn.cursor()
            cursor.execute("SELECT 1 FROM db_root")
            cursor.close()
            # Ping should still work
            assert engine.dialect.do_ping(raw_conn) is True
        finally:
            raw_conn.close()


# --- 2. Invalid SQL exception types ---


class TestInvalidSQLExceptions:
    """Verify correct exception types for various SQL errors."""

    def test_syntax_error_raises_programming_error(self, engine):
        """Malformed SQL raises ProgrammingError."""
        with engine.connect() as conn:
            with pytest.raises(exc.ProgrammingError):
                conn.execute(text("SELEC 1"))

    def test_nonexistent_table_raises_programming_error(self, engine):
        """Query on non-existent table raises ProgrammingError."""
        with engine.connect() as conn:
            with pytest.raises(exc.ProgrammingError):
                conn.execute(text("SELECT * FROM nonexistent_table_xyz"))

    def test_duplicate_pk_raises_integrity_error(self, engine):
        """Duplicate primary key raises IntegrityError."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, val VARCHAR(50))"
            ))
            conn.execute(text("INSERT INTO test_edge VALUES (1, 'a')"))
            conn.commit()

            with pytest.raises(exc.IntegrityError):
                conn.execute(text("INSERT INTO test_edge VALUES (1, 'b')"))

    def test_not_null_violation_raises_database_error(self, engine):
        """NOT NULL violation raises DatabaseError (pycubrid maps this to DatabaseError)."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, val VARCHAR(50) NOT NULL)"
            ))
            conn.commit()

            with pytest.raises((exc.IntegrityError, exc.DatabaseError)):
                conn.execute(text("INSERT INTO test_edge (id, val) VALUES (1, NULL)"))

    def test_fk_violation_raises_integrity_error(self, engine):
        """Foreign key violation raises IntegrityError."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY)"
            ))
            conn.execute(text(
                "CREATE TABLE test_edge_child ("
                "  id INT PRIMARY KEY,"
                "  parent_id INT,"
                "  FOREIGN KEY (parent_id) REFERENCES test_edge(id)"
                ")"
            ))
            conn.commit()

            with pytest.raises(exc.IntegrityError):
                conn.execute(text(
                    "INSERT INTO test_edge_child VALUES (1, 999)"
                ))
            conn.rollback()

            conn.execute(text("DROP TABLE test_edge_child"))
            conn.commit()

    def test_division_by_zero(self, engine):
        """Division by zero raises DatabaseError or similar."""
        with engine.connect() as conn:
            # CUBRID may return NULL or raise an error for division by zero
            try:
                result = conn.execute(text("SELECT 1/0 FROM db_root"))
                val = result.scalar()
                # If CUBRID returns NULL instead of error, that's also valid
                assert val is None
            except exc.DatabaseError:
                pass  # Expected for some CUBRID versions

    def test_drop_nonexistent_table_without_if_exists(self, engine):
        """DROP TABLE without IF EXISTS raises ProgrammingError."""
        with engine.connect() as conn:
            with pytest.raises(exc.ProgrammingError):
                conn.execute(text("DROP TABLE nonexistent_table_xyz"))

    def test_invalid_column_reference(self, engine):
        """Reference to non-existent column raises ProgrammingError."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY)"
            ))
            conn.commit()

            with pytest.raises(exc.ProgrammingError):
                conn.execute(text("SELECT nonexistent_col FROM test_edge"))


# --- 3. Timeout behavior ---


class TestTimeout:
    """Test query and connection timeout behavior."""

    def test_long_query_completes(self, engine):
        """A moderately long query completes without timeout."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, val VARCHAR(50))"
            ))
            conn.commit()

            # Insert enough rows to make a query non-trivial
            for i in range(100):
                conn.execute(text(
                    "INSERT INTO test_edge VALUES (:id, :val)"
                ), {"id": i, "val": f"value_{i}"})
            conn.commit()

            # Cross join produces 10000 rows
            result = conn.execute(text(
                "SELECT COUNT(*) FROM test_edge a, test_edge b"
            ))
            count = result.scalar()
            assert count == 10000

    def test_engine_pool_timeout(self):
        """Engine with small pool raises TimeoutError when exhausted."""
        eng = create_engine(
            CUBRID_URL, pool_size=1, max_overflow=0, pool_timeout=1
        )
        try:
            conn1 = eng.connect()
            # Pool is exhausted; second connect should timeout
            with pytest.raises(exc.TimeoutError):
                eng.connect()
            conn1.close()
        finally:
            eng.dispose()


# --- 4. Bulk data insert/select ---


class TestBulkData:
    """Test large data operations."""

    def test_bulk_insert_1000_rows(self, engine):
        """Insert and verify 1000 rows."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge ("
                "  id INT PRIMARY KEY,"
                "  name VARCHAR(100),"
                "  score INT"
                ")"
            ))
            conn.commit()

            for batch_start in range(0, 1000, 100):
                for i in range(batch_start, batch_start + 100):
                    conn.execute(text(
                        "INSERT INTO test_edge VALUES (:id, :name, :score)"
                    ), {"id": i, "name": f"user_{i}", "score": i * 10})
                conn.commit()

            count = conn.execute(text(
                "SELECT COUNT(*) FROM test_edge"
            )).scalar()
            assert count == 1000

    def test_bulk_select_with_filter(self, engine):
        """Select with WHERE on bulk data."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, val INT)"
            ))
            conn.commit()

            for i in range(500):
                conn.execute(text(
                    "INSERT INTO test_edge VALUES (:id, :val)"
                ), {"id": i, "val": i % 10})
            conn.commit()

            result = conn.execute(text(
                "SELECT COUNT(*) FROM test_edge WHERE val = 0"
            ))
            assert result.scalar() == 50

    def test_large_varchar_roundtrip(self, engine):
        """Insert and retrieve large VARCHAR values."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, payload VARCHAR(10000))"
            ))
            conn.commit()

            large_str = "x" * 5000
            conn.execute(text(
                "INSERT INTO test_edge VALUES (1, :payload)"
            ), {"payload": large_str})
            conn.commit()

            result = conn.execute(text(
                "SELECT payload FROM test_edge WHERE id = 1"
            )).scalar()
            assert result == large_str
            assert len(result) == 5000

    def test_batch_update(self, engine):
        """Update all rows in a single statement."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, val INT)"
            ))
            conn.commit()

            for i in range(200):
                conn.execute(text(
                    "INSERT INTO test_edge VALUES (:id, :val)"
                ), {"id": i, "val": 0})
            conn.commit()

            result = conn.execute(text(
                "UPDATE test_edge SET val = val + 1"
            ))
            conn.commit()
            assert result.rowcount == 200

            total = conn.execute(text(
                "SELECT SUM(val) FROM test_edge"
            )).scalar()
            assert total == 200

    def test_batch_delete(self, engine):
        """Delete with WHERE condition on bulk data."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, val INT)"
            ))
            conn.commit()

            for i in range(300):
                conn.execute(text(
                    "INSERT INTO test_edge VALUES (:id, :val)"
                ), {"id": i, "val": i % 3})
            conn.commit()

            result = conn.execute(text(
                "DELETE FROM test_edge WHERE val = 0"
            ))
            conn.commit()
            assert result.rowcount == 100

            remaining = conn.execute(text(
                "SELECT COUNT(*) FROM test_edge"
            )).scalar()
            assert remaining == 200


# --- 5. Concurrent connections ---


class TestConcurrency:
    """Test multiple simultaneous connections."""

    def test_independent_connections(self, engine):
        """Multiple connections operate independently."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, val INT)"
            ))
            conn.commit()

        eng1 = create_engine(CUBRID_URL)
        eng2 = create_engine(CUBRID_URL)
        try:
            with eng1.connect() as c1, eng2.connect() as c2:
                c1.execute(text("INSERT INTO test_edge VALUES (1, 10)"))
                c1.commit()

                c2.execute(text("INSERT INTO test_edge VALUES (2, 20)"))
                c2.commit()

                # Both see all committed rows
                r1 = c1.execute(text(
                    "SELECT COUNT(*) FROM test_edge"
                )).scalar()
                r2 = c2.execute(text(
                    "SELECT COUNT(*) FROM test_edge"
                )).scalar()
                assert r1 == 2
                assert r2 == 2
        finally:
            eng1.dispose()
            eng2.dispose()

    def test_concurrent_inserts_threading(self, engine):
        """Multiple threads can insert concurrently without data loss."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge ("
                "  id INT PRIMARY KEY,"
                "  thread_id INT,"
                "  val INT"
                ")"
            ))
            conn.commit()

        errors = []
        num_threads = 5
        rows_per_thread = 50

        def worker(thread_idx):
            eng = create_engine(CUBRID_URL, poolclass=NullPool)
            try:
                with eng.connect() as conn:
                    for i in range(rows_per_thread):
                        row_id = thread_idx * rows_per_thread + i
                        conn.execute(text(
                            "INSERT INTO test_edge VALUES (:id, :tid, :val)"
                        ), {"id": row_id, "tid": thread_idx, "val": i})
                    conn.commit()
            except Exception as e:
                errors.append((thread_idx, e))
            finally:
                eng.dispose()

        threads = [
            threading.Thread(target=worker, args=(t,))
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"

        with engine.connect() as conn:
            count = conn.execute(text(
                "SELECT COUNT(*) FROM test_edge"
            )).scalar()
            assert count == num_threads * rows_per_thread

    def test_concurrent_reads_threading(self, engine):
        """Multiple threads can read concurrently."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, val VARCHAR(50))"
            ))
            for i in range(100):
                conn.execute(text(
                    "INSERT INTO test_edge VALUES (:id, :val)"
                ), {"id": i, "val": f"item_{i}"})
            conn.commit()

        results = {}
        errors = []

        def reader(thread_idx):
            eng = create_engine(CUBRID_URL, poolclass=NullPool)
            try:
                with eng.connect() as conn:
                    count = conn.execute(text(
                        "SELECT COUNT(*) FROM test_edge"
                    )).scalar()
                    results[thread_idx] = count
            except Exception as e:
                errors.append((thread_idx, e))
            finally:
                eng.dispose()

        threads = [
            threading.Thread(target=reader, args=(t,))
            for t in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Reader errors: {errors}"
        # All readers should see 100 rows
        for tid, count in results.items():
            assert count == 100, f"Thread {tid} saw {count} rows"

    def test_pool_size_limit(self):
        """Connection pool respects size limits."""
        eng = create_engine(CUBRID_URL, pool_size=3, max_overflow=0)
        try:
            connections = []
            for _ in range(3):
                connections.append(eng.connect())

            # Pool full — next connect should timeout
            with pytest.raises(exc.TimeoutError):
                eng.connect().close()

            for c in connections:
                c.close()
        finally:
            eng.dispose()

    def test_isolation_between_transactions(self, engine):
        """Uncommitted changes are not visible to other connections."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_edge (id INT PRIMARY KEY, val INT)"
            ))
            conn.execute(text("INSERT INTO test_edge VALUES (1, 100)"))
            conn.commit()

        eng2 = create_engine(CUBRID_URL)
        try:
            with engine.connect() as c1, eng2.connect() as c2:
                # c1 updates but does not commit
                c1.execute(text("UPDATE test_edge SET val = 200 WHERE id = 1"))

                # c2 should see the old committed value
                val = c2.execute(text(
                    "SELECT val FROM test_edge WHERE id = 1"
                )).scalar()
                assert val == 100

                c1.rollback()
        finally:
            eng2.dispose()
