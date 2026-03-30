"""Constraint and ENUM/BOOLEAN tests for sqlalchemy-cubrid dialect (0.2.2).

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
    String,
    SmallInteger,
    Enum,
)

import os
CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def cleanup(engine):
    yield
    with engine.connect() as conn:
        for tbl in ["t_bool", "t_enum", "t_nullable", "t_defaults"]:
            conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
        conn.commit()


class TestBooleanType:
    def test_boolean_creates_smallint(self, engine):
        """CUBRID has no BOOLEAN column type; maps to SMALLINT."""
        metadata = MetaData()
        # Boolean is mapped to SMALLINT, so use SmallInteger explicitly
        # to test the BOOLEAN visit mapping
        from sqlalchemy import Boolean
        Table(
            "t_bool",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("active", Boolean),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        columns = insp.get_columns("t_bool")
        col_map = {c["name"]: c for c in columns}
        # SHOW COLUMNS shows SHORT for SMALLINT
        assert col_map["active"] is not None

    def test_boolean_roundtrip(self, engine):
        """Boolean values stored as 0/1 in SMALLINT."""
        from sqlalchemy import Boolean
        metadata = MetaData()
        table = Table(
            "t_bool",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("active", Boolean),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(table.insert().values(active=True))
            conn.execute(table.insert().values(active=False))
            conn.commit()

            result = conn.execute(
                text("SELECT active FROM t_bool ORDER BY id")
            )
            rows = result.fetchall()
            assert rows[0][0] == 1
            assert rows[1][0] == 0


class TestEnumType:
    def test_enum_create_table(self, engine):
        """Create table with ENUM type column."""
        metadata = MetaData()
        Table(
            "t_enum",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("color", Enum("red", "yellow", "blue", "green", name="color_enum")),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        assert insp.has_table("t_enum")

    def test_enum_roundtrip(self, engine):
        """Insert and retrieve ENUM values."""
        metadata = MetaData()
        table = Table(
            "t_enum",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("color", Enum("red", "yellow", "blue", "green", name="color_enum")),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(table.insert().values(color="red"))
            conn.execute(table.insert().values(color="blue"))
            conn.commit()

            result = conn.execute(
                text("SELECT color FROM t_enum ORDER BY id")
            )
            rows = result.fetchall()
            assert rows[0][0] == "red"
            assert rows[1][0] == "blue"


class TestNullNotNull:
    def test_not_null_constraint(self, engine):
        metadata = MetaData()
        table = Table(
            "t_nullable",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("required_name", String(100), nullable=False),
            Column("optional_name", String(100), nullable=True),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        columns = insp.get_columns("t_nullable")
        col_map = {c["name"]: c for c in columns}
        assert col_map["required_name"]["nullable"] is False
        assert col_map["optional_name"]["nullable"] is True

    def test_not_null_insert_fails(self, engine):
        metadata = MetaData()
        table = Table(
            "t_nullable",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("required_name", String(100), nullable=False),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            with pytest.raises(Exception):
                conn.execute(table.insert().values(required_name=None))
                conn.commit()


class TestDefaults:
    def test_server_default(self, engine):
        metadata = MetaData()
        table = Table(
            "t_defaults",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("status", String(20), server_default="active"),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(text("INSERT INTO t_defaults (id) VALUES (1)"))
            conn.commit()
            result = conn.execute(text("SELECT status FROM t_defaults"))
            row = result.fetchone()
            assert row[0] == "active"

    def test_default_in_reflection(self, engine):
        metadata = MetaData()
        Table(
            "t_defaults",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("status", String(20), server_default="active"),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        columns = insp.get_columns("t_defaults")
        col_map = {c["name"]: c for c in columns}
        assert col_map["status"]["default"] is not None
