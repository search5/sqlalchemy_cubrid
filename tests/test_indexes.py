"""Extended index introspection tests for sqlalchemy-cubrid dialect (0.5.0).

Tests UNIQUE, FILTERED (partial), and FUNCTION-BASED indexes.
Verifies that get_indexes() returns dialect_options with CUBRID-specific metadata.

Requires a running CUBRID instance:
    docker compose up -d
"""

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
)

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
        conn.execute(text("DROP TABLE IF EXISTS t_idx_test"))
        conn.commit()


def _get_index_by_name(indexes, name):
    for idx in indexes:
        if idx["name"] == name:
            return idx
    return None


class TestIndexIntrospectionRaw:
    """Test CUBRID index types with raw SQL to verify baseline."""

    def test_create_unique_index(self, engine):
        """UNIQUE index creation and catalog query."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_idx_test ("
                "  id INT PRIMARY KEY, name VARCHAR(50), score INT)"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX idx_unique_name ON t_idx_test (name)"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT is_unique FROM db_index "
                "WHERE class_name = 't_idx_test' AND index_name = 'idx_unique_name'"
            ))
            assert result.scalar() == "YES"

    def test_create_filtered_index(self, engine):
        """FILTERED (partial) index with WHERE clause."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_idx_test ("
                "  id INT PRIMARY KEY, name VARCHAR(50) NOT NULL, score INT NOT NULL)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_filtered_score ON t_idx_test (score) "
                "WHERE score > 50"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT filter_expression FROM db_index "
                "WHERE class_name = 't_idx_test' AND index_name = 'idx_filtered_score'"
            ))
            filt = result.scalar()
            assert filt is not None
            assert "50" in filt

    def test_create_function_index(self, engine):
        """FUNCTION-BASED index."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_idx_test ("
                "  id INT PRIMARY KEY, name VARCHAR(50))"
            ))
            conn.execute(text(
                "CREATE INDEX idx_func_lower ON t_idx_test (LOWER(name))"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT have_function FROM db_index "
                "WHERE class_name = 't_idx_test' AND index_name = 'idx_func_lower'"
            ))
            assert result.scalar() == "YES"


class TestIndexIntrospectionSQLAlchemy:
    """Test get_indexes() returns extended dialect_options."""

    def test_regular_index_dialect_options(self, engine):
        """Regular index has default dialect_options."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_idx_test ("
                "  id INT PRIMARY KEY, name VARCHAR(50), score INT)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_score ON t_idx_test (score)"
            ))
            conn.commit()

        insp = inspect(engine)
        indexes = insp.get_indexes("t_idx_test")
        idx = _get_index_by_name(indexes, "idx_score")
        assert idx is not None
        assert idx["unique"] is False
        assert idx["column_names"] == ["score"]
        opts = idx.get("dialect_options", {})
        assert opts.get("cubrid_filtered") is None
        assert opts.get("cubrid_function") is None

    def test_unique_index(self, engine):
        """UNIQUE index reflected correctly."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_idx_test ("
                "  id INT PRIMARY KEY, email VARCHAR(100))"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX idx_unique_email ON t_idx_test (email)"
            ))
            conn.commit()

        insp = inspect(engine)
        indexes = insp.get_indexes("t_idx_test")
        idx = _get_index_by_name(indexes, "idx_unique_email")
        assert idx is not None
        assert idx["unique"] is True

    def test_filtered_index_dialect_options(self, engine):
        """FILTERED index includes filter_expression in dialect_options."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_idx_test ("
                "  id INT PRIMARY KEY, status INT NOT NULL)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_active ON t_idx_test (status) WHERE status > 0"
            ))
            conn.commit()

        insp = inspect(engine)
        indexes = insp.get_indexes("t_idx_test")
        idx = _get_index_by_name(indexes, "idx_active")
        assert idx is not None
        opts = idx.get("dialect_options", {})
        assert opts.get("cubrid_filtered") is not None
        assert "0" in opts["cubrid_filtered"]

    def test_function_index_dialect_options(self, engine):
        """FUNCTION-BASED index includes function expr in dialect_options."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_idx_test ("
                "  id INT PRIMARY KEY, name VARCHAR(50))"
            ))
            conn.execute(text(
                "CREATE INDEX idx_lower ON t_idx_test (LOWER(name))"
            ))
            conn.commit()

        insp = inspect(engine)
        indexes = insp.get_indexes("t_idx_test")
        idx = _get_index_by_name(indexes, "idx_lower")
        assert idx is not None
        opts = idx.get("dialect_options", {})
        assert opts.get("cubrid_function") is not None
        assert "lower" in opts["cubrid_function"].lower()

    def test_multi_column_index(self, engine):
        """Multi-column index preserves column order."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_idx_test ("
                "  id INT PRIMARY KEY, a INT, b INT, c INT)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_abc ON t_idx_test (a, b, c)"
            ))
            conn.commit()

        insp = inspect(engine)
        indexes = insp.get_indexes("t_idx_test")
        idx = _get_index_by_name(indexes, "idx_abc")
        assert idx is not None
        assert idx["column_names"] == ["a", "b", "c"]

    def test_desc_index_column_sorting(self, engine):
        """Index with DESC columns reports column_sorting."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_idx_test ("
                "  id INT PRIMARY KEY, a INT, b INT)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_desc ON t_idx_test (a ASC, b DESC)"
            ))
            conn.commit()

        insp = inspect(engine)
        indexes = insp.get_indexes("t_idx_test")
        idx = _get_index_by_name(indexes, "idx_desc")
        assert idx is not None
        sorting = idx.get("column_sorting", {})
        # ASC is omitted (default), DESC is stored as tuple
        assert "a" not in sorting  # ASC is the default, not included
        assert sorting.get("b") == ("desc",)
