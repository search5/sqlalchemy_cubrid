"""Alembic integration and query trace tests for 0.6.6 features.

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import create_engine, text

import os
CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


# ---- Alembic integration tests ----

class TestAlembicImpl:
    def test_import(self):
        from sqlalchemy_cubrid.alembic_impl import CubridImpl
        assert CubridImpl.__dialect__ == "cubrid"

    def test_transactional_ddl_false(self):
        from sqlalchemy_cubrid.alembic_impl import CubridImpl
        assert CubridImpl.transactional_ddl is False

    def test_render_type_cubrid_set(self):
        from sqlalchemy_cubrid.alembic_impl import CubridImpl
        from sqlalchemy_cubrid.types import CubridSet
        from unittest.mock import MagicMock

        impl = MagicMock(spec=CubridImpl)
        impl.render_type = CubridImpl.render_type.__get__(impl)

        ctx = MagicMock()
        ctx.imports = set()

        type_obj = CubridSet("INTEGER")
        result = impl.render_type(type_obj, ctx)
        assert result == "CubridSet('INTEGER')"
        assert any("CubridSet" in imp for imp in ctx.imports)

    def test_render_type_cubrid_multiset(self):
        from sqlalchemy_cubrid.alembic_impl import CubridImpl
        from sqlalchemy_cubrid.types import CubridMultiset
        from unittest.mock import MagicMock

        impl = MagicMock(spec=CubridImpl)
        impl.render_type = CubridImpl.render_type.__get__(impl)

        ctx = MagicMock()
        ctx.imports = set()

        type_obj = CubridMultiset("VARCHAR(100)")
        result = impl.render_type(type_obj, ctx)
        assert result == "CubridMultiset('VARCHAR(100)')"

    def test_render_type_cubrid_list(self):
        from sqlalchemy_cubrid.alembic_impl import CubridImpl
        from sqlalchemy_cubrid.types import CubridList
        from unittest.mock import MagicMock

        impl = MagicMock(spec=CubridImpl)
        impl.render_type = CubridImpl.render_type.__get__(impl)

        ctx = MagicMock()
        ctx.imports = set()

        type_obj = CubridList("VARCHAR(50)")
        result = impl.render_type(type_obj, ctx)
        assert result == "CubridList('VARCHAR(50)')"

    def test_render_type_standard_returns_false(self):
        from sqlalchemy_cubrid.alembic_impl import CubridImpl
        from sqlalchemy import Integer
        from unittest.mock import MagicMock

        impl = MagicMock(spec=CubridImpl)
        impl.render_type = CubridImpl.render_type.__get__(impl)

        ctx = MagicMock()
        ctx.imports = set()

        result = impl.render_type(Integer(), ctx)
        assert result is False

    def test_compare_type_same_collection(self):
        from sqlalchemy_cubrid.alembic_impl import CubridImpl
        from sqlalchemy_cubrid.types import CubridSet
        from unittest.mock import MagicMock

        impl = CubridImpl.__new__(CubridImpl)

        insp_col = MagicMock()
        insp_col.type = CubridSet("INTEGER")
        meta_col = MagicMock()
        meta_col.type = CubridSet("integer")  # case-insensitive

        result = impl.compare_type(insp_col, meta_col)
        assert result is False  # Same type

    def test_compare_type_different_collection(self):
        from sqlalchemy_cubrid.alembic_impl import CubridImpl
        from sqlalchemy_cubrid.types import CubridSet, CubridMultiset
        from unittest.mock import MagicMock

        impl = CubridImpl.__new__(CubridImpl)

        insp_col = MagicMock()
        insp_col.type = CubridSet("INTEGER")
        meta_col = MagicMock()
        meta_col.type = CubridMultiset("INTEGER")

        result = impl.compare_type(insp_col, meta_col)
        assert result is True  # Different kind

    def test_compare_type_different_element(self):
        from sqlalchemy_cubrid.alembic_impl import CubridImpl
        from sqlalchemy_cubrid.types import CubridSet
        from unittest.mock import MagicMock

        impl = CubridImpl.__new__(CubridImpl)

        insp_col = MagicMock()
        insp_col.type = CubridSet("INTEGER")
        meta_col = MagicMock()
        meta_col.type = CubridSet("VARCHAR(100)")

        result = impl.compare_type(insp_col, meta_col)
        assert result is True  # Different element type


# ---- Alembic migration basic test ----

class TestAlembicMigration:
    def test_alembic_ops_create_table(self):
        """Alembic operations context can create a table via CUBRID."""
        from alembic.operations import ops
        from alembic.migration import MigrationContext
        from sqlalchemy import Column, Integer, String

        engine = create_engine(CUBRID_URL)
        try:
            with engine.connect() as conn:
                conn.execute(text("DROP TABLE IF EXISTS alembic_test"))
                conn.commit()

            with engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                op = ops.CreateTableOp(
                    "alembic_test",
                    [
                        Column("id", Integer, primary_key=True),
                        Column("name", String(50)),
                    ],
                )
                ctx.impl.create_table(op.to_table())
                conn.commit()

            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM db_class "
                        "WHERE class_name = 'alembic_test'"
                    )
                )
                assert result.scalar() == 1

            with engine.connect() as conn:
                conn.execute(text("DROP TABLE IF EXISTS alembic_test"))
                conn.commit()
        finally:
            engine.dispose()


# ---- Query trace tests ----

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def trace_table(engine):
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_trace"))
        conn.execute(text(
            "CREATE TABLE test_trace ("
            "  id INTEGER AUTO_INCREMENT PRIMARY KEY,"
            "  name VARCHAR(50)"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO test_trace (name) VALUES ('alice'), ('bob'), ('carol')"
        ))
        conn.commit()
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_trace"))
        conn.commit()


class TestTraceQuery:
    def test_trace_query_text_output(self, engine, trace_table):
        from sqlalchemy_cubrid.trace import trace_query

        with engine.connect() as conn:
            result, trace_output = trace_query(
                conn,
                "SELECT /*+ RECOMPILE */ * FROM test_trace WHERE id = :id",
                {"id": 1},
                output="TEXT",
            )
            row = result.fetchone()
            assert row is not None
            assert row.name == "alice"
            assert isinstance(trace_output, str)
            assert len(trace_output) > 0

    def test_trace_query_json_output(self, engine, trace_table):
        from sqlalchemy_cubrid.trace import trace_query
        import json

        with engine.connect() as conn:
            result, trace_output = trace_query(
                conn,
                "SELECT /*+ RECOMPILE */ * FROM test_trace",
                output="JSON",
            )
            rows = result.fetchall()
            assert len(rows) == 3
            # JSON output should be parseable
            parsed = json.loads(trace_output)
            assert isinstance(parsed, dict)

    def test_trace_query_invalid_output(self, engine, trace_table):
        from sqlalchemy_cubrid.trace import trace_query

        with engine.connect() as conn:
            with pytest.raises(ValueError, match="output must be"):
                trace_query(conn, "SELECT 1", output="XML")


class TestQueryTracer:
    def test_tracer_context_manager(self, engine, trace_table):
        from sqlalchemy_cubrid.trace import QueryTracer

        with engine.connect() as conn:
            with QueryTracer(conn, output="TEXT") as tracer:
                conn.execute(text(
                    "SELECT /*+ RECOMPILE */ * FROM test_trace"
                ))
            trace_output = tracer.stop()
            # After stop, should return empty (already stopped)
            assert trace_output == ""

    def test_tracer_manual_start_stop(self, engine, trace_table):
        from sqlalchemy_cubrid.trace import QueryTracer

        with engine.connect() as conn:
            tracer = QueryTracer(conn, output="TEXT")
            tracer.start()
            conn.execute(text(
                "SELECT /*+ RECOMPILE */ * FROM test_trace WHERE id > :id"
            ), {"id": 0})
            trace_output = tracer.stop()
            assert isinstance(trace_output, str)
            assert len(trace_output) > 0

    def test_tracer_json_output(self, engine, trace_table):
        from sqlalchemy_cubrid.trace import QueryTracer
        import json

        with engine.connect() as conn:
            tracer = QueryTracer(conn, output="JSON")
            tracer.start()
            conn.execute(text(
                "SELECT /*+ RECOMPILE */ * FROM test_trace"
            ))
            trace_output = tracer.stop()
            parsed = json.loads(trace_output)
            assert isinstance(parsed, dict)

    def test_tracer_invalid_output(self):
        from sqlalchemy_cubrid.trace import QueryTracer
        with pytest.raises(ValueError, match="output must be"):
            QueryTracer(None, output="XML")
