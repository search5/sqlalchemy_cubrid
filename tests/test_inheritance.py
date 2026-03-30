"""Class inheritance (UNDER) tests for 0.7.0 features.

Tests CREATE TABLE ... UNDER, inheritance introspection, and CRUD.

Requires a running CUBRID instance:
    docker compose up -d
"""

import pytest
from sqlalchemy import (
    create_engine, text, inspect, MetaData, Table, Column, Integer, String,
    select,
)

from sqlalchemy_cubrid.inheritance import (
    CreateTableUnder,
    DropTableInheritance,
    get_super_class,
    get_sub_classes,
    get_inherited_columns,
)

import os
CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def inheritance_tables(engine):
    """Create parent and child tables with UNDER inheritance."""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_employee"))
        conn.execute(text("DROP TABLE IF EXISTS test_manager"))
        conn.execute(text("DROP TABLE IF EXISTS test_person"))

        # Parent
        conn.execute(text(
            "CREATE TABLE test_person ("
            "  id INTEGER AUTO_INCREMENT PRIMARY KEY,"
            "  name VARCHAR(50) NOT NULL,"
            "  age INTEGER"
            ")"
        ))

        # Child via UNDER
        conn.execute(text(
            "CREATE TABLE test_employee UNDER test_person ("
            "  department VARCHAR(50),"
            "  salary INTEGER"
            ")"
        ))

        # Grandchild via UNDER
        conn.execute(text(
            "CREATE TABLE test_manager UNDER test_employee ("
            "  team_size INTEGER"
            ")"
        ))

        conn.commit()

    yield

    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_manager"))
        conn.execute(text("DROP TABLE IF EXISTS test_employee"))
        conn.execute(text("DROP TABLE IF EXISTS test_person"))
        conn.commit()


class TestCreateTableUnder:
    def test_create_and_drop(self, engine):
        """CreateTableUnder DDL construct works end-to-end."""
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_under_child"))
            conn.execute(text("DROP TABLE IF EXISTS test_under_parent"))
            conn.execute(text(
                "CREATE TABLE test_under_parent ("
                "  id INTEGER AUTO_INCREMENT PRIMARY KEY,"
                "  name VARCHAR(50)"
                ")"
            ))
            conn.commit()

            # Use our DDL construct
            ddl = CreateTableUnder(
                "test_under_child", "test_under_parent",
                Column("score", Integer),
            )
            conn.execute(ddl)
            conn.commit()

            # Verify child exists
            assert engine.dialect.has_table(conn, "test_under_child")

            # Verify child has parent + own columns
            cols = [c["name"] for c in inspect(engine).get_columns("test_under_child")]
            assert "id" in cols
            assert "name" in cols
            assert "score" in cols

            # Cleanup
            conn.execute(DropTableInheritance("test_under_child"))
            conn.execute(text("DROP TABLE IF EXISTS test_under_parent"))
            conn.commit()

    def test_compile_output(self, engine):
        ddl = CreateTableUnder(
            "child", "parent",
            Column("grade", Integer),
        )
        compiled = ddl.compile(dialect=engine.dialect)
        sql = str(compiled)
        assert "CREATE TABLE" in sql
        assert "UNDER" in sql
        assert "parent" in sql.lower()
        assert "child" in sql.lower()


class TestInheritanceIntrospection:
    def test_get_super_class(self, engine, inheritance_tables):
        with engine.connect() as conn:
            assert get_super_class(conn, "test_employee") == "test_person"
            assert get_super_class(conn, "test_manager") == "test_employee"
            assert get_super_class(conn, "test_person") is None

    def test_get_sub_classes(self, engine, inheritance_tables):
        with engine.connect() as conn:
            subs = get_sub_classes(conn, "test_person")
            assert "test_employee" in subs

            subs2 = get_sub_classes(conn, "test_employee")
            assert "test_manager" in subs2

            subs3 = get_sub_classes(conn, "test_manager")
            assert subs3 == []

    def test_get_inherited_columns(self, engine, inheritance_tables):
        with engine.connect() as conn:
            cols = get_inherited_columns(conn, "test_employee")
            names = [c["name"] for c in cols]
            assert "id" in names
            assert "name" in names
            assert "department" in names

            # Check from_class for inherited vs local
            col_map = {c["name"]: c["from_class"] for c in cols}
            assert col_map["id"] == "test_person"
            assert col_map["name"] == "test_person"
            assert col_map["department"] is None  # local

    def test_get_inherited_columns_grandchild(self, engine, inheritance_tables):
        with engine.connect() as conn:
            cols = get_inherited_columns(conn, "test_manager")
            names = [c["name"] for c in cols]
            # Grandchild should have: id, name, age (from person),
            # department, salary (from employee), team_size (local)
            assert "id" in names
            assert "name" in names
            assert "age" in names
            assert "department" in names
            assert "salary" in names
            assert "team_size" in names

    def test_dialect_get_super_class_name(self, engine, inheritance_tables):
        with engine.connect() as conn:
            result = engine.dialect.get_super_class_name(
                conn, "test_employee"
            )
            assert result == "test_person"

    def test_dialect_get_sub_class_names(self, engine, inheritance_tables):
        with engine.connect() as conn:
            result = engine.dialect.get_sub_class_names(
                conn, "test_person"
            )
            assert "test_employee" in result

    def test_get_columns_includes_inherited(self, engine, inheritance_tables):
        """Standard get_columns() returns inherited columns too."""
        insp = inspect(engine)
        cols = insp.get_columns("test_employee")
        names = [c["name"] for c in cols]
        assert "id" in names       # from parent
        assert "name" in names     # from parent
        assert "department" in names  # local


class TestInheritanceCRUD:
    def test_insert_into_child(self, engine, inheritance_tables):
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO test_employee (name, age, department, salary) "
                "VALUES ('alice', 30, 'engineering', 80000)"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT name, department, salary FROM test_employee "
                "WHERE name = 'alice'"
            ))
            row = result.fetchone()
            assert row[0] == "alice"
            assert row[1] == "engineering"
            assert row[2] == 80000

            conn.execute(text("DELETE FROM test_employee WHERE name = 'alice'"))
            conn.commit()

    def test_insert_into_grandchild(self, engine, inheritance_tables):
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO test_manager "
                "(name, age, department, salary, team_size) "
                "VALUES ('bob', 45, 'engineering', 120000, 10)"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT name, department, team_size FROM test_manager "
                "WHERE name = 'bob'"
            ))
            row = result.fetchone()
            assert row[0] == "bob"
            assert row[1] == "engineering"
            assert row[2] == 10

            conn.execute(text("DELETE FROM test_manager WHERE name = 'bob'"))
            conn.commit()

    def test_parent_does_not_include_child_rows(self, engine, inheritance_tables):
        """In CUBRID, parent queries do NOT include child rows."""
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO test_person (name, age) VALUES ('parent_only', 50)"
            ))
            conn.execute(text(
                "INSERT INTO test_employee (name, age, department, salary) "
                "VALUES ('child_only', 25, 'sales', 50000)"
            ))
            conn.commit()

            # Parent should only have its own rows
            result = conn.execute(text(
                "SELECT name FROM test_person"
            ))
            parent_names = [r[0] for r in result]
            assert "parent_only" in parent_names
            assert "child_only" not in parent_names

            conn.execute(text("DELETE FROM test_employee WHERE name = 'child_only'"))
            conn.execute(text("DELETE FROM test_person WHERE name = 'parent_only'"))
            conn.commit()

    def test_update_child_row(self, engine, inheritance_tables):
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO test_employee (name, age, department, salary) "
                "VALUES ('carol', 35, 'hr', 70000)"
            ))
            conn.commit()

            conn.execute(text(
                "UPDATE test_employee SET salary = 75000 WHERE name = 'carol'"
            ))
            conn.commit()

            result = conn.execute(text(
                "SELECT salary FROM test_employee WHERE name = 'carol'"
            ))
            assert result.fetchone()[0] == 75000

            conn.execute(text("DELETE FROM test_employee WHERE name = 'carol'"))
            conn.commit()

    def test_delete_child_row(self, engine, inheritance_tables):
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO test_employee (name, age, department, salary) "
                "VALUES ('dave', 28, 'ops', 60000)"
            ))
            conn.commit()

            conn.execute(text("DELETE FROM test_employee WHERE name = 'dave'"))
            conn.commit()

            result = conn.execute(text(
                "SELECT COUNT(*) FROM test_employee WHERE name = 'dave'"
            ))
            assert result.scalar() == 0

    def test_orm_crud_with_reflected_child(self, engine, inheritance_tables):
        """ORM-style CRUD using reflected child table."""
        meta = MetaData()
        tbl = Table("test_employee", meta, autoload_with=engine)

        with engine.connect() as conn:
            conn.execute(
                tbl.insert().values(
                    name="eve", age=32, department="finance", salary=90000
                )
            )
            conn.commit()

            result = conn.execute(
                select(tbl).where(tbl.c.name == "eve")
            ).fetchone()
            assert result.department == "finance"
            assert result.salary == 90000

            conn.execute(
                tbl.update().where(tbl.c.name == "eve").values(salary=95000)
            )
            conn.commit()

            result = conn.execute(
                select(tbl.c.salary).where(tbl.c.name == "eve")
            ).fetchone()
            assert result[0] == 95000

            conn.execute(tbl.delete().where(tbl.c.name == "eve"))
            conn.commit()
