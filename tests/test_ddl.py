"""DDL and basic type tests for sqlalchemy-cubrid dialect (0.2.0).

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import (
    create_engine,
    inspect,
    text,
    MetaData,
    Table,
    Column,
    Integer,
    BigInteger,
    SmallInteger,
    Float,
    Numeric,
    String,
    Text,
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
        for tbl in ["t_ddl_basic", "t_ddl_types", "t_ddl_autoinc"]:
            conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
        conn.commit()


class TestCreateDropTable:
    def test_create_table(self, engine):
        metadata = MetaData()
        table = Table(
            "t_ddl_basic",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(100)),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        assert insp.has_table("t_ddl_basic")

    def test_drop_table(self, engine):
        metadata = MetaData()
        table = Table(
            "t_ddl_basic",
            metadata,
            Column("id", Integer, primary_key=True),
        )
        metadata.create_all(engine)
        assert inspect(engine).has_table("t_ddl_basic")

        metadata.drop_all(engine)
        # Need a fresh inspector after DDL changes
        insp = inspect(engine)
        insp.clear_cache()
        assert not insp.has_table("t_ddl_basic")


class TestTypeCompilation:
    def test_integer_types(self, engine):
        metadata = MetaData()
        Table(
            "t_ddl_types",
            metadata,
            Column("col_int", Integer, primary_key=True),
            Column("col_bigint", BigInteger),
            Column("col_smallint", SmallInteger),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        columns = insp.get_columns("t_ddl_types")
        col_map = {c["name"]: c for c in columns}
        assert col_map["col_int"] is not None
        assert col_map["col_bigint"] is not None
        assert col_map["col_smallint"] is not None

    def test_float_numeric_types(self, engine):
        metadata = MetaData()
        Table(
            "t_ddl_types",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("col_float", Float),
            Column("col_numeric", Numeric(10, 2)),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        columns = insp.get_columns("t_ddl_types")
        col_map = {c["name"]: c for c in columns}
        assert col_map["col_float"] is not None
        assert col_map["col_numeric"] is not None

    def test_string_types(self, engine):
        metadata = MetaData()
        Table(
            "t_ddl_types",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("col_varchar", String(200)),
            Column("col_text", Text),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        columns = insp.get_columns("t_ddl_types")
        col_map = {c["name"]: c for c in columns}
        assert col_map["col_varchar"] is not None
        assert col_map["col_text"] is not None


class TestAutoIncrement:
    def test_autoincrement_column(self, engine):
        metadata = MetaData()
        Table(
            "t_ddl_autoinc",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("name", String(50)),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        columns = insp.get_columns("t_ddl_autoinc")
        col_map = {c["name"]: c for c in columns}
        assert col_map["id"]["autoincrement"] is True

    def test_autoincrement_insert(self, engine):
        metadata = MetaData()
        table = Table(
            "t_ddl_autoinc",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("name", String(50)),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(table.insert().values(name="alice"))
            conn.execute(table.insert().values(name="bob"))
            conn.commit()

            result = conn.execute(text("SELECT id, name FROM t_ddl_autoinc ORDER BY id"))
            rows = result.fetchall()
            assert len(rows) == 2
            assert rows[0][0] < rows[1][0]
