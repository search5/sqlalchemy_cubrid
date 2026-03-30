"""OID reference tests for 0.7.1 features.

Tests OID column types, path expression dereferencing, and OID introspection.

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import (
    create_engine, text, inspect, Column, Integer, String, literal_column,
    select,
)

from sqlalchemy_cubrid.oid import (
    CubridOID,
    OIDDeref,
    deref,
    CreateTableDontReuseOID,
)

import os
CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


def _requires_dont_reuse_oid(engine):
    """Skip if CUBRID version < 11.0 (DONT_REUSE_OID not supported)."""
    # Ensure dialect is initialized (server_version_info requires a connection)
    if engine.dialect.server_version_info is None:
        with engine.connect():
            pass
    version = engine.dialect.server_version_info or (0,)
    if version < (11, 0):
        pytest.skip("DONT_REUSE_OID requires CUBRID 11.0+")


@pytest.fixture(scope="module")
def oid_tables(engine):
    """Create referable tables and OID reference tables."""
    _requires_dont_reuse_oid(engine)
    with engine.connect() as conn:
        # Cleanup in reverse dependency order
        conn.execute(text("DROP TABLE IF EXISTS test_oid_department"))
        conn.execute(text("DROP TABLE IF EXISTS test_oid_team"))
        conn.execute(text("DROP TABLE IF EXISTS test_oid_person"))

        # Referable table (DONT_REUSE_OID)
        conn.execute(text(
            "CREATE TABLE test_oid_person ("
            "  id INTEGER AUTO_INCREMENT PRIMARY KEY,"
            "  name VARCHAR(50) NOT NULL,"
            "  age INTEGER"
            ") DONT_REUSE_OID"
        ))

        # Table with OID reference column (DONT_REUSE_OID so it can also
        # be referenced by test_oid_team)
        conn.execute(text(
            "CREATE TABLE test_oid_department ("
            "  id INTEGER AUTO_INCREMENT PRIMARY KEY,"
            "  dept_name VARCHAR(50) NOT NULL,"
            "  manager test_oid_person"
            ") DONT_REUSE_OID"
        ))

        # Table with chained OID reference (dept -> person)
        conn.execute(text(
            "CREATE TABLE test_oid_team ("
            "  id INTEGER AUTO_INCREMENT PRIMARY KEY,"
            "  team_name VARCHAR(50) NOT NULL,"
            "  parent_dept test_oid_department"
            ") DONT_REUSE_OID"
        ))

        # Insert test data
        conn.execute(text(
            "INSERT INTO test_oid_person (name, age) VALUES ('Alice', 30)"
        ))
        conn.execute(text(
            "INSERT INTO test_oid_person (name, age) VALUES ('Bob', 40)"
        ))
        conn.execute(text(
            "INSERT INTO test_oid_department (dept_name, manager) "
            "VALUES ('Engineering', "
            "  (SELECT test_oid_person FROM test_oid_person WHERE name = 'Alice'))"
        ))
        conn.execute(text(
            "INSERT INTO test_oid_department (dept_name, manager) "
            "VALUES ('Marketing', "
            "  (SELECT test_oid_person FROM test_oid_person WHERE name = 'Bob'))"
        ))
        conn.execute(text(
            "INSERT INTO test_oid_team (team_name, parent_dept) "
            "VALUES ('Backend', "
            "  (SELECT test_oid_department FROM test_oid_department "
            "   WHERE dept_name = 'Engineering'))"
        ))
        conn.commit()

    yield

    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_oid_team"))
        conn.execute(text("DROP TABLE IF EXISTS test_oid_department"))
        conn.execute(text("DROP TABLE IF EXISTS test_oid_person"))
        conn.commit()


class TestCreateTableDontReuseOID:
    """Tests for CreateTableDontReuseOID DDL construct."""

    def test_compile_output(self, engine):
        ddl = CreateTableDontReuseOID(
            "my_table",
            Column("id", Integer),
            Column("name", String(50)),
        )
        compiled = ddl.compile(dialect=engine.dialect)
        sql = str(compiled)
        assert "CREATE TABLE" in sql
        assert "my_table" in sql
        version = engine.dialect.server_version_info or (0,)
        if version >= (11, 0):
            assert "DONT_REUSE_OID" in sql
        else:
            assert "DONT_REUSE_OID" not in sql

    def test_create_and_drop(self, engine):
        _requires_dont_reuse_oid(engine)
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_oid_ddl_referable"))

            ddl = CreateTableDontReuseOID(
                "test_oid_ddl_referable",
                Column("id", Integer),
                Column("val", String(50)),
            )
            conn.execute(ddl)
            conn.commit()

            assert engine.dialect.has_table(conn, "test_oid_ddl_referable")

            conn.execute(text("DROP TABLE test_oid_ddl_referable"))
            conn.commit()


class TestCubridOIDType:
    """Tests for CubridOID type rendering."""

    def test_get_col_spec(self):
        oid_type = CubridOID("person")
        assert oid_type.get_col_spec() == "person"

    def test_type_compiler(self, engine):
        oid_type = CubridOID("test_oid_person")
        rendered = engine.dialect.type_compiler_instance.process(oid_type)
        assert rendered == "test_oid_person"


class TestOIDDeref:
    """Tests for OID dereference (path expression) compilation."""

    def test_simple_deref_compile(self, engine):
        expr = deref(literal_column("manager"), "name")
        compiled = expr.compile(dialect=engine.dialect)
        assert str(compiled) == "manager.name"

    def test_chained_deref_compile(self, engine):
        expr = deref(deref(literal_column("parent_dept"), "manager"), "name")
        compiled = expr.compile(dialect=engine.dialect)
        assert str(compiled) == "parent_dept.manager.name"

    def test_deref_with_type(self):
        expr = deref(literal_column("manager"), "age", type_=Integer())
        assert isinstance(expr.type, Integer)

    def test_deref_default_type(self):
        expr = deref(literal_column("manager"), "name")
        assert isinstance(expr.type, String)


class TestOIDQueryExecution:
    """Tests for OID reference queries against live CUBRID."""

    def test_select_oid_column(self, engine, oid_tables):
        """OID columns should be selectable (returns OID string)."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT manager FROM test_oid_department "
                "WHERE dept_name = 'Engineering'"
            ))
            row = result.fetchone()
            assert row is not None
            # OID value is returned (format varies by driver)
            assert row[0] is not None

    def test_path_expression_single_level(self, engine, oid_tables):
        """Dereference OID column to access referenced object attribute."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT manager.name FROM test_oid_department "
                "WHERE dept_name = 'Engineering'"
            ))
            row = result.fetchone()
            assert row is not None
            assert row[0] == "Alice"

    def test_path_expression_multi_level(self, engine, oid_tables):
        """Chain dereferences across two OID references."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT parent_dept.manager.name FROM test_oid_team "
                "WHERE team_name = 'Backend'"
            ))
            row = result.fetchone()
            assert row is not None
            assert row[0] == "Alice"

    def test_deref_in_select(self, engine, oid_tables):
        """Use deref() construct in a SQLAlchemy select."""
        with engine.connect() as conn:
            stmt = select(
                deref(literal_column("manager"), "name")
            ).select_from(text("test_oid_department")).where(
                text("dept_name = 'Marketing'")
            )
            result = conn.execute(stmt)
            row = result.fetchone()
            assert row is not None
            assert row[0] == "Bob"

    def test_chained_deref_in_select(self, engine, oid_tables):
        """Use chained deref() in a SQLAlchemy select."""
        with engine.connect() as conn:
            stmt = select(
                deref(
                    deref(literal_column("parent_dept"), "manager"),
                    "name",
                )
            ).select_from(text("test_oid_team")).where(
                text("team_name = 'Backend'")
            )
            result = conn.execute(stmt)
            row = result.fetchone()
            assert row is not None
            assert row[0] == "Alice"

    def test_path_expression_in_where(self, engine, oid_tables):
        """Use path expression in WHERE clause."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT dept_name FROM test_oid_department "
                "WHERE manager.name = 'Bob'"
            ))
            row = result.fetchone()
            assert row is not None
            assert row[0] == "Marketing"


class TestOIDIntrospection:
    """Tests for OID column introspection."""

    def test_get_columns_includes_oid(self, engine, oid_tables):
        """get_columns() should return OID columns."""
        with engine.connect() as conn:
            cols = engine.dialect.get_columns(conn, "test_oid_department")
            col_names = [c["name"] for c in cols]
            assert "manager" in col_names

    def test_get_oid_columns(self, engine, oid_tables):
        """get_oid_columns() returns OID reference info."""
        with engine.connect() as conn:
            oid_cols = engine.dialect.get_oid_columns(
                conn, "test_oid_department"
            )
            assert len(oid_cols) >= 1
            manager_col = next(
                c for c in oid_cols if c["name"] == "manager"
            )
            assert manager_col["referenced_class"] == "test_oid_person"

    def test_get_oid_columns_no_oid(self, engine, oid_tables):
        """Tables without OID columns return empty list."""
        with engine.connect() as conn:
            oid_cols = engine.dialect.get_oid_columns(
                conn, "test_oid_person"
            )
            assert oid_cols == []

    def test_get_oid_columns_chained(self, engine, oid_tables):
        """get_oid_columns() on a table referencing another OID table."""
        with engine.connect() as conn:
            oid_cols = engine.dialect.get_oid_columns(
                conn, "test_oid_team"
            )
            assert len(oid_cols) >= 1
            dept_col = next(
                c for c in oid_cols if c["name"] == "parent_dept"
            )
            assert dept_col["referenced_class"] == "test_oid_department"
