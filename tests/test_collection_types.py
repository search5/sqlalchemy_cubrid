"""Collection type tests for sqlalchemy-cubrid dialect (0.4.0).

SET, MULTISET, LIST/SEQUENCE types.

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import (
    create_engine,
    text,
    MetaData,
    Table,
    Column,
    Integer,
)
from sqlalchemy_cubrid.types import CubridSet, CubridMultiset, CubridList

CUBRID_URL = "cubrid://dba:@localhost:33000/testdb"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def cleanup(engine):
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_collection"))
        conn.execute(text("DROP TABLE IF EXISTS t_sa_collection"))
        conn.commit()


class TestCollectionDDL:
    def test_create_table_with_set(self, engine):
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_collection ("
                "  id INT PRIMARY KEY,"
                "  tags SET VARCHAR(50)"
                ")"
            ))
            conn.commit()
            from sqlalchemy import inspect
            assert inspect(engine).has_table("t_collection")

    def test_create_table_with_multiset(self, engine):
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_collection ("
                "  id INT PRIMARY KEY,"
                "  scores MULTISET INT"
                ")"
            ))
            conn.commit()
            from sqlalchemy import inspect
            assert inspect(engine).has_table("t_collection")

    def test_create_table_with_list(self, engine):
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_collection ("
                "  id INT PRIMARY KEY,"
                "  items LIST VARCHAR(50)"
                ")"
            ))
            conn.commit()
            from sqlalchemy import inspect
            assert inspect(engine).has_table("t_collection")


class TestCollectionCRUD:
    def test_set_insert_and_select(self, engine):
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_collection ("
                "  id INT PRIMARY KEY,"
                "  tags SET VARCHAR(50)"
                ")"
            ))
            conn.execute(text(
                "INSERT INTO t_collection VALUES (1, {'python', 'cubrid', 'sql'})"
            ))
            conn.commit()

            result = conn.execute(text("SELECT tags FROM t_collection WHERE id = 1"))
            row = result.fetchone()
            # SET returns as Python set, elements are strings
            assert isinstance(row[0], set)
            assert "python" in row[0]
            assert "cubrid" in row[0]

    def test_set_deduplicates(self, engine):
        """SET automatically removes duplicate values."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_collection ("
                "  id INT PRIMARY KEY,"
                "  tags SET VARCHAR(50)"
                ")"
            ))
            conn.execute(text(
                "INSERT INTO t_collection VALUES (1, {'a', 'b', 'a', 'c', 'b'})"
            ))
            conn.commit()

            result = conn.execute(text("SELECT tags FROM t_collection WHERE id = 1"))
            row = result.fetchone()
            assert len(row[0]) == 3

    def test_multiset_allows_duplicates(self, engine):
        """MULTISET allows duplicate values."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_collection ("
                "  id INT PRIMARY KEY,"
                "  scores MULTISET INT"
                ")"
            ))
            conn.execute(text(
                "INSERT INTO t_collection VALUES (1, {10, 20, 10, 30})"
            ))
            conn.commit()

            result = conn.execute(text("SELECT scores FROM t_collection WHERE id = 1"))
            row = result.fetchone()
            assert isinstance(row[0], list)
            assert len(row[0]) == 4

    def test_list_preserves_order(self, engine):
        """LIST preserves insertion order."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_collection ("
                "  id INT PRIMARY KEY,"
                "  items LIST VARCHAR(50)"
                ")"
            ))
            conn.execute(text(
                "INSERT INTO t_collection VALUES (1, {'charlie', 'alice', 'bob'})"
            ))
            conn.commit()

            result = conn.execute(text("SELECT items FROM t_collection WHERE id = 1"))
            row = result.fetchone()
            assert isinstance(row[0], list)
            assert row[0] == ["charlie", "alice", "bob"]

    def test_set_update(self, engine):
        """Update SET column with set arithmetic."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_collection ("
                "  id INT PRIMARY KEY,"
                "  tags SET VARCHAR(50)"
                ")"
            ))
            conn.execute(text(
                "INSERT INTO t_collection VALUES (1, {'a', 'b'})"
            ))
            conn.execute(text(
                "UPDATE t_collection SET tags = tags + {'c'} WHERE id = 1"
            ))
            conn.commit()

            result = conn.execute(text("SELECT tags FROM t_collection WHERE id = 1"))
            row = result.fetchone()
            assert "c" in row[0]

    def test_collection_null(self, engine):
        """Collection columns accept NULL."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_collection ("
                "  id INT PRIMARY KEY,"
                "  tags SET VARCHAR(50)"
                ")"
            ))
            conn.execute(text(
                "INSERT INTO t_collection VALUES (1, NULL)"
            ))
            conn.commit()

            result = conn.execute(text("SELECT tags FROM t_collection WHERE id = 1"))
            row = result.fetchone()
            assert row[0] is None


class TestSACollectionTypes:
    """Test CUBRID collection types via SQLAlchemy custom types."""

    def test_set_type_ddl(self, engine):
        """CubridSet generates correct DDL."""
        metadata = MetaData()
        Table(
            "t_sa_collection",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("tags", CubridSet("VARCHAR(50)")),
        )
        metadata.create_all(engine)

        from sqlalchemy import inspect
        insp = inspect(engine)
        assert insp.has_table("t_sa_collection")

    def test_multiset_type_ddl(self, engine):
        """CubridMultiset generates correct DDL."""
        metadata = MetaData()
        Table(
            "t_sa_collection",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("scores", CubridMultiset("INT")),
        )
        metadata.create_all(engine)

        from sqlalchemy import inspect
        assert inspect(engine).has_table("t_sa_collection")

    def test_list_type_ddl(self, engine):
        """CubridList generates correct DDL."""
        metadata = MetaData()
        Table(
            "t_sa_collection",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("items", CubridList("VARCHAR(50)")),
        )
        metadata.create_all(engine)

        from sqlalchemy import inspect
        assert inspect(engine).has_table("t_sa_collection")
