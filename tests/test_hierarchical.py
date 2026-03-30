"""Hierarchical query (CONNECT BY) tests for sqlalchemy-cubrid dialect (0.4.2).

CUBRID supports Oracle-style hierarchical queries:
    SELECT ... FROM ... START WITH ... CONNECT BY [NOCYCLE] PRIOR ...
    [ORDER SIBLINGS BY ...]

Pseudo-columns: LEVEL, CONNECT_BY_ISLEAF, CONNECT_BY_ISCYCLE
Functions: SYS_CONNECT_BY_PATH, CONNECT_BY_ROOT

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import (
    create_engine,
    text,
    MetaData,
    Table,
    Column,
    Integer,
    String,
)
from sqlalchemy_cubrid.hierarchical import (
    HierarchicalSelect,
    prior,
    level_col,
    sys_connect_by_path,
    connect_by_root,
    connect_by_isleaf,
)

import os
CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def tree_table(engine):
    metadata = MetaData()
    t = Table(
        "t_tree",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
        Column("parent_id", Integer),
    )
    metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM t_tree"))
        # Tree structure:
        #   1 (CEO)
        #   ├── 2 (CTO)
        #   │   ├── 4 (Dev Lead)
        #   │   └── 5 (QA Lead)
        #   └── 3 (CFO)
        #       └── 6 (Accountant)
        conn.execute(text(
            "INSERT INTO t_tree VALUES "
            "(1, 'CEO', NULL), "
            "(2, 'CTO', 1), "
            "(3, 'CFO', 1), "
            "(4, 'Dev Lead', 2), "
            "(5, 'QA Lead', 2), "
            "(6, 'Accountant', 3)"
        ))
        conn.commit()
    yield t
    metadata.drop_all(engine)


class TestConnectByRaw:
    """Test CONNECT BY with raw SQL to verify baseline behavior."""

    def test_basic_hierarchy(self, engine, tree_table):
        """Basic CONNECT BY traversal from root."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT id, name, LEVEL "
                "FROM t_tree "
                "START WITH parent_id IS NULL "
                "CONNECT BY PRIOR id = parent_id "
                "ORDER SIBLINGS BY name"
            ))
            rows = result.fetchall()
            # CEO(1) -> CFO(2) -> Accountant(2) -> CTO(2) -> Dev Lead(3) -> QA Lead(3)
            assert len(rows) == 6
            assert rows[0][1] == "CEO"
            assert rows[0][2] == 1  # LEVEL

    def test_level_filtering(self, engine, tree_table):
        """Filter by LEVEL pseudo-column using WHERE."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name, LEVEL "
                "FROM t_tree "
                "WHERE LEVEL <= 2 "
                "START WITH parent_id IS NULL "
                "CONNECT BY PRIOR id = parent_id"
            ))
            rows = result.fetchall()
            # Only CEO (level 1) and CTO, CFO (level 2)
            assert all(row[1] <= 2 for row in rows)

    def test_sys_connect_by_path(self, engine, tree_table):
        """SYS_CONNECT_BY_PATH returns full hierarchy path."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT SYS_CONNECT_BY_PATH(name, '/') "
                "FROM t_tree "
                "WHERE name = 'Dev Lead' "
                "START WITH parent_id IS NULL "
                "CONNECT BY PRIOR id = parent_id"
            ))
            path = result.scalar()
            assert "/CEO/CTO/Dev Lead" == path

    def test_connect_by_root(self, engine, tree_table):
        """CONNECT_BY_ROOT returns root ancestor value."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name, CONNECT_BY_ROOT name AS root_name "
                "FROM t_tree "
                "START WITH parent_id IS NULL "
                "CONNECT BY PRIOR id = parent_id"
            ))
            rows = result.fetchall()
            # All rows share the same root: CEO
            for row in rows:
                assert row[1] == "CEO"

    def test_connect_by_isleaf(self, engine, tree_table):
        """CONNECT_BY_ISLEAF identifies leaf nodes."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name, CONNECT_BY_ISLEAF "
                "FROM t_tree "
                "START WITH parent_id IS NULL "
                "CONNECT BY PRIOR id = parent_id"
            ))
            rows = {row[0]: row[1] for row in result}
            assert rows["CEO"] == 0       # has children
            assert rows["Dev Lead"] == 1  # leaf
            assert rows["Accountant"] == 1  # leaf

    def test_order_siblings_by(self, engine, tree_table):
        """ORDER SIBLINGS BY sorts within same level."""
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name, LEVEL "
                "FROM t_tree "
                "START WITH parent_id IS NULL "
                "CONNECT BY PRIOR id = parent_id "
                "ORDER SIBLINGS BY name"
            ))
            rows = result.fetchall()
            # At level 2: CFO before CTO (alphabetical)
            level2 = [r[0] for r in rows if r[1] == 2]
            assert level2 == ["CFO", "CTO"]


class TestHierarchicalSelect:
    """Test CONNECT BY via SQLAlchemy HierarchicalSelect construct."""

    def test_basic_connect_by(self, engine, tree_table):
        """HierarchicalSelect generates correct CONNECT BY SQL."""
        t = tree_table
        stmt = HierarchicalSelect(
            t,
            columns=[t.c.id, t.c.name, level_col()],
            connect_by=prior(t.c.id) == t.c.parent_id,
            start_with=t.c.parent_id == None,  # noqa: E711
        )
        with engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
            assert len(rows) == 6
            # First row is root (LEVEL=1)
            root = [r for r in rows if r[2] == 1]
            assert len(root) == 1
            assert root[0][1] == "CEO"

    def test_with_order_siblings_by(self, engine, tree_table):
        """ORDER SIBLINGS BY preserves hierarchy while sorting."""
        t = tree_table
        stmt = HierarchicalSelect(
            t,
            columns=[t.c.name, level_col()],
            connect_by=prior(t.c.id) == t.c.parent_id,
            start_with=t.c.parent_id == None,  # noqa: E711
            order_siblings_by=[t.c.name],
        )
        with engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
            level2 = [r[0] for r in rows if r[1] == 2]
            assert level2 == ["CFO", "CTO"]

    def test_with_sys_connect_by_path(self, engine, tree_table):
        """SYS_CONNECT_BY_PATH function in columns."""
        t = tree_table
        stmt = HierarchicalSelect(
            t,
            columns=[t.c.name, sys_connect_by_path(t.c.name, "/")],
            connect_by=prior(t.c.id) == t.c.parent_id,
            start_with=t.c.parent_id == None,  # noqa: E711
            where=t.c.name == "Dev Lead",
        )
        with engine.connect() as conn:
            row = conn.execute(stmt).fetchone()
            assert row[1] == "/CEO/CTO/Dev Lead"

    def test_with_connect_by_root(self, engine, tree_table):
        """CONNECT_BY_ROOT operator in columns."""
        t = tree_table
        stmt = HierarchicalSelect(
            t,
            columns=[t.c.name, connect_by_root(t.c.name)],
            connect_by=prior(t.c.id) == t.c.parent_id,
            start_with=t.c.parent_id == None,  # noqa: E711
        )
        with engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
            for row in rows:
                assert row[1] == "CEO"

    def test_with_connect_by_isleaf(self, engine, tree_table):
        """CONNECT_BY_ISLEAF pseudo-column in columns."""
        t = tree_table
        stmt = HierarchicalSelect(
            t,
            columns=[t.c.name, connect_by_isleaf()],
            connect_by=prior(t.c.id) == t.c.parent_id,
            start_with=t.c.parent_id == None,  # noqa: E711
        )
        with engine.connect() as conn:
            rows = {r[0]: r[1] for r in conn.execute(stmt)}
            assert rows["CEO"] == 0
            assert rows["Dev Lead"] == 1

    def test_nocycle(self, engine):
        """NOCYCLE prevents infinite loops in cyclic data."""
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS t_cycle"))
            conn.execute(text(
                "CREATE TABLE t_cycle (id INT PRIMARY KEY, pid INT)"
            ))
            conn.execute(text(
                "INSERT INTO t_cycle VALUES (1, 3), (2, 1), (3, 2)"
            ))
            conn.commit()

            # Without NOCYCLE this would error; with NOCYCLE it succeeds
            result = conn.execute(text(
                "SELECT id, LEVEL FROM t_cycle "
                "START WITH id = 1 "
                "CONNECT BY NOCYCLE PRIOR id = pid"
            ))
            rows = result.fetchall()
            assert len(rows) >= 1

            conn.execute(text("DROP TABLE t_cycle"))
            conn.commit()

    def test_compile_output(self, engine, tree_table):
        """Verify compiled SQL contains CONNECT BY keywords."""
        t = tree_table
        stmt = HierarchicalSelect(
            t,
            columns=[t.c.id, t.c.name],
            connect_by=prior(t.c.id) == t.c.parent_id,
            start_with=t.c.parent_id == None,  # noqa: E711
            nocycle=True,
        )
        compiled = stmt.compile(engine)
        sql_str = str(compiled).upper()
        assert "CONNECT BY" in sql_str
        assert "NOCYCLE" in sql_str
        assert "START WITH" in sql_str
        assert "PRIOR" in sql_str
