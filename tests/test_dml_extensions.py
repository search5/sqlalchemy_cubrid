"""DML extension tests for 0.6.5 features.

Tests INSERT ... ON DUPLICATE KEY UPDATE, REPLACE INTO, FOR UPDATE.

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import (
    create_engine, text, MetaData, Table, Column, Integer, String, select,
)

from sqlalchemy_cubrid.dml import insert, replace

import os
CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def meta(engine):
    m = MetaData()
    yield m


@pytest.fixture(scope="module")
def upsert_table(engine, meta):
    """Create a table with a UNIQUE constraint for upsert tests."""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_upsert"))
        conn.execute(text(
            "CREATE TABLE test_upsert ("
            "  id INTEGER PRIMARY KEY,"
            "  name VARCHAR(50),"
            "  score INTEGER DEFAULT 0"
            ")"
        ))
        conn.commit()
    tbl = Table("test_upsert", meta, autoload_with=engine)
    yield tbl
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_upsert"))
        conn.commit()


@pytest.fixture(scope="module")
def for_update_table(engine, meta):
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_forupdate"))
        conn.execute(text(
            "CREATE TABLE test_forupdate ("
            "  id INTEGER AUTO_INCREMENT PRIMARY KEY,"
            "  name VARCHAR(50)"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO test_forupdate (name) VALUES ('alice'), ('bob')"
        ))
        conn.commit()
    tbl = Table("test_forupdate", meta, autoload_with=engine)
    yield tbl
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_forupdate"))
        conn.commit()


class TestOnDuplicateKeyUpdate:
    def test_insert_new_row(self, engine, upsert_table):
        tbl = upsert_table
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM test_upsert"))
            stmt = insert(tbl).values(id=1, name="alice", score=10)
            stmt = stmt.on_duplicate_key_update(name="alice_updated", score=99)
            conn.execute(stmt)
            conn.commit()

            result = conn.execute(
                select(tbl).where(tbl.c.id == 1)
            ).fetchone()
            assert result.name == "alice"
            assert result.score == 10

    def test_update_on_duplicate(self, engine, upsert_table):
        tbl = upsert_table
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM test_upsert"))
            conn.execute(text(
                "INSERT INTO test_upsert VALUES (1, 'alice', 10)"
            ))
            conn.commit()

            stmt = insert(tbl).values(id=1, name="alice_new", score=20)
            stmt = stmt.on_duplicate_key_update(
                name="alice_updated", score=99
            )
            conn.execute(stmt)
            conn.commit()

            result = conn.execute(
                select(tbl).where(tbl.c.id == 1)
            ).fetchone()
            assert result.name == "alice_updated"
            assert result.score == 99

    def test_on_duplicate_with_expression(self, engine, upsert_table):
        """ON DUPLICATE KEY UPDATE with SQL expression.

        Note: CUBRID does not support VALUES() function in ON DUPLICATE KEY
        UPDATE (unlike MySQL). Use explicit values or expressions instead.
        """
        tbl = upsert_table
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM test_upsert"))
            conn.execute(text(
                "INSERT INTO test_upsert VALUES (1, 'alice', 10)"
            ))
            conn.commit()

            stmt = insert(tbl).values(id=1, name="bob", score=50)
            stmt = stmt.on_duplicate_key_update(
                name="bob",
                score=tbl.c.score + 100,
            )
            conn.execute(stmt)
            conn.commit()

            result = conn.execute(
                select(tbl).where(tbl.c.id == 1)
            ).fetchone()
            assert result.name == "bob"
            assert result.score == 110  # 10 + 100

    def test_on_duplicate_with_dict(self, engine, upsert_table):
        tbl = upsert_table
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM test_upsert"))
            conn.execute(text(
                "INSERT INTO test_upsert VALUES (1, 'alice', 10)"
            ))
            conn.commit()

            stmt = insert(tbl).values(id=1, name="bob", score=20)
            stmt = stmt.on_duplicate_key_update({"name": "dict_updated"})
            conn.execute(stmt)
            conn.commit()

            result = conn.execute(
                select(tbl).where(tbl.c.id == 1)
            ).fetchone()
            assert result.name == "dict_updated"

    def test_on_duplicate_compile_output(self, engine, upsert_table):
        """Verify the compiled SQL structure."""
        tbl = upsert_table
        stmt = insert(tbl).values(id=1, name="test", score=10)
        stmt = stmt.on_duplicate_key_update(name="updated")
        compiled = stmt.compile(dialect=engine.dialect)
        sql = str(compiled)
        assert "ON DUPLICATE KEY UPDATE" in sql
        assert "\"name\"" in sql or "name" in sql


class TestReplace:
    def test_replace_insert_new(self, engine, upsert_table):
        tbl = upsert_table
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM test_upsert"))
            stmt = replace(tbl).values(id=1, name="alice", score=10)
            conn.execute(stmt)
            conn.commit()

            result = conn.execute(
                select(tbl).where(tbl.c.id == 1)
            ).fetchone()
            assert result.name == "alice"
            assert result.score == 10

    def test_replace_overwrites_existing(self, engine, upsert_table):
        tbl = upsert_table
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM test_upsert"))
            conn.execute(text(
                "INSERT INTO test_upsert VALUES (1, 'alice', 10)"
            ))
            conn.commit()

            stmt = replace(tbl).values(id=1, name="bob", score=99)
            conn.execute(stmt)
            conn.commit()

            result = conn.execute(
                select(tbl).where(tbl.c.id == 1)
            ).fetchone()
            assert result.name == "bob"
            assert result.score == 99

    def test_replace_compile_output(self, engine, upsert_table):
        tbl = upsert_table
        stmt = replace(tbl).values(id=1, name="test", score=10)
        compiled = stmt.compile(dialect=engine.dialect)
        sql = str(compiled)
        assert sql.startswith("REPLACE")
        assert "INSERT" not in sql


class TestForUpdate:
    def test_for_update_basic(self, engine, for_update_table):
        tbl = for_update_table
        with engine.connect() as conn:
            stmt = select(tbl).where(tbl.c.id == 1).with_for_update()
            result = conn.execute(stmt).fetchone()
            assert result.name == "alice"
            conn.rollback()

    def test_for_update_of(self, engine, for_update_table):
        tbl = for_update_table
        with engine.connect() as conn:
            stmt = select(tbl).with_for_update(of=tbl)
            result = conn.execute(stmt).fetchall()
            assert len(result) == 2
            conn.rollback()

    def test_for_update_compile_output(self, engine, for_update_table):
        tbl = for_update_table
        stmt = select(tbl).with_for_update()
        compiled = stmt.compile(dialect=engine.dialect)
        sql = str(compiled)
        assert "FOR UPDATE" in sql

    def test_for_update_of_compile_output(self, engine, for_update_table):
        tbl = for_update_table
        stmt = select(tbl).with_for_update(of=tbl)
        compiled = stmt.compile(dialect=engine.dialect)
        sql = str(compiled)
        assert "FOR UPDATE OF" in sql

    def test_for_update_read_ignored(self, engine, for_update_table):
        """FOR SHARE (read=True) is not supported, should be empty."""
        tbl = for_update_table
        stmt = select(tbl).with_for_update(read=True)
        compiled = stmt.compile(dialect=engine.dialect)
        sql = str(compiled)
        assert "FOR UPDATE" not in sql
        assert "LOCK IN SHARE" not in sql
