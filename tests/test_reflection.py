"""Schema reflection tests for sqlalchemy-cubrid dialect (0.1.2).

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import create_engine, inspect, text

CUBRID_URL = "cubrid://dba:@localhost:33000/testdb"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module", autouse=True)
def setup_tables(engine):
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_child"))
        conn.execute(text("DROP TABLE IF EXISTS t_parent"))
        conn.execute(text("""
            CREATE TABLE t_parent (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(200) DEFAULT 'none',
                score DOUBLE,
                created_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE t_child (
                id INT AUTO_INCREMENT PRIMARY KEY,
                parent_id INT NOT NULL,
                label VARCHAR(50),
                FOREIGN KEY (parent_id) REFERENCES t_parent(id)
            )
        """))
        conn.execute(text("CREATE INDEX idx_name ON t_parent(name)"))
        conn.execute(text("CREATE UNIQUE INDEX idx_email ON t_parent(email)"))
        conn.commit()
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_child"))
        conn.execute(text("DROP TABLE IF EXISTS t_parent"))
        conn.commit()


class TestGetColumns:
    def test_returns_list(self, engine):
        insp = inspect(engine)
        columns = insp.get_columns("t_parent")
        assert isinstance(columns, list)
        assert len(columns) == 5

    def test_column_names(self, engine):
        insp = inspect(engine)
        columns = insp.get_columns("t_parent")
        names = [c["name"] for c in columns]
        assert names == ["id", "name", "email", "score", "created_at"]

    def test_column_types(self, engine):
        insp = inspect(engine)
        columns = insp.get_columns("t_parent")
        type_names = [type(c["type"]).__name__ for c in columns]
        assert "INTEGER" in type_names[0]
        assert "VARCHAR" in type_names[1]

    def test_nullable(self, engine):
        insp = inspect(engine)
        columns = insp.get_columns("t_parent")
        col_map = {c["name"]: c for c in columns}
        assert col_map["id"]["nullable"] is False
        assert col_map["name"]["nullable"] is False
        assert col_map["score"]["nullable"] is True

    def test_default(self, engine):
        insp = inspect(engine)
        columns = insp.get_columns("t_parent")
        col_map = {c["name"]: c for c in columns}
        assert col_map["email"]["default"] == "none"

    def test_autoincrement(self, engine):
        insp = inspect(engine)
        columns = insp.get_columns("t_parent")
        col_map = {c["name"]: c for c in columns}
        assert col_map["id"]["autoincrement"] is True
        assert col_map["name"].get("autoincrement", False) is False


class TestGetPKConstraint:
    def test_returns_dict(self, engine):
        insp = inspect(engine)
        pk = insp.get_pk_constraint("t_parent")
        assert isinstance(pk, dict)
        assert "constrained_columns" in pk

    def test_pk_columns(self, engine):
        insp = inspect(engine)
        pk = insp.get_pk_constraint("t_parent")
        assert pk["constrained_columns"] == ["id"]

    def test_pk_name(self, engine):
        insp = inspect(engine)
        pk = insp.get_pk_constraint("t_parent")
        assert pk["name"] is not None


class TestGetForeignKeys:
    def test_returns_list(self, engine):
        insp = inspect(engine)
        fks = insp.get_foreign_keys("t_child")
        assert isinstance(fks, list)
        assert len(fks) == 1

    def test_fk_columns(self, engine):
        insp = inspect(engine)
        fks = insp.get_foreign_keys("t_child")
        fk = fks[0]
        assert fk["constrained_columns"] == ["parent_id"]
        assert fk["referred_table"] == "t_parent"
        assert fk["referred_columns"] == ["id"]

    def test_no_fk(self, engine):
        insp = inspect(engine)
        fks = insp.get_foreign_keys("t_parent")
        assert fks == []


class TestGetIndexes:
    def test_returns_list(self, engine):
        insp = inspect(engine)
        indexes = insp.get_indexes("t_parent")
        assert isinstance(indexes, list)

    def test_index_names(self, engine):
        insp = inspect(engine)
        indexes = insp.get_indexes("t_parent")
        names = {idx["name"] for idx in indexes}
        assert "idx_name" in names
        assert "idx_email" in names

    def test_unique_flag(self, engine):
        insp = inspect(engine)
        indexes = insp.get_indexes("t_parent")
        idx_map = {idx["name"]: idx for idx in indexes}
        assert idx_map["idx_name"]["unique"] is False
        assert idx_map["idx_email"]["unique"] is True

    def test_index_columns(self, engine):
        insp = inspect(engine)
        indexes = insp.get_indexes("t_parent")
        idx_map = {idx["name"]: idx for idx in indexes}
        assert idx_map["idx_name"]["column_names"] == ["name"]
        assert idx_map["idx_email"]["column_names"] == ["email"]

    def test_excludes_pk_index(self, engine):
        """PK index should not appear in get_indexes."""
        insp = inspect(engine)
        indexes = insp.get_indexes("t_parent")
        names = {idx["name"] for idx in indexes}
        for name in names:
            assert "pk_" not in name.lower() and "primary" not in name.lower()
