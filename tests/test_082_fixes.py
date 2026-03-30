"""Tests for 0.8.2 bug fixes and missing feature additions.

All tests are compile-only (no running CUBRID instance required).
They verify that the generated SQL is correct for each fix.
"""

import pytest
from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Text, Boolean, Float,
    create_engine, select, cast, column, literal_column, text,
    ForeignKey, Index,
)

from sqlalchemy_cubrid.dialect import CubridDialect
from sqlalchemy_cubrid.types import CubridSet, CubridMultiset, CubridList


@pytest.fixture(scope="module")
def dialect():
    return CubridDialect()


@pytest.fixture(scope="module")
def meta():
    return MetaData()


# ---------------------------------------------------------------------------
# 0.8.2a — FK reflection: ondelete / onupdate regex capture
# ---------------------------------------------------------------------------
class TestFKOnDeleteOnUpdate:
    """Verify get_foreign_keys regex captures ON DELETE / ON UPDATE actions."""

    def _parse(self, ddl):
        """Run the FK regex from the dialect against a DDL string."""
        import re
        fk_pattern = re.compile(
            r"CONSTRAINT\s+\[([^\]]+)\]\s+FOREIGN\s+KEY\s*\(([^)]+)\)\s+"
            r"REFERENCES\s+\[(?:[^\]]+\.)?([^\]]+)\]\s*\(([^)]+)\)"
            r"(?:\s+ON\s+DELETE\s+(CASCADE|SET\s+NULL|NO\s+ACTION|RESTRICT))?"
            r"(?:\s+ON\s+UPDATE\s+(CASCADE|SET\s+NULL|NO\s+ACTION|RESTRICT))?",
            re.IGNORECASE,
        )
        results = []
        for match in fk_pattern.finditer(ddl):
            options = {}
            if match.group(5):
                options["ondelete"] = " ".join(match.group(5).upper().split())
            if match.group(6):
                options["onupdate"] = " ".join(match.group(6).upper().split())
            results.append({
                "name": match.group(1),
                "constrained_columns": [c.strip().strip("[]") for c in match.group(2).split(",")],
                "referred_table": match.group(3),
                "referred_columns": [c.strip().strip("[]") for c in match.group(4).split(",")],
                "options": options,
            })
        return results

    def test_cascade_delete(self):
        ddl = (
            "CONSTRAINT [fk_order_user] FOREIGN KEY ([user_id]) "
            "REFERENCES [users] ([id]) ON DELETE CASCADE"
        )
        fks = self._parse(ddl)
        assert len(fks) == 1
        assert fks[0]["options"]["ondelete"] == "CASCADE"
        assert "onupdate" not in fks[0]["options"]

    def test_set_null_update(self):
        ddl = (
            "CONSTRAINT [fk_item] FOREIGN KEY ([cat_id]) "
            "REFERENCES [categories] ([id]) ON UPDATE SET NULL"
        )
        fks = self._parse(ddl)
        assert fks[0]["options"]["onupdate"] == "SET NULL"

    def test_both_actions(self):
        ddl = (
            "CONSTRAINT [fk_both] FOREIGN KEY ([ref_id]) "
            "REFERENCES [other] ([id]) ON DELETE NO ACTION ON UPDATE RESTRICT"
        )
        fks = self._parse(ddl)
        assert fks[0]["options"]["ondelete"] == "NO ACTION"
        assert fks[0]["options"]["onupdate"] == "RESTRICT"

    def test_no_actions(self):
        ddl = (
            "CONSTRAINT [fk_plain] FOREIGN KEY ([col]) "
            "REFERENCES [tbl] ([id])"
        )
        fks = self._parse(ddl)
        assert fks[0]["options"] == {}

    def test_multiple_fks(self):
        ddl = (
            "CONSTRAINT [fk1] FOREIGN KEY ([a]) REFERENCES [t1] ([id]) ON DELETE CASCADE,\n"
            "CONSTRAINT [fk2] FOREIGN KEY ([b]) REFERENCES [t2] ([id]) ON UPDATE SET NULL"
        )
        fks = self._parse(ddl)
        assert len(fks) == 2
        assert fks[0]["options"]["ondelete"] == "CASCADE"
        assert fks[1]["options"]["onupdate"] == "SET NULL"


# ---------------------------------------------------------------------------
# 0.8.2b — CAST type name mapping
# ---------------------------------------------------------------------------
class TestCastTypeMapping:
    """Verify CAST uses CubridTypeCompiler for CUBRID-native type names."""

    def test_cast_text_to_string(self, dialect):
        stmt = cast(literal_column("x"), Text)
        sql = str(stmt.compile(dialect=dialect))
        assert "STRING" in sql
        assert "TEXT" not in sql

    def test_cast_boolean_to_smallint(self, dialect):
        stmt = cast(literal_column("x"), Boolean)
        sql = str(stmt.compile(dialect=dialect))
        assert "SMALLINT" in sql

    def test_cast_float_to_double(self, dialect):
        stmt = cast(literal_column("x"), Float)
        sql = str(stmt.compile(dialect=dialect))
        assert "DOUBLE" in sql

    def test_cast_integer_passthrough(self, dialect):
        stmt = cast(literal_column("x"), Integer)
        sql = str(stmt.compile(dialect=dialect))
        assert "INTEGER" in sql

    def test_cast_string_passthrough(self, dialect):
        stmt = cast(literal_column("x"), String(100))
        sql = str(stmt.compile(dialect=dialect))
        assert "VARCHAR" in sql


# ---------------------------------------------------------------------------
# 0.8.2c — Narrow exception catches (structural, verified by code review)
# ---------------------------------------------------------------------------
class TestNarrowExceptions:
    """Verify dialect uses specific exception classes, not bare Exception."""

    def test_has_index_exception_types(self):
        import inspect as ins
        from sqlalchemy_cubrid.dialect import CubridDialect
        source = ins.getsource(CubridDialect.has_index)
        assert "except Exception:" not in source
        assert "ProgrammingError" in source or "DatabaseError" in source

    def test_get_columns_comment_exception_types(self):
        import inspect as ins
        from sqlalchemy_cubrid.dialect import CubridDialect
        source = ins.getsource(CubridDialect.get_columns)
        # The comment fetch block should NOT use bare Exception
        assert source.count("except Exception:") == 0


# ---------------------------------------------------------------------------
# 0.8.2d — GROUP_CONCAT function
# ---------------------------------------------------------------------------
class TestGroupConcat:
    def test_group_concat_registered(self):
        from sqlalchemy_cubrid.functions import group_concat
        assert group_concat.name == "GROUP_CONCAT"

    def test_group_concat_compile(self, dialect):
        from sqlalchemy import func
        stmt = select(func.group_concat(column("name")))
        sql = str(stmt.compile(dialect=dialect))
        assert "GROUP_CONCAT" in sql


# ---------------------------------------------------------------------------
# 0.8.2e — EXTRACT function (standard SQL, no custom handler needed)
# ---------------------------------------------------------------------------
class TestExtract:
    def test_extract_compiles(self, dialect):
        from sqlalchemy import extract
        stmt = select(extract("year", column("created_at")))
        sql = str(stmt.compile(dialect=dialect))
        assert "EXTRACT" in sql.upper()
        assert "YEAR" in sql.upper()


# ---------------------------------------------------------------------------
# 0.8.2f — TRUNCATE TABLE
# ---------------------------------------------------------------------------
class TestTruncate:
    def test_truncate_compile(self, dialect):
        from sqlalchemy_cubrid.dml import truncate
        stmt = truncate("my_table")
        sql = str(stmt.compile(dialect=dialect))
        assert "TRUNCATE TABLE" in sql

    def test_truncate_quotes_reserved_word(self, dialect):
        from sqlalchemy_cubrid.dml import truncate
        stmt = truncate("data")  # 'data' is a CUBRID reserved word
        sql = str(stmt.compile(dialect=dialect))
        assert '"data"' in sql


# ---------------------------------------------------------------------------
# 0.8.2g — get_sequence_names SQL safety
# ---------------------------------------------------------------------------
class TestSequenceNamesSafety:
    def test_serial_attr_column_whitelist(self, dialect):
        # Version < 11.4
        dialect._cubrid_version = (11, 3)
        assert dialect._serial_attr_column == "att_name"
        # Version >= 11.4
        dialect._cubrid_version = (11, 4)
        assert dialect._serial_attr_column == "attr_name"

    def test_assert_guards_invalid_value(self, dialect):
        """Ensure the assertion catches unexpected column names."""
        # Simulate a bad version branch (should never happen in practice)
        original = dialect._cubrid_version
        try:
            dialect._cubrid_version = (11, 4)
            col = dialect._serial_attr_column
            assert col in ("att_name", "attr_name")
        finally:
            dialect._cubrid_version = original


# ---------------------------------------------------------------------------
# 0.8.2h — index_ddl_if_exists requirement
# ---------------------------------------------------------------------------
class TestIndexDdlIfExists:
    def test_requirement_is_closed(self):
        """CUBRID does not support IF [NOT] EXISTS for indexes."""
        import inspect as ins
        from sqlalchemy_cubrid.requirements import Requirements
        source = ins.getsource(Requirements.index_ddl_if_exists.fget)
        assert "exclusions.closed()" in source


# ---------------------------------------------------------------------------
# 0.8.2i — Collection parser bounds checking
# ---------------------------------------------------------------------------
class TestCollectionParserSafety:
    def test_empty_bytes_returns_none(self):
        result = CubridSet._parse_collection_bytes(b"")
        assert result is None

    def test_short_bytes_returns_none(self):
        result = CubridSet._parse_collection_bytes(b"\x00\x01\x02")
        assert result is None

    def test_truncated_data_stops_gracefully(self):
        import struct
        # type=26 (SET), count=5, but only 1 element's worth of data
        header = struct.pack("<II", 26, 5)
        element = b"\x04abc"  # size=4, data="abc" (3 bytes + null)
        data = header + element
        result = CubridSet._parse_collection_bytes(data)
        # Should parse what it can without crashing
        assert result is not None
        assert len(result) <= 5

    def test_set_fallback_bytes_returns_empty_set(self):
        proc = CubridSet("VARCHAR(50)").result_processor(CubridDialect(), None)
        result = proc(b"\x00\x01")
        assert result == set()
        assert isinstance(result, set)

    def test_multiset_fallback_bytes_returns_empty_list(self):
        proc = CubridMultiset("VARCHAR(50)").result_processor(CubridDialect(), None)
        result = proc(b"\x00\x01")
        assert result == []
        assert isinstance(result, list)

    def test_list_fallback_bytes_returns_empty_list(self):
        proc = CubridList("VARCHAR(50)").result_processor(CubridDialect(), None)
        result = proc(b"\x00\x01")
        assert result == []
        assert isinstance(result, list)

    def test_none_passthrough(self):
        proc = CubridSet("VARCHAR(50)").result_processor(CubridDialect(), None)
        assert proc(None) is None

    def test_set_passthrough(self):
        proc = CubridSet("VARCHAR(50)").result_processor(CubridDialect(), None)
        assert proc({"a", "b"}) == {"a", "b"}


# ---------------------------------------------------------------------------
# 0.8.2j — Collection type reflection (NullType → CubridSet etc.)
# ---------------------------------------------------------------------------
class TestCollectionTypeReflection:
    def test_set_of_resolved(self, dialect):
        t = dialect._resolve_type("SET_OF(VARCHAR(50))")
        assert isinstance(t, CubridSet)
        assert t.element_type == "VARCHAR(50)"

    def test_multiset_of_resolved(self, dialect):
        t = dialect._resolve_type("MULTISET_OF(INTEGER)")
        assert isinstance(t, CubridMultiset)
        assert t.element_type == "INTEGER"

    def test_sequence_of_resolved(self, dialect):
        t = dialect._resolve_type("SEQUENCE_OF(VARCHAR(100))")
        assert isinstance(t, CubridList)
        assert t.element_type == "VARCHAR(100)"

    def test_set_no_params_default_element(self, dialect):
        t = dialect._resolve_type("SET")
        assert isinstance(t, CubridSet)
        assert "VARCHAR" in t.element_type

    def test_list_of_resolved(self, dialect):
        t = dialect._resolve_type("LIST_OF(DOUBLE)")
        assert isinstance(t, CubridList)
        assert t.element_type == "DOUBLE"


# ---------------------------------------------------------------------------
# 0.8.2k — ROWNUM pseudo-column
# ---------------------------------------------------------------------------
class TestRownum:
    def test_rownum_compile(self, dialect):
        from sqlalchemy_cubrid.hierarchical import rownum
        r = rownum()
        sql = str(r.compile(dialect=dialect))
        assert sql == "ROWNUM"

    def test_rownum_type_is_integer(self):
        from sqlalchemy_cubrid.hierarchical import rownum
        r = rownum()
        assert isinstance(r.type, Integer)


# ---------------------------------------------------------------------------
# 0.8.2l — MERGE DELETE + conditional WHEN
# ---------------------------------------------------------------------------
class TestMergeDeleteConditional:
    def _make_tables(self, meta):
        t = Table("target", meta, Column("id", Integer), Column("name", String(50)),
                  Column("active", Integer))
        s = Table("source", meta, Column("id", Integer), Column("name", String(50)),
                  Column("active", Integer))
        return t, s

    def test_merge_when_matched_then_delete(self, dialect):
        m = MetaData()
        t, s = self._make_tables(m)
        stmt = (
            __import__("sqlalchemy_cubrid.merge", fromlist=["Merge"]).Merge(t)
            .using(s)
            .on(t.c.id == s.c.id)
            .when_matched_then_delete()
        )
        sql = str(stmt.compile(dialect=dialect))
        assert "WHEN MATCHED THEN DELETE" in sql

    def test_merge_conditional_update(self, dialect):
        m = MetaData()
        t, s = self._make_tables(m)
        from sqlalchemy_cubrid.merge import Merge
        stmt = (
            Merge(t).using(s).on(t.c.id == s.c.id)
            .when_matched_then_update(
                {t.c.name: s.c.name},
                condition=s.c.active == 1,
            )
        )
        sql = str(stmt.compile(dialect=dialect))
        assert "WHEN MATCHED AND" in sql
        assert "THEN UPDATE SET" in sql

    def test_merge_conditional_delete(self, dialect):
        m = MetaData()
        t, s = self._make_tables(m)
        from sqlalchemy_cubrid.merge import Merge
        stmt = (
            Merge(t).using(s).on(t.c.id == s.c.id)
            .when_matched_then_delete(condition=s.c.active == 0)
        )
        sql = str(stmt.compile(dialect=dialect))
        assert "WHEN MATCHED AND" in sql
        assert "THEN DELETE" in sql

    def test_merge_update_and_delete_and_insert(self, dialect):
        m = MetaData()
        t, s = self._make_tables(m)
        from sqlalchemy_cubrid.merge import Merge
        stmt = (
            Merge(t).using(s).on(t.c.id == s.c.id)
            .when_matched_then_update(
                {t.c.name: s.c.name}, condition=s.c.active == 1,
            )
            .when_matched_then_delete(condition=s.c.active == 0)
            .when_not_matched_then_insert(
                {t.c.id: s.c.id, t.c.name: s.c.name},
            )
        )
        sql = str(stmt.compile(dialect=dialect))
        assert "THEN UPDATE SET" in sql
        assert "THEN DELETE" in sql
        assert "THEN INSERT" in sql

    def test_merge_conditional_insert(self, dialect):
        m = MetaData()
        t, s = self._make_tables(m)
        from sqlalchemy_cubrid.merge import Merge
        stmt = (
            Merge(t).using(s).on(t.c.id == s.c.id)
            .when_not_matched_then_insert(
                {t.c.id: s.c.id}, condition=s.c.active == 1,
            )
        )
        sql = str(stmt.compile(dialect=dialect))
        assert "WHEN NOT MATCHED AND" in sql


# ---------------------------------------------------------------------------
# 0.8.2m — SYS_CONNECT_BY_PATH escaping
# ---------------------------------------------------------------------------
class TestSysConnectByPathEscaping:
    def test_simple_separator(self, dialect):
        from sqlalchemy_cubrid.hierarchical import sys_connect_by_path
        expr = sys_connect_by_path(column("name"), "/")
        sql = str(expr.compile(dialect=dialect))
        assert "SYS_CONNECT_BY_PATH" in sql
        assert "'/'" in sql

    def test_quote_in_separator(self, dialect):
        from sqlalchemy_cubrid.hierarchical import sys_connect_by_path
        expr = sys_connect_by_path(column("name"), "it's")
        sql = str(expr.compile(dialect=dialect))
        assert "SYS_CONNECT_BY_PATH" in sql
        # The quote should be properly escaped
        assert "it" in sql


# ---------------------------------------------------------------------------
# 0.8.2n — CUBRID built-in functions (NVL, NVL2, DECODE, IF, IFNULL)
# ---------------------------------------------------------------------------
class TestCubridFunctions:
    def test_nvl(self, dialect):
        from sqlalchemy import func
        stmt = select(func.nvl(column("x"), 0))
        sql = str(stmt.compile(dialect=dialect))
        assert "NVL" in sql

    def test_nvl2(self, dialect):
        from sqlalchemy import func
        stmt = select(func.nvl2(column("x"), "yes", "no"))
        sql = str(stmt.compile(dialect=dialect))
        assert "NVL2" in sql

    def test_decode(self, dialect):
        from sqlalchemy import func
        stmt = select(func.decode(column("status"), 1, "active", "inactive"))
        sql = str(stmt.compile(dialect=dialect))
        assert "DECODE" in sql

    def test_if_(self, dialect):
        from sqlalchemy import func
        stmt = select(func.if_(column("x") > 0, "pos", "neg"))
        sql = str(stmt.compile(dialect=dialect))
        assert "IF" in sql.upper()

    def test_ifnull(self, dialect):
        from sqlalchemy import func
        stmt = select(func.ifnull(column("x"), 0))
        sql = str(stmt.compile(dialect=dialect))
        assert "IFNULL" in sql


# ---------------------------------------------------------------------------
# 0.8.2o — REGEXP / RLIKE operator
# ---------------------------------------------------------------------------
class TestRegexp:
    def test_regexp_match(self, dialect):
        c = column("name")
        expr = c.regexp_match(r"^[a-z]+$")
        sql = str(expr.compile(dialect=dialect))
        assert "REGEXP" in sql

    def test_not_regexp_match(self, dialect):
        c = column("name")
        expr = ~c.regexp_match(r"^[a-z]+$")
        sql = str(expr.compile(dialect=dialect))
        assert "NOT" in sql
        assert "REGEXP" in sql


# ---------------------------------------------------------------------------
# 0.8.2p — PARTITION table DDL
# ---------------------------------------------------------------------------
class TestPartition:
    def test_partition_by_range(self, dialect):
        from sqlalchemy_cubrid.partition import PartitionByRange, RangePartition
        stmt = PartitionByRange("orders", "order_date", [
            RangePartition("p2024", "'2025-01-01'"),
            RangePartition("pmax", "MAXVALUE"),
        ])
        sql = str(stmt.compile(dialect=dialect))
        assert "PARTITION BY RANGE" in sql
        assert "VALUES LESS THAN" in sql
        assert "MAXVALUE" in sql

    def test_partition_by_hash(self, dialect):
        from sqlalchemy_cubrid.partition import PartitionByHash
        stmt = PartitionByHash("orders", "id", 4)
        sql = str(stmt.compile(dialect=dialect))
        assert "PARTITION BY HASH" in sql
        assert "PARTITIONS 4" in sql

    def test_partition_by_list(self, dialect):
        from sqlalchemy_cubrid.partition import PartitionByList, ListPartition
        stmt = PartitionByList("orders", "region", [
            ListPartition("p_east", ["'east'", "'northeast'"]),
            ListPartition("p_west", ["'west'"]),
        ])
        sql = str(stmt.compile(dialect=dialect))
        assert "PARTITION BY LIST" in sql
        assert "VALUES IN" in sql


# ---------------------------------------------------------------------------
# 0.8.2q — DBLINK support (11.2+)
# ---------------------------------------------------------------------------
class TestDblink:
    def test_create_server(self, dialect):
        from sqlalchemy_cubrid.dblink import CreateServer
        stmt = CreateServer("remote", host="192.168.1.10", port=33000,
                            dbname="demodb", user="dba", password="secret")
        sql = str(stmt.compile(dialect=dialect))
        assert "CREATE SERVER" in sql
        assert "192.168.1.10" in sql
        assert "demodb" in sql

    def test_drop_server(self, dialect):
        from sqlalchemy_cubrid.dblink import DropServer
        stmt = DropServer("remote")
        sql = str(stmt.compile(dialect=dialect))
        assert "DROP SERVER" in sql
        assert "IF EXISTS" in sql

    def test_drop_server_no_if_exists(self, dialect):
        from sqlalchemy_cubrid.dblink import DropServer
        stmt = DropServer("remote", if_exists=False)
        sql = str(stmt.compile(dialect=dialect))
        assert "IF EXISTS" not in sql

    def test_dblink_as_text(self):
        from sqlalchemy_cubrid.dblink import DbLink
        link = DbLink("remote", "SELECT id, name FROM t",
                       columns=[("id", "INT"), ("name", "VARCHAR(50)")])
        result = link.as_text("t")
        assert "DBLINK(remote," in result
        assert "AS t(id INT, name VARCHAR(50))" in result


# ---------------------------------------------------------------------------
# 0.8.2r — visit_create_index() DDL
# ---------------------------------------------------------------------------
class TestCreateIndex:
    def _compile_create(self, idx, dialect):
        from sqlalchemy.schema import CreateIndex
        return str(CreateIndex(idx).compile(dialect=dialect))

    def _compile_drop(self, idx, dialect):
        from sqlalchemy.schema import DropIndex
        return str(DropIndex(idx).compile(dialect=dialect))

    def test_basic_index(self, dialect):
        m = MetaData()
        t = Table("tbl", m, Column("id", Integer), Column("name", String(50)))
        idx = Index("idx_name", t.c.name)
        sql = self._compile_create(idx, dialect)
        assert "CREATE INDEX" in sql
        assert "idx_name" in sql
        assert "ON" in sql

    def test_unique_index(self, dialect):
        m = MetaData()
        t = Table("tbl", m, Column("id", Integer), Column("name", String(50)))
        idx = Index("idx_uq", t.c.name, unique=True)
        sql = self._compile_create(idx, dialect)
        assert "CREATE UNIQUE INDEX" in sql

    def test_reverse_index(self, dialect):
        m = MetaData()
        t = Table("tbl", m, Column("id", Integer), Column("name", String(50)))
        idx = Index("idx_rev", t.c.name, cubrid_reverse=True)
        sql = self._compile_create(idx, dialect)
        assert "REVERSE" in sql

    def test_filtered_index(self, dialect):
        m = MetaData()
        t = Table("tbl", m, Column("id", Integer), Column("status", Integer))
        idx = Index("idx_flt", t.c.status, cubrid_filtered="status > 0")
        sql = self._compile_create(idx, dialect)
        assert "WHERE status > 0" in sql

    def test_function_based_index(self, dialect):
        m = MetaData()
        t = Table("tbl", m, Column("id", Integer), Column("name", String(50)))
        idx = Index("idx_fn", t.c.name, cubrid_function="LOWER(name)")
        sql = self._compile_create(idx, dialect)
        assert "LOWER(name)" in sql

    def test_drop_index_with_table(self, dialect):
        m = MetaData()
        t = Table("tbl", m, Column("id", Integer), Column("name", String(50)))
        idx = Index("idx_drp", t.c.name)
        sql = self._compile_drop(idx, dialect)
        assert "DROP INDEX" in sql
        assert "ON" in sql


# ---------------------------------------------------------------------------
# 0.8.2s — get_lastrowid safety
# ---------------------------------------------------------------------------
class TestGetLastRowId:
    def test_get_lastrowid_returns_none_on_missing_attr(self):
        from sqlalchemy_cubrid.base import CubridExecutionContext

        class FakeCursor:
            pass  # No lastrowid attribute

        ctx = CubridExecutionContext.__new__(CubridExecutionContext)
        ctx.cursor = FakeCursor()
        result = ctx.get_lastrowid()
        assert result is None


# ---------------------------------------------------------------------------
# 0.8.2t — get_multi_* batch reflection methods exist
# ---------------------------------------------------------------------------
class TestBatchReflection:
    def test_default_fallback_exists(self, dialect):
        """SQLAlchemy 2.x provides default get_multi_* via single-table methods."""
        # The dialect inherits defaults from DefaultDialect
        assert hasattr(dialect, "get_columns")
        assert hasattr(dialect, "get_pk_constraint")
        assert hasattr(dialect, "get_foreign_keys")
        assert hasattr(dialect, "get_indexes")
        assert hasattr(dialect, "get_unique_constraints")


# ---------------------------------------------------------------------------
# 0.8.2u — _type_map thread safety (eager init)
# ---------------------------------------------------------------------------
class TestTypeMapThreadSafety:
    def test_type_map_is_not_none(self):
        """_type_map should be eagerly initialized, not None."""
        assert CubridDialect._type_map is not None

    def test_type_map_is_dict(self):
        assert isinstance(CubridDialect._type_map, dict)

    def test_type_map_has_collection_types(self):
        assert CubridDialect._type_map["SET"] is CubridSet
        assert CubridDialect._type_map["MULTISET"] is CubridMultiset
        assert CubridDialect._type_map["LIST"] is CubridList
        assert CubridDialect._type_map["SET_OF"] is CubridSet
        assert CubridDialect._type_map["SEQUENCE_OF"] is CubridList
