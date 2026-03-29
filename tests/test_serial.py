"""SERIAL (sequence) tests for sqlalchemy-cubrid dialect (0.4.1).

CUBRID uses SERIAL instead of standard SQL SEQUENCE.
Syntax: CREATE SERIAL, serial_name.NEXT_VALUE, serial_name.CURRENT_VALUE

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
    Sequence,
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
        conn.execute(text("DROP SERIAL IF EXISTS test_serial"))
        conn.execute(text("DROP SERIAL IF EXISTS user_id_seq"))
        conn.execute(text("DROP SERIAL IF EXISTS custom_serial"))
        conn.execute(text("DROP TABLE IF EXISTS t_serial_test"))
        conn.commit()


class TestSerialDDLRaw:
    """Test CUBRID SERIAL with raw SQL to verify baseline behavior."""

    def test_create_serial_basic(self, engine):
        """CREATE SERIAL with default options."""
        with engine.connect() as conn:
            conn.execute(text("CREATE SERIAL test_serial"))
            conn.commit()

            result = conn.execute(text(
                "SELECT name FROM db_serial WHERE name = 'test_serial'"
            ))
            row = result.fetchone()
            assert row is not None
            assert row[0] == "test_serial"

    def test_create_serial_with_options(self, engine):
        """CREATE SERIAL with START WITH, INCREMENT BY, CYCLE, CACHE."""
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE SERIAL test_serial "
                "START WITH 100 "
                "INCREMENT BY 5 "
                "MINVALUE 1 "
                "MAXVALUE 10000 "
                "CYCLE "
                "CACHE 10"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT increment_val, min_val, max_val, cyclic, cached_num "
                "FROM db_serial WHERE name = 'test_serial'"
            ))
            row = result.fetchone()
            assert row is not None
            assert int(row[0]) == 5       # increment_val
            assert int(row[1]) == 1       # min_val
            assert int(row[2]) == 10000   # max_val
            assert int(row[3]) == 1       # cyclic (1 = CYCLE)
            assert int(row[4]) == 10      # cached_num

    def test_serial_next_value(self, engine):
        """serial_name.NEXT_VALUE advances and returns value."""
        with engine.connect() as conn:
            conn.execute(text("CREATE SERIAL test_serial START WITH 1"))
            conn.commit()

            result = conn.execute(text("SELECT test_serial.NEXT_VALUE"))
            assert result.scalar() == 1

            result = conn.execute(text("SELECT test_serial.NEXT_VALUE"))
            assert result.scalar() == 2

    def test_serial_current_value(self, engine):
        """serial_name.CURRENT_VALUE returns current without advancing."""
        with engine.connect() as conn:
            conn.execute(text("CREATE SERIAL test_serial START WITH 1"))
            conn.commit()

            conn.execute(text("SELECT test_serial.NEXT_VALUE"))
            result = conn.execute(text("SELECT test_serial.CURRENT_VALUE"))
            val1 = result.scalar()

            result = conn.execute(text("SELECT test_serial.CURRENT_VALUE"))
            val2 = result.scalar()

            assert val1 == val2  # CURRENT_VALUE does not advance

    def test_drop_serial(self, engine):
        """DROP SERIAL removes the serial."""
        with engine.connect() as conn:
            conn.execute(text("CREATE SERIAL test_serial"))
            conn.commit()
            conn.execute(text("DROP SERIAL test_serial"))
            conn.commit()

            result = conn.execute(text(
                "SELECT COUNT(*) FROM db_serial WHERE name = 'test_serial'"
            ))
            assert result.scalar() == 0

    def test_drop_serial_if_exists(self, engine):
        """DROP SERIAL IF EXISTS does not error on missing serial."""
        with engine.connect() as conn:
            conn.execute(text("DROP SERIAL IF EXISTS nonexistent_serial"))
            conn.commit()


class TestSerialSQLAlchemy:
    """Test SERIAL via SQLAlchemy Sequence API."""

    def test_create_sequence_generates_create_serial(self, engine):
        """SQLAlchemy Sequence should generate CREATE SERIAL DDL."""
        seq = Sequence("test_serial")
        seq.create(engine)

        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM db_serial WHERE name = 'test_serial'"
            ))
            assert result.fetchone() is not None

    def test_drop_sequence_generates_drop_serial(self, engine):
        """SQLAlchemy Sequence.drop() should generate DROP SERIAL DDL."""
        seq = Sequence("test_serial")
        seq.create(engine)
        seq.drop(engine)

        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM db_serial WHERE name = 'test_serial'"
            ))
            assert result.scalar() == 0

    def test_sequence_with_options(self, engine):
        """Sequence with start/increment/min/max/cycle/cache."""
        seq = Sequence(
            "test_serial",
            start=100,
            increment=5,
            minvalue=1,
            maxvalue=10000,
            cycle=True,
            cache=10,
        )
        seq.create(engine)

        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT increment_val, min_val, max_val, cyclic, cached_num "
                "FROM db_serial WHERE name = 'test_serial'"
            ))
            row = result.fetchone()
            assert int(row[0]) == 5
            assert int(row[1]) == 1
            assert int(row[2]) == 10000
            assert int(row[3]) == 1
            assert int(row[4]) == 10

    def test_sequence_next_value(self, engine):
        """Sequence.next_value() generates serial_name.NEXT_VALUE."""
        seq = Sequence("test_serial", start=1)
        seq.create(engine)

        with engine.connect() as conn:
            val = conn.execute(seq.next_value()).scalar()
            assert val == 1

            val = conn.execute(seq.next_value()).scalar()
            assert val == 2

    def test_sequence_as_column_default(self, engine):
        """Sequence used as Column default for auto-generating IDs."""
        seq = Sequence("user_id_seq", start=1000)
        metadata = MetaData()
        t = Table(
            "t_serial_test",
            metadata,
            Column("id", Integer, seq, primary_key=True),
            Column("name", String(50)),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(t.insert().values(name="alice"))
            conn.execute(t.insert().values(name="bob"))
            conn.commit()

            result = conn.execute(
                t.select().order_by(t.c.id)
            )
            rows = result.fetchall()
            assert rows[0].id == 1000
            assert rows[1].id == 1001
            assert rows[0].name == "alice"


class TestSerialIntrospection:
    """Test SERIAL introspection via SQLAlchemy Inspector."""

    def test_get_sequence_names(self, engine):
        """Inspector.get_sequence_names() lists serials from db_serial."""
        with engine.connect() as conn:
            conn.execute(text("CREATE SERIAL test_serial"))
            conn.execute(text("CREATE SERIAL custom_serial"))
            conn.commit()

        insp = inspect(engine)
        names = insp.get_sequence_names()
        assert "test_serial" in names
        assert "custom_serial" in names

    def test_has_sequence(self, engine):
        """Inspector.has_sequence() checks serial existence."""
        with engine.connect() as conn:
            conn.execute(text("CREATE SERIAL test_serial"))
            conn.commit()

        insp = inspect(engine)
        assert insp.has_sequence("test_serial") is True
        assert insp.has_sequence("nonexistent_serial") is False
