"""View introspection tests for sqlalchemy-cubrid dialect (0.5.0).

Tests get_view_names() and get_view_definition().

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import (
    create_engine,
    text,
    inspect,
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
        conn.execute(text("DROP VIEW IF EXISTS v_test_simple"))
        conn.execute(text("DROP VIEW IF EXISTS v_test_filtered"))
        conn.execute(text("DROP VIEW IF EXISTS v_test_other"))
        conn.execute(text("DROP TABLE IF EXISTS t_view_base"))
        conn.commit()


@pytest.fixture()
def base_table(engine):
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE t_view_base ("
            "  id INT PRIMARY KEY, name VARCHAR(50), score INT)"
        ))
        conn.execute(text(
            "INSERT INTO t_view_base VALUES (1, 'Alice', 90), (2, 'Bob', 60)"
        ))
        conn.commit()
    yield
    # cleanup fixture handles DROP


class TestViewRaw:
    """Test CUBRID view operations with raw SQL."""

    def test_create_view(self, engine, base_table):
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIEW v_test_simple AS "
                "SELECT id, name FROM t_view_base"
            ))
            conn.commit()

            result = conn.execute(text("SELECT * FROM v_test_simple"))
            rows = result.fetchall()
            assert len(rows) == 2

    def test_view_in_db_class(self, engine, base_table):
        """Views appear in db_class with class_type='VCLASS'."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIEW v_test_simple AS "
                "SELECT id, name FROM t_view_base"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT class_name FROM db_class "
                "WHERE class_type = 'VCLASS' "
                "AND class_name = 'v_test_simple'"
            ))
            assert result.fetchone() is not None

    def test_view_definition_in_db_vclass(self, engine, base_table):
        """View definition stored in db_vclass."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIEW v_test_simple AS "
                "SELECT id, name FROM t_view_base"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT vclass_def FROM db_vclass "
                "WHERE vclass_name = 'v_test_simple'"
            ))
            defn = result.scalar()
            assert defn is not None
            assert "t_view_base" in defn.lower()

    def test_drop_view(self, engine, base_table):
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIEW v_test_simple AS "
                "SELECT id, name FROM t_view_base"
            ))
            conn.commit()
            conn.execute(text("DROP VIEW v_test_simple"))
            conn.commit()

            result = conn.execute(text(
                "SELECT COUNT(*) FROM db_class "
                "WHERE class_name = 'v_test_simple'"
            ))
            assert result.scalar() == 0


class TestViewIntrospection:
    """Test view introspection via SQLAlchemy Inspector."""

    def test_get_view_names_empty(self, engine, base_table):
        """get_view_names() returns empty list when no views exist."""
        insp = inspect(engine)
        names = insp.get_view_names()
        assert "v_test_simple" not in names

    def test_get_view_names(self, engine, base_table):
        """get_view_names() lists user-created views."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIEW v_test_simple AS "
                "SELECT id, name FROM t_view_base"
            ))
            conn.execute(text(
                "CREATE VIEW v_test_filtered AS "
                "SELECT id, name FROM t_view_base WHERE score > 70"
            ))
            conn.commit()

        insp = inspect(engine)
        names = insp.get_view_names()
        assert "v_test_simple" in names
        assert "v_test_filtered" in names

    def test_get_view_names_excludes_tables(self, engine, base_table):
        """get_view_names() does not include regular tables."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIEW v_test_simple AS "
                "SELECT id, name FROM t_view_base"
            ))
            conn.commit()

        insp = inspect(engine)
        names = insp.get_view_names()
        assert "t_view_base" not in names

    def test_get_view_definition(self, engine, base_table):
        """get_view_definition() returns the SELECT statement."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIEW v_test_simple AS "
                "SELECT id, name FROM t_view_base"
            ))
            conn.commit()

        insp = inspect(engine)
        defn = insp.get_view_definition("v_test_simple")
        assert defn is not None
        assert "t_view_base" in defn.lower()

    def test_get_view_definition_nonexistent(self, engine, base_table):
        """get_view_definition() raises NoSuchTableError for nonexistent view."""
        from sqlalchemy.exc import NoSuchTableError
        insp = inspect(engine)
        with pytest.raises(NoSuchTableError):
            insp.get_view_definition("nonexistent_view")

    def test_get_view_definition_with_where(self, engine, base_table):
        """View definition preserves WHERE clause."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIEW v_test_filtered AS "
                "SELECT id, name FROM t_view_base WHERE score > 70"
            ))
            conn.commit()

        insp = inspect(engine)
        defn = insp.get_view_definition("v_test_filtered")
        assert defn is not None
        assert "70" in defn
