"""Type round-trip tests for sqlalchemy-cubrid dialect (0.2.1).

Tests DATE, TIME, DATETIME, TIMESTAMP, BLOB, CLOB, BIT types.

Requires a running CUBRID instance:
    docker compose up -d
"""

import datetime
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
    Date,
    Time,
    DateTime,
    LargeBinary,
)
from sqlalchemy.types import TIMESTAMP, BLOB, CLOB

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
        for tbl in ["t_datetime", "t_lob", "t_bit"]:
            conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
        conn.commit()


class TestDateTimeTypes:
    def test_create_table_with_datetime_types(self, engine):
        metadata = MetaData()
        Table(
            "t_datetime",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("col_date", Date),
            Column("col_time", Time),
            Column("col_datetime", DateTime),
            Column("col_timestamp", TIMESTAMP),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        assert insp.has_table("t_datetime")
        columns = insp.get_columns("t_datetime")
        col_map = {c["name"]: c for c in columns}
        assert col_map["col_date"] is not None
        assert col_map["col_time"] is not None
        assert col_map["col_datetime"] is not None
        assert col_map["col_timestamp"] is not None

    def test_date_roundtrip(self, engine):
        metadata = MetaData()
        table = Table(
            "t_datetime",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("col_date", Date),
            Column("col_time", Time),
            Column("col_datetime", DateTime),
            Column("col_timestamp", TIMESTAMP),
        )
        metadata.create_all(engine)

        test_date = datetime.date(2026, 3, 27)
        test_time = datetime.time(14, 30, 45)
        test_datetime = datetime.datetime(2026, 3, 27, 14, 30, 45)

        with engine.connect() as conn:
            conn.execute(table.insert().values(
                col_date=test_date,
                col_time=test_time,
                col_datetime=test_datetime,
                col_timestamp=test_datetime,
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT col_date, col_time, col_datetime, col_timestamp FROM t_datetime"
            ))
            row = result.fetchone()
            assert row[0] == test_date
            assert row[1] == test_time


class TestLobTypes:
    def test_create_table_with_lob_types(self, engine):
        metadata = MetaData()
        Table(
            "t_lob",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("col_blob", BLOB),
            Column("col_clob", CLOB),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        assert insp.has_table("t_lob")
        columns = insp.get_columns("t_lob")
        names = [c["name"] for c in columns]
        assert "col_blob" in names
        assert "col_clob" in names


class TestBitTypes:
    def test_create_table_with_bit_types(self, engine):
        """BIT columns via LargeBinary type."""
        metadata = MetaData()
        Table(
            "t_bit",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("col_bin", LargeBinary),
        )
        metadata.create_all(engine)

        insp = inspect(engine)
        assert insp.has_table("t_bit")
        columns = insp.get_columns("t_bit")
        names = [c["name"] for c in columns]
        assert "col_bin" in names
