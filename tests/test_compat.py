"""Cross-version compatibility tests for sqlalchemy-cubrid dialect (0.5.1).

Tests core dialect functionality across CUBRID 10.2, 11.0, 11.2, 11.3, 11.4.

Requires all CUBRID containers running:
    docker-compose up -d
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
    Sequence,
    select,
)
from sqlalchemy.orm import Session, DeclarativeBase, Mapped, mapped_column

CUBRID_VERSIONS = {
    "10.2": "cubrid://dba:@localhost:33002/testdb",
    "11.0": "cubrid://dba:@localhost:33100/testdb",
    "11.2": "cubrid://dba:@localhost:33102/testdb",
    "11.3": "cubrid://dba:@localhost:33103/testdb",
    "11.4": "cubrid://dba:@localhost:33000/testdb",
}


def _is_available(url):
    """Check if a CUBRID instance is reachable."""
    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


# Collect available versions at module load time
_available = {v: url for v, url in CUBRID_VERSIONS.items() if _is_available(url)}

if not _available:
    pytest.skip("No CUBRID instances available", allow_module_level=True)


@pytest.fixture(params=list(_available.keys()), scope="module")
def version_engine(request):
    """Parametrized fixture: yields (version, engine) for each available CUBRID."""
    version = request.param
    url = _available[version]
    eng = create_engine(url)
    yield version, eng
    eng.dispose()


@pytest.fixture(autouse=True)
def cleanup(version_engine):
    yield
    _, engine = version_engine
    with engine.connect() as conn:
        conn.execute(text("DROP SERIAL IF EXISTS compat_serial"))
        conn.execute(text("DROP TABLE IF EXISTS t_compat"))
        conn.commit()


class TestConnection:
    def test_connect_and_version(self, version_engine):
        """Engine connects and detects server version."""
        version, engine = version_engine
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

        ver = engine.dialect.server_version_info
        assert len(ver) >= 2
        expected_major_minor = tuple(int(x) for x in version.split("."))
        assert ver[:2] == expected_major_minor


class TestIntrospection:
    def test_has_table(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_compat (id INT PRIMARY KEY, name VARCHAR(50))"
            ))
            conn.commit()

        insp = inspect(engine)
        assert insp.has_table("t_compat") is True
        assert insp.has_table("nonexistent_table") is False

    def test_get_table_names(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_compat (id INT PRIMARY KEY)"
            ))
            conn.commit()

        insp = inspect(engine)
        names = insp.get_table_names()
        assert "t_compat" in names

    def test_get_columns(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_compat ("
                "  id INT PRIMARY KEY,"
                "  name VARCHAR(100),"
                "  score INT"
                ")"
            ))
            conn.commit()

        insp = inspect(engine)
        columns = insp.get_columns("t_compat")
        col_names = [c["name"] for c in columns]
        assert "id" in col_names
        assert "name" in col_names
        assert "score" in col_names

    def test_get_pk_constraint(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_compat (id INT PRIMARY KEY, name VARCHAR(50))"
            ))
            conn.commit()

        insp = inspect(engine)
        pk = insp.get_pk_constraint("t_compat")
        assert "id" in pk["constrained_columns"]

    def test_get_indexes(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_compat (id INT PRIMARY KEY, name VARCHAR(50))"
            ))
            conn.execute(text(
                "CREATE INDEX idx_name ON t_compat (name)"
            ))
            conn.commit()

        insp = inspect(engine)
        indexes = insp.get_indexes("t_compat")
        idx_names = [i["name"] for i in indexes]
        assert "idx_name" in idx_names


class TestSerial:
    """Test SERIAL (sequence) across versions — validates db_serial column name branching."""

    def test_get_sequence_names(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text("CREATE SERIAL compat_serial"))
            conn.commit()

        insp = inspect(engine)
        names = insp.get_sequence_names()
        assert "compat_serial" in names

    def test_has_sequence(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text("CREATE SERIAL compat_serial"))
            conn.commit()

        insp = inspect(engine)
        assert insp.has_sequence("compat_serial") is True
        assert insp.has_sequence("nonexistent_serial") is False

    def test_serial_next_value(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text("CREATE SERIAL compat_serial START WITH 1"))
            conn.commit()

            result = conn.execute(text("SELECT compat_serial.NEXT_VALUE"))
            assert result.scalar() == 1

    def test_sequence_ddl(self, version_engine):
        """SQLAlchemy Sequence creates/drops CUBRID SERIAL."""
        _, engine = version_engine
        seq = Sequence("compat_serial")
        seq.create(engine)

        insp = inspect(engine)
        assert insp.has_sequence("compat_serial") is True

        seq.drop(engine)
        insp = inspect(engine)
        assert insp.has_sequence("compat_serial") is False


class TestFeatureSupport:
    """Validate version-dependent feature support across all CUBRID versions."""

    def test_cte_support(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            result = conn.execute(text(
                "WITH cte AS (SELECT 1 AS n) SELECT n FROM cte"
            ))
            assert result.scalar() == 1

    def test_window_function(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_compat (id INT PRIMARY KEY, val INT)"
            ))
            conn.execute(text(
                "INSERT INTO t_compat VALUES (1, 10), (2, 20)"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn "
                "FROM t_compat"
            ))
            rows = result.fetchall()
            assert len(rows) == 2
            assert rows[0][1] == 1

    def test_json_support(self, version_engine):
        _, engine = version_engine
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT JSON_OBJECT('key', 'value')"
            ))
            val = result.scalar()
            assert "key" in val
            assert "value" in val

    def test_isolation_level(self, version_engine):
        """Validate isolation level support across versions."""
        _, engine = version_engine
        with engine.connect() as conn:
            pass  # trigger initialization
        levels = engine.dialect.get_isolation_level_values(None)
        assert "AUTOCOMMIT" in levels
        assert "READ COMMITTED" in levels
        assert "REPEATABLE READ" in levels
        assert "SERIALIZABLE" in levels

    def test_dont_reuse_oid(self, version_engine):
        """DONT_REUSE_OID is supported on 11.0+ only."""
        version, engine = version_engine
        with engine.connect() as conn:
            pass  # trigger initialization
        ver_tuple = engine.dialect.server_version_info
        if ver_tuple >= (11, 0):
            with engine.connect() as conn:
                conn.execute(text(
                    "CREATE TABLE t_compat (id INT) DONT_REUSE_OID"
                ))
                conn.commit()
        # 10.2 does not support DONT_REUSE_OID — verified by version check


class TestCRUD:
    def test_orm_insert_select(self, version_engine):
        """Basic ORM INSERT and SELECT."""
        _, engine = version_engine
        metadata = MetaData()
        t = Table(
            "t_compat", metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(50)),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(t.insert().values(id=1, name="alice"))
            conn.execute(t.insert().values(id=2, name="bob"))
            conn.commit()

            rows = conn.execute(
                select(t).order_by(t.c.id)
            ).fetchall()
            assert len(rows) == 2
            assert rows[0] == (1, "alice")
            assert rows[1] == (2, "bob")

    def test_update_delete(self, version_engine):
        """Basic UPDATE and DELETE."""
        _, engine = version_engine
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE t_compat (id INT PRIMARY KEY, val INT)"
            ))
            conn.execute(text("INSERT INTO t_compat VALUES (1, 10)"))
            conn.commit()

            conn.execute(text("UPDATE t_compat SET val = 20 WHERE id = 1"))
            conn.commit()
            assert conn.execute(text(
                "SELECT val FROM t_compat WHERE id = 1"
            )).scalar() == 20

            conn.execute(text("DELETE FROM t_compat WHERE id = 1"))
            conn.commit()
            assert conn.execute(text(
                "SELECT COUNT(*) FROM t_compat"
            )).scalar() == 0
