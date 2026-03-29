"""MERGE statement tests for sqlalchemy-cubrid dialect (0.4.2).

CUBRID MERGE syntax:
    MERGE INTO target USING source ON (condition)
    WHEN MATCHED THEN UPDATE SET ...
    WHEN NOT MATCHED THEN INSERT (...) VALUES (...)

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
    String,
)
from sqlalchemy_cubrid.merge import Merge

CUBRID_URL = "cubrid://dba:@localhost:33000/testdb"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def tables(engine):
    metadata = MetaData()
    target = Table(
        "t_merge_target",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
        Column("score", Integer),
    )
    source = Table(
        "t_merge_source",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
        Column("score", Integer),
    )
    metadata.create_all(engine)
    yield target, source
    metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def seed_data(engine, tables):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM t_merge_target"))
        conn.execute(text("DELETE FROM t_merge_source"))
        # Target: existing records
        conn.execute(text(
            "INSERT INTO t_merge_target VALUES "
            "(1, 'Alice', 80), (2, 'Bob', 70)"
        ))
        # Source: new + updated records
        conn.execute(text(
            "INSERT INTO t_merge_source VALUES "
            "(2, 'Bob Updated', 90), (3, 'Charlie', 85)"
        ))
        conn.commit()
    yield


class TestMergeRaw:
    """Test MERGE with raw SQL to verify baseline behavior."""

    def test_merge_update_and_insert(self, engine, tables):
        """MERGE updates matched rows and inserts unmatched rows."""
        with engine.connect() as conn:
            conn.execute(text(
                "MERGE INTO t_merge_target t "
                "USING t_merge_source s "
                "ON (t.id = s.id) "
                "WHEN MATCHED THEN UPDATE SET t.name = s.name, t.score = s.score "
                "WHEN NOT MATCHED THEN INSERT (id, name, score) "
                "VALUES (s.id, s.name, s.score)"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT id, name, score FROM t_merge_target ORDER BY id"
            ))
            rows = result.fetchall()
            assert len(rows) == 3
            # id=1 unchanged
            assert rows[0] == (1, "Alice", 80)
            # id=2 updated
            assert rows[1] == (2, "Bob Updated", 90)
            # id=3 inserted
            assert rows[2] == (3, "Charlie", 85)

    def test_merge_update_only(self, engine, tables):
        """MERGE with only WHEN MATCHED (no insert)."""
        with engine.connect() as conn:
            conn.execute(text(
                "MERGE INTO t_merge_target t "
                "USING t_merge_source s "
                "ON (t.id = s.id) "
                "WHEN MATCHED THEN UPDATE SET t.score = s.score"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT id, score FROM t_merge_target ORDER BY id"
            ))
            rows = result.fetchall()
            assert len(rows) == 2  # no new rows inserted
            assert rows[1] == (2, 90)  # Bob updated

    def test_merge_insert_only(self, engine, tables):
        """MERGE with only WHEN NOT MATCHED (no update)."""
        with engine.connect() as conn:
            conn.execute(text(
                "MERGE INTO t_merge_target t "
                "USING t_merge_source s "
                "ON (t.id = s.id) "
                "WHEN NOT MATCHED THEN INSERT (id, name, score) "
                "VALUES (s.id, s.name, s.score)"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT COUNT(*) FROM t_merge_target"
            ))
            assert result.scalar() == 3  # original 2 + 1 new

    def test_merge_with_subquery_source(self, engine, tables):
        """MERGE USING subquery as source."""
        with engine.connect() as conn:
            conn.execute(text(
                "MERGE INTO t_merge_target t "
                "USING (SELECT * FROM t_merge_source WHERE score > 80) s "
                "ON (t.id = s.id) "
                "WHEN MATCHED THEN UPDATE SET t.score = s.score "
                "WHEN NOT MATCHED THEN INSERT (id, name, score) "
                "VALUES (s.id, s.name, s.score)"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT id, name, score FROM t_merge_target ORDER BY id"
            ))
            rows = result.fetchall()
            assert len(rows) == 3
            assert rows[1] == (2, "Bob", 90)     # score > 80, updated
            assert rows[2] == (3, "Charlie", 85)  # inserted


class TestMergeSQLAlchemy:
    """Test MERGE via SQLAlchemy Merge construct."""

    def test_merge_update_and_insert(self, engine, tables):
        """Merge construct with both update and insert."""
        target, source = tables
        stmt = (
            Merge(target)
            .using(source)
            .on(target.c.id == source.c.id)
            .when_matched_then_update({
                target.c.name: source.c.name,
                target.c.score: source.c.score,
            })
            .when_not_matched_then_insert({
                target.c.id: source.c.id,
                target.c.name: source.c.name,
                target.c.score: source.c.score,
            })
        )

        with engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

            result = conn.execute(text(
                "SELECT id, name, score FROM t_merge_target ORDER BY id"
            ))
            rows = result.fetchall()
            assert len(rows) == 3
            assert rows[1] == (2, "Bob Updated", 90)
            assert rows[2] == (3, "Charlie", 85)

    def test_merge_update_only(self, engine, tables):
        """Merge construct with only update clause."""
        target, source = tables
        stmt = (
            Merge(target)
            .using(source)
            .on(target.c.id == source.c.id)
            .when_matched_then_update({
                target.c.score: source.c.score,
            })
        )

        with engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

            result = conn.execute(text(
                "SELECT COUNT(*) FROM t_merge_target"
            ))
            assert result.scalar() == 2

    def test_merge_insert_only(self, engine, tables):
        """Merge construct with only insert clause."""
        target, source = tables
        stmt = (
            Merge(target)
            .using(source)
            .on(target.c.id == source.c.id)
            .when_not_matched_then_insert({
                target.c.id: source.c.id,
                target.c.name: source.c.name,
                target.c.score: source.c.score,
            })
        )

        with engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

            result = conn.execute(text(
                "SELECT COUNT(*) FROM t_merge_target"
            ))
            assert result.scalar() == 3

    def test_merge_compile_output(self, engine, tables):
        """Verify compiled SQL contains MERGE keywords."""
        target, source = tables
        stmt = (
            Merge(target)
            .using(source)
            .on(target.c.id == source.c.id)
            .when_matched_then_update({target.c.name: source.c.name})
            .when_not_matched_then_insert({
                target.c.id: source.c.id,
                target.c.name: source.c.name,
            })
        )
        compiled = stmt.compile(engine)
        sql_str = str(compiled).upper()
        assert "MERGE INTO" in sql_str
        assert "USING" in sql_str
        assert "ON" in sql_str
        assert "WHEN MATCHED THEN UPDATE" in sql_str
        assert "WHEN NOT MATCHED THEN INSERT" in sql_str
