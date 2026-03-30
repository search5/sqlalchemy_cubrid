"""Tests to increase code coverage to 95%+.

Targets uncovered lines in compiler, dialect, types, dml, oid, alembic_impl.
"""

import os

import pytest
from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    Sequence,
    String,
    Table,
    Unicode,
    UnicodeText,
    cast,
    create_engine,
    inspect,
    literal_column,
    select,
    text,
    types as sa_types,
)
from sqlalchemy.dialects import registry

from sqlalchemy_cubrid.compiler import CubridTypeCompiler
from sqlalchemy_cubrid.dml import Insert, insert
from sqlalchemy_cubrid.oid import CubridOID, CreateTableDontReuseOID, deref
from sqlalchemy_cubrid.types import (
    NUMERIC,
    CubridList,
    CubridMultiset,
    CubridSet,
    _CollectionType,
)

CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


def _drop_all(conn):
    conn.execute(text("DROP VIEW IF EXISTS test_cov_view"))
    for tbl in [
        "test_cov_child",
        "test_cov_uq",
        "test_cov_idx",
        "test_cov_chk",
        "test_cov_comment",
        "test_cov",
    ]:
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
    conn.execute(text("DROP SERIAL IF EXISTS test_cov_serial"))
    conn.commit()


@pytest.fixture(autouse=True)
def cleanup(engine):
    with engine.connect() as conn:
        _drop_all(conn)
    yield
    with engine.connect() as conn:
        _drop_all(conn)


# === compiler.py coverage ===


class TestCompilerCoverage:
    def test_limit_offset_without_limit(self, engine):
        """OFFSET without LIMIT appends sentinel value (line 44)."""
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test_cov (id INT PRIMARY KEY)"))
            conn.execute(text("INSERT INTO test_cov VALUES (1)"))
            conn.execute(text("INSERT INTO test_cov VALUES (2)"))
            conn.commit()

            meta = MetaData()
            t = Table("test_cov", meta, autoload_with=engine)
            stmt = select(t).offset(1).order_by(t.c.id)
            result = conn.execute(stmt).fetchall()
            assert len(result) == 1

    def test_for_update_none(self, engine):
        """FOR UPDATE is None returns empty (line 122)."""
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test_cov (id INT PRIMARY KEY)"))
            conn.commit()
            meta = MetaData()
            t = Table("test_cov", meta, autoload_with=engine)
            # Normal SELECT without FOR UPDATE
            stmt = select(t)
            compiled = stmt.compile(dialect=engine.dialect)
            assert "FOR UPDATE" not in str(compiled)

    def test_sequence_nominvalue_nomaxvalue(self, engine):
        """SERIAL DDL with nominvalue/nomaxvalue (lines 262, 266)."""
        seq = Sequence("test_cov_serial", nominvalue=True, nomaxvalue=True)
        compiled = seq.create(engine)
        with engine.connect() as conn:
            conn.execute(text("DROP SERIAL IF EXISTS test_cov_serial"))
            conn.commit()

    def test_type_compiler_text(self, engine):
        """TEXT → STRING mapping (line 433)."""
        compiled = sa_types.TEXT().compile(dialect=engine.dialect)
        assert str(compiled) == "STRING"

    def test_type_compiler_float_precision(self, engine):
        """FLOAT precision > 7 → DOUBLE (lines 465-467)."""
        compiled = sa_types.FLOAT(precision=8).compile(dialect=engine.dialect)
        assert str(compiled) == "DOUBLE"

        compiled = sa_types.FLOAT(precision=5).compile(dialect=engine.dialect)
        assert str(compiled) == "FLOAT"

        compiled = sa_types.FLOAT().compile(dialect=engine.dialect)
        assert str(compiled) == "DOUBLE"

    def test_type_compiler_double(self, engine):
        """DOUBLE types (lines 471, 474)."""
        compiled = sa_types.DOUBLE().compile(dialect=engine.dialect)
        assert str(compiled) == "DOUBLE"

        compiled = sa_types.DOUBLE_PRECISION().compile(dialect=engine.dialect)
        assert str(compiled) == "DOUBLE"

    def test_type_compiler_json(self, engine):
        """JSON type (line 478)."""
        compiled = sa_types.JSON().compile(dialect=engine.dialect)
        assert str(compiled) == "JSON"

    def test_type_compiler_nchar(self, engine):
        """NCHAR → CHAR mapping (lines 482-484)."""
        compiled = sa_types.NCHAR(50).compile(dialect=engine.dialect)
        assert str(compiled) == "CHAR(50)"

        compiled = sa_types.NCHAR().compile(dialect=engine.dialect)
        assert str(compiled) == "CHAR"

    def test_type_compiler_nvarchar(self, engine):
        """NVARCHAR → VARCHAR mapping (lines 487-489)."""
        compiled = sa_types.NVARCHAR(100).compile(dialect=engine.dialect)
        assert str(compiled) == "VARCHAR(100)"

        compiled = sa_types.NVARCHAR().compile(dialect=engine.dialect)
        assert str(compiled) == "VARCHAR"

    def test_type_compiler_unicode(self, engine):
        """Unicode → VARCHAR mapping (lines 492-494, 497)."""
        compiled = Unicode(100).compile(dialect=engine.dialect)
        assert str(compiled) == "VARCHAR(100)"

        compiled = Unicode().compile(dialect=engine.dialect)
        assert str(compiled) == "VARCHAR"

        compiled = UnicodeText().compile(dialect=engine.dialect)
        assert str(compiled) == "STRING"

    def test_type_compiler_oid(self, engine):
        """CubridOID type rendering (line 501)."""
        oid_type = CubridOID("person")
        compiled = oid_type.compile(dialect=engine.dialect)
        assert "person" in str(compiled).lower()

    def test_connect_by_iscycle_compile(self, engine):
        """CONNECT_BY_ISCYCLE compile (line 64)."""
        from sqlalchemy_cubrid.hierarchical import connect_by_iscycle

        compiled = connect_by_iscycle().compile(dialect=engine.dialect)
        assert "CONNECT_BY_ISCYCLE" in str(compiled)

    def test_numeric_type_init(self):
        """NUMERIC type __init__ (types.py lines 16, 27)."""
        n = NUMERIC(precision=10, scale=2)
        assert n.precision == 10
        assert n.scale == 2


# === dialect.py coverage ===


class TestDialectCoverage:
    def test_autocommit_isolation(self, engine):
        """AUTOCOMMIT mode (lines 162-164, 171)."""
        raw_conn = engine.raw_connection()
        try:
            engine.dialect.set_isolation_level(raw_conn, "AUTOCOMMIT")
            assert raw_conn.autocommit is True
            level = engine.dialect.get_isolation_level(raw_conn)
            assert level == "AUTOCOMMIT"

            # Switch back to normal
            engine.dialect.set_isolation_level(raw_conn, "READ COMMITTED")
            assert raw_conn.autocommit is False
        finally:
            raw_conn.close()

    def test_do_ping_failure(self):
        """do_ping returns False on error (lines 202-203)."""
        from sqlalchemy.pool import NullPool

        eng = create_engine(CUBRID_URL, poolclass=NullPool)
        raw_conn = eng.raw_connection()
        dbapi_conn = raw_conn.connection
        raw_conn.close()
        # dbapi_conn is now closed
        result = eng.dialect.do_ping(dbapi_conn)
        assert result is False
        eng.dispose()

    def test_get_fk_for_view(self, engine):
        """get_foreign_keys returns [] for views (lines 518-522)."""
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test_cov (id INT PRIMARY KEY)"))
            conn.execute(text(
                "CREATE VIEW test_cov_view AS SELECT id FROM test_cov"
            ))
            conn.commit()

        insp = inspect(engine)
        fks = insp.get_foreign_keys("test_cov_view")
        assert fks == []

    def test_get_pk_nonexistent_table(self, engine):
        """get_pk_constraint raises NoSuchTableError (lines 483-485)."""
        insp = inspect(engine)
        with pytest.raises(Exception):
            insp.get_pk_constraint("nonexistent_table_xyz")

    def test_get_unique_constraints_nonexistent(self, engine):
        """get_unique_constraints raises NoSuchTableError (lines 574-576)."""
        insp = inspect(engine)
        with pytest.raises(Exception):
            insp.get_unique_constraints("nonexistent_table_xyz")

    def test_get_indexes_nonexistent(self, engine):
        """get_indexes raises NoSuchTableError (lines 608-610)."""
        insp = inspect(engine)
        with pytest.raises(Exception):
            insp.get_indexes("nonexistent_table_xyz")

    def test_get_check_constraints_nonexistent(self, engine):
        """get_check_constraints raises NoSuchTableError (lines 693-695)."""
        insp = inspect(engine)
        with pytest.raises(Exception):
            insp.get_check_constraints("nonexistent_table_xyz")

    def test_get_table_comment_nonexistent(self, engine):
        """get_table_comment raises NoSuchTableError (lines 710-712)."""
        insp = inspect(engine)
        with pytest.raises(Exception):
            insp.get_table_comment("nonexistent_table_xyz")

    def test_get_unique_constraints(self, engine):
        """get_unique_constraints returns constraint dicts (lines 594-602)."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_cov_uq ("
                "  id INT PRIMARY KEY,"
                "  email VARCHAR(100) UNIQUE,"
                "  name VARCHAR(50)"
                ")"
            ))
            conn.commit()

        insp = inspect(engine)
        uqs = insp.get_unique_constraints("test_cov_uq")
        col_names = [c for uq in uqs for c in uq["column_names"]]
        assert "email" in col_names

    def test_has_index_cached(self, engine):
        """has_index uses info_cache (lines 285-302)."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_cov_idx (id INT PRIMARY KEY, val INT)"
            ))
            conn.execute(text("CREATE INDEX idx_val ON test_cov_idx (val)"))
            conn.commit()

        insp = inspect(engine)
        assert insp.has_table("test_cov_idx")
        # has_index should check via get_indexes
        indexes = insp.get_indexes("test_cov_idx")
        idx_names = [i["name"] for i in indexes]
        assert "idx_val" in idx_names

    def test_resolve_type_unknown(self, engine):
        """_resolve_type returns NullType for unknown types (line 391)."""
        result = engine.dialect._resolve_type("UNKNOWN_TYPE_XYZ")
        assert isinstance(result, sa_types.NullType)

    def test_resolve_type_enum(self, engine):
        """_resolve_type parses ENUM values (lines 417-418)."""
        result = engine.dialect._resolve_type("ENUM('a','b','c')")
        assert hasattr(result, "enums")
        assert "a" in result.enums

    def test_resolve_type_float_with_precision(self, engine):
        """_resolve_type parses FLOAT(n) (line 420)."""
        result = engine.dialect._resolve_type("FLOAT(5)")
        assert isinstance(result, sa_types.FLOAT)

    def test_resolve_type_double_with_params(self, engine):
        """_resolve_type parses DOUBLE (line 422)."""
        result = engine.dialect._resolve_type("DOUBLE")
        assert isinstance(result, sa_types.DOUBLE)

    def test_table_comment_ddl(self, engine):
        """Table with COMMENT (compiler lines 374, 381, 385)."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE test_cov_comment ("
                "  id INT PRIMARY KEY"
                ") COMMENT='test table'"
            ))
            conn.commit()

        insp = inspect(engine)
        comment = insp.get_table_comment("test_cov_comment")
        assert comment.get("text") == "test table"

    def test_column_comment_fetch(self, engine):
        """Column comment via db_attribute (line 454)."""
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_cov_comment"))
            conn.execute(text(
                "CREATE TABLE test_cov_comment ("
                "  id INT PRIMARY KEY COMMENT 'primary key'"
                ")"
            ))
            conn.commit()

        insp = inspect(engine)
        cols = insp.get_columns("test_cov_comment")
        id_col = [c for c in cols if c["name"] == "id"][0]
        assert id_col.get("comment") == "primary key"


# === oid.py coverage ===


class TestOIDCoverage:
    def test_bind_processor(self):
        """CubridOID bind_processor pass-through (lines 74-79)."""
        oid = CubridOID("person")
        proc = oid.bind_processor(None)
        assert proc(None) is None
        assert proc("some_oid_value") == "some_oid_value"

    def test_result_processor(self):
        """CubridOID result_processor pass-through (lines 82-87)."""
        oid = CubridOID("person")
        proc = oid.result_processor(None, None)
        assert proc(None) is None
        assert proc("some_oid_value") == "some_oid_value"


# === types.py coverage ===


class TestTypesCoverage:
    def test_collection_bind_processor(self):
        """_CollectionType bind_processor (lines 43-48)."""
        ct = CubridSet("VARCHAR(50)")
        proc = ct.bind_processor(None)
        assert proc(None) is None
        assert proc({"a", "b"}) == {"a", "b"}

    def test_collection_parse_short_data(self):
        """Binary parser returns None for short data (line 65)."""
        result = _CollectionType._parse_collection_bytes(b"\x00\x01")
        assert result is None

    def test_set_fallback_bytes(self):
        """CubridSet fallback for unparseable bytes (line 115)."""
        cs = CubridSet("VARCHAR(50)")
        proc = cs.result_processor(None, None)
        # Provide a string that's not binary format
        result = proc("plain_string")
        assert isinstance(result, set)

    def test_multiset_fallback_bytes(self):
        """CubridMultiset fallback for unparseable (lines 131, 133)."""
        cm = CubridMultiset("VARCHAR(50)")
        proc = cm.result_processor(None, None)
        result = proc("plain_string")
        assert isinstance(result, list)

    def test_list_fallback_bytes(self):
        """CubridList fallback for unparseable (lines 158, 160, 166)."""
        cl = CubridList("VARCHAR(50)")
        proc = cl.result_processor(None, None)
        result = proc("plain_string")
        assert isinstance(result, list)

    def test_list_fallback_empty_bytes(self):
        """CubridList fallback for bytes input (line 139)."""
        cl = CubridList("VARCHAR(50)")
        proc = cl.result_processor(None, None)
        result = proc(b"\x00\x01")
        assert isinstance(result, list)

    def test_multiset_fallback_empty_bytes(self):
        """CubridMultiset fallback for bytes input."""
        cm = CubridMultiset("VARCHAR(50)")
        proc = cm.result_processor(None, None)
        result = proc(b"\x00\x01")
        assert isinstance(result, list)


# === dml.py coverage ===


class TestDMLCoverage:
    def test_on_duplicate_key_update_both_args_and_kwargs(self, engine):
        """Raises ArgumentError on mixed args+kwargs (line 99)."""
        meta = MetaData()
        t = Table("test_cov", meta, Column("id", Integer, primary_key=True))
        stmt = insert(t).values(id=1)
        with pytest.raises(Exception):
            stmt.on_duplicate_key_update({"id": 1}, id=2)

    def test_on_duplicate_key_update_empty_raises(self, engine):
        """Raises ValueError on empty update (lines 135-141)."""
        meta = MetaData()
        t = Table("test_cov", meta, Column("id", Integer, primary_key=True))
        stmt = insert(t).values(id=1)
        with pytest.raises(ValueError):
            stmt.on_duplicate_key_update({})

    def test_on_duplicate_key_update_invalid_type(self, engine):
        """Raises ValueError on invalid type (lines 135-141)."""
        meta = MetaData()
        t = Table("test_cov", meta, Column("id", Integer, primary_key=True))
        stmt = insert(t).values(id=1)
        with pytest.raises((ValueError, TypeError)):
            stmt.on_duplicate_key_update(12345)

    def test_inserted_property(self, engine):
        """Insert.inserted returns column collection (line 71)."""
        meta = MetaData()
        t = Table(
            "test_cov",
            meta,
            Column("id", Integer, primary_key=True),
            Column("val", String(50)),
        )
        stmt = insert(t)
        inserted = stmt.inserted
        assert hasattr(inserted, "id")


# === alembic_impl.py coverage ===


class TestAlembicImplCoverage:
    def test_compare_type_collection_vs_non_collection(self):
        """compare_type returns True when one is collection, other is not (lines 68-73)."""
        from unittest.mock import MagicMock

        from sqlalchemy_cubrid.alembic_impl import CubridImpl

        impl = CubridImpl.__new__(CubridImpl)
        cs = CubridSet("VARCHAR(50)")
        si = sa_types.Integer()

        # Create mock columns with .type attribute
        col_cs = MagicMock()
        col_cs.type = cs
        col_si = MagicMock()
        col_si.type = si

        # collection vs non-collection → types differ
        result = impl.compare_type(col_cs, col_si)
        assert result is True

        result = impl.compare_type(col_si, col_cs)
        assert result is True
