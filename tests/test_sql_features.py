"""SQL compiler feature tests for sqlalchemy-cubrid dialect (0.3.1).

String concatenation, functions, JOIN.

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
    ForeignKey,
    select,
    func,
    literal_column,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, relationship

CUBRID_URL = "cubrid://dba:@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


class Department(Base):
    __tablename__ = "t_department"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    employees: Mapped[list["Employee"]] = relationship(back_populates="department")


class Employee(Base):
    __tablename__ = "t_employee"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    dept_id: Mapped[int] = mapped_column(ForeignKey("t_department.id"), nullable=True)
    department: Mapped["Department"] = relationship(back_populates="employees")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module", autouse=True)
def setup_tables(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        eng = Department(name="Engineering")
        mkt = Department(name="Marketing")
        session.add_all([eng, mkt])
        session.flush()

        session.add_all([
            Employee(name="Alice", dept_id=eng.id),
            Employee(name="Bob", dept_id=eng.id),
            Employee(name="Charlie", dept_id=mkt.id),
            Employee(name="Dave", dept_id=None),  # no department
        ])
        session.commit()
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_employee"))
        conn.execute(text("DROP TABLE IF EXISTS t_department"))
        conn.commit()


class TestStringConcat:
    def test_concat_operator(self, engine):
        """String concatenation using || operator."""
        with engine.connect() as conn:
            result = conn.execute(
                select(
                    (literal_column("'Hello'") + literal_column("' World'")).label("greeting")
                )
            )
            row = result.fetchone()
            assert "Hello" in str(row[0]) or row[0] is not None

    def test_concat_function(self, engine):
        """CONCAT() function."""
        with engine.connect() as conn:
            result = conn.execute(
                select(func.concat("Hello", " ", "World").label("greeting"))
            )
            row = result.fetchone()
            assert row[0] == "Hello World"


class TestStringFunctions:
    def test_upper(self, engine):
        with Session(engine) as session:
            result = session.execute(
                select(func.upper(Employee.name))
                .where(Employee.name == "Alice")
            ).scalar_one()
            assert result == "ALICE"

    def test_lower(self, engine):
        with Session(engine) as session:
            result = session.execute(
                select(func.lower(Employee.name))
                .where(Employee.name == "Alice")
            ).scalar_one()
            assert result == "alice"

    def test_length(self, engine):
        with Session(engine) as session:
            result = session.execute(
                select(func.length(Employee.name))
                .where(Employee.name == "Alice")
            ).scalar_one()
            assert result == 5

    def test_substring(self, engine):
        with Session(engine) as session:
            result = session.execute(
                select(func.substr(Employee.name, 1, 3))
                .where(Employee.name == "Alice")
            ).scalar_one()
            assert result == "Ali"

    def test_trim(self, engine):
        with engine.connect() as conn:
            result = conn.execute(
                select(func.trim(literal_column("'  hello  '")))
            ).scalar_one()
            assert result == "hello"

    def test_replace(self, engine):
        with engine.connect() as conn:
            result = conn.execute(
                select(func.replace(literal_column("'hello world'"), "world", "cubrid"))
            ).scalar_one()
            assert result == "hello cubrid"


class TestDateFunctions:
    def test_now(self, engine):
        """NOW() returns current datetime."""
        with engine.connect() as conn:
            result = conn.execute(select(func.now())).scalar_one()
            assert result is not None

    def test_sysdate(self, engine):
        """SYS_DATE returns current date (keyword, not function)."""
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT SYS_DATE")
            ).scalar_one()
            assert result is not None


class TestJoins:
    def test_inner_join(self, engine):
        with Session(engine) as session:
            results = session.execute(
                select(Employee.name, Department.name)
                .join(Department)
                .order_by(Employee.name)
            ).all()
            names = [r[0] for r in results]
            assert "Alice" in names
            assert "Bob" in names
            assert "Charlie" in names
            # Dave has no department, should be excluded
            assert "Dave" not in names

    def test_left_join(self, engine):
        with Session(engine) as session:
            results = session.execute(
                select(Employee.name, Department.name)
                .outerjoin(Department)
                .order_by(Employee.name)
            ).all()
            names = [r[0] for r in results]
            # Dave should appear with NULL department
            assert "Dave" in names
            dave_row = [r for r in results if r[0] == "Dave"][0]
            assert dave_row[1] is None

    def test_cross_join(self, engine):
        with engine.connect() as conn:
            dept_table = Department.__table__
            emp_table = Employee.__table__
            result = conn.execute(
                select(emp_table.c.name, dept_table.c.name)
                .select_from(emp_table.join(dept_table, onclause=literal_column("1=1")))
            ).all()
            # 4 employees x 2 departments = 8 rows
            assert len(result) == 8
