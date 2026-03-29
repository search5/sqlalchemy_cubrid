"""Click Counter function tests for sqlalchemy-cubrid dialect (0.4.1).

CUBRID INCR/DECR functions atomically increment/decrement integer columns
within a SELECT statement. Returns the value *before* the operation.

Restrictions:
- Only works on SMALLINT, INT, BIGINT columns
- Result set must contain exactly one row
- Independent of transaction COMMIT/ROLLBACK

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
    select,
)
from sqlalchemy_cubrid.functions import incr, decr

CUBRID_URL = "cubrid://dba:@localhost:33000/testdb"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def board_table(engine):
    metadata = MetaData()
    t = Table(
        "t_click_counter",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("title", String(100)),
        Column("read_count", Integer),
    )
    metadata.create_all(engine)
    yield t
    metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def seed_data(engine, board_table):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM t_click_counter"))
        conn.execute(text(
            "INSERT INTO t_click_counter VALUES (1, 'Post A', 0)"
        ))
        conn.execute(text(
            "INSERT INTO t_click_counter VALUES (2, 'Post B', 10)"
        ))
        conn.commit()
    yield


class TestClickCounterRaw:
    """Test INCR/DECR with raw SQL to verify baseline behavior."""

    def test_incr_raw(self, engine):
        """INCR returns old value and increments stored value by 1."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT INCR(read_count) FROM t_click_counter WHERE id = 1"
            ))
            old_val = result.scalar()
            assert old_val == 0

            # Verify the stored value was incremented
            result = conn.execute(text(
                "SELECT read_count FROM t_click_counter WHERE id = 1"
            ))
            assert result.scalar() == 1

    def test_decr_raw(self, engine):
        """DECR returns old value and decrements stored value by 1."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT DECR(read_count) FROM t_click_counter WHERE id = 2"
            ))
            old_val = result.scalar()
            assert old_val == 10

            result = conn.execute(text(
                "SELECT read_count FROM t_click_counter WHERE id = 2"
            ))
            assert result.scalar() == 9

    def test_incr_multiple_calls(self, engine):
        """Multiple INCR calls increment sequentially."""
        with engine.connect() as conn:
            conn.execute(text(
                "SELECT INCR(read_count) FROM t_click_counter WHERE id = 1"
            ))
            conn.execute(text(
                "SELECT INCR(read_count) FROM t_click_counter WHERE id = 1"
            ))
            conn.execute(text(
                "SELECT INCR(read_count) FROM t_click_counter WHERE id = 1"
            ))

            result = conn.execute(text(
                "SELECT read_count FROM t_click_counter WHERE id = 1"
            ))
            assert result.scalar() == 3


class TestClickCounterSQLAlchemy:
    """Test INCR/DECR via SQLAlchemy function constructs."""

    def test_incr_function(self, engine, board_table):
        """incr() generates INCR(column) SQL."""
        t = board_table
        stmt = select(incr(t.c.read_count)).where(t.c.id == 1)

        with engine.connect() as conn:
            old_val = conn.execute(stmt).scalar()
            assert old_val == 0

            # Verify increment
            result = conn.execute(select(t.c.read_count).where(t.c.id == 1))
            assert result.scalar() == 1

    def test_decr_function(self, engine, board_table):
        """decr() generates DECR(column) SQL."""
        t = board_table
        stmt = select(decr(t.c.read_count)).where(t.c.id == 2)

        with engine.connect() as conn:
            old_val = conn.execute(stmt).scalar()
            assert old_val == 10

            result = conn.execute(select(t.c.read_count).where(t.c.id == 2))
            assert result.scalar() == 9

    def test_incr_with_other_columns(self, engine, board_table):
        """incr() can be used alongside other columns in SELECT."""
        t = board_table
        stmt = select(t.c.title, incr(t.c.read_count)).where(t.c.id == 1)

        with engine.connect() as conn:
            row = conn.execute(stmt).fetchone()
            assert row[0] == "Post A"
            assert row[1] == 0  # returns pre-increment value

    def test_incr_compiles_correctly(self, engine, board_table):
        """Verify the compiled SQL string contains INCR()."""
        t = board_table
        stmt = select(incr(t.c.read_count)).where(t.c.id == 1)
        compiled = stmt.compile(engine)
        sql_str = str(compiled).upper()
        assert "INCR(" in sql_str

    def test_decr_compiles_correctly(self, engine, board_table):
        """Verify the compiled SQL string contains DECR()."""
        t = board_table
        stmt = select(decr(t.c.read_count)).where(t.c.id == 2)
        compiled = stmt.compile(engine)
        sql_str = str(compiled).upper()
        assert "DECR(" in sql_str
