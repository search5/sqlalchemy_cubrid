"""Complex query tests for sqlalchemy-cubrid dialect (0.3.2).

Subqueries, GROUP BY / HAVING / ORDER BY, UNION / INTERSECT / EXCEPT.

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
    select,
    func,
    union,
    union_all,
    intersect,
    except_,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

CUBRID_URL = "cubrid://dba:@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "t_product"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(50))
    price: Mapped[int] = mapped_column(Integer)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module", autouse=True)
def setup_tables(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Product(name="Widget A", category="widgets", price=100),
            Product(name="Widget B", category="widgets", price=200),
            Product(name="Widget C", category="widgets", price=150),
            Product(name="Gadget A", category="gadgets", price=300),
            Product(name="Gadget B", category="gadgets", price=250),
            Product(name="Tool A", category="tools", price=50),
        ])
        session.commit()
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_product"))
        conn.commit()


class TestGroupBy:
    def test_group_by_count(self, engine):
        with Session(engine) as session:
            results = session.execute(
                select(Product.category, func.count(Product.id).label("cnt"))
                .group_by(Product.category)
                .order_by(Product.category)
            ).all()
            cat_map = {r[0]: r[1] for r in results}
            assert cat_map["widgets"] == 3
            assert cat_map["gadgets"] == 2
            assert cat_map["tools"] == 1

    def test_group_by_sum(self, engine):
        with Session(engine) as session:
            results = session.execute(
                select(Product.category, func.sum(Product.price).label("total"))
                .group_by(Product.category)
                .order_by(Product.category)
            ).all()
            cat_map = {r[0]: r[1] for r in results}
            assert cat_map["widgets"] == 450
            assert cat_map["gadgets"] == 550

    def test_group_by_avg(self, engine):
        with Session(engine) as session:
            result = session.execute(
                select(func.avg(Product.price).label("avg_price"))
                .where(Product.category == "widgets")
            ).scalar_one()
            assert result == 150


class TestHaving:
    def test_having_filter(self, engine):
        with Session(engine) as session:
            results = session.execute(
                select(Product.category, func.count(Product.id).label("cnt"))
                .group_by(Product.category)
                .having(func.count(Product.id) >= 2)
                .order_by(Product.category)
            ).all()
            categories = [r[0] for r in results]
            assert "widgets" in categories
            assert "gadgets" in categories
            assert "tools" not in categories


class TestOrderBy:
    def test_order_by_asc(self, engine):
        with Session(engine) as session:
            results = session.execute(
                select(Product.price)
                .order_by(Product.price.asc())
            ).scalars().all()
            assert results == sorted(results)

    def test_order_by_desc(self, engine):
        with Session(engine) as session:
            results = session.execute(
                select(Product.price)
                .order_by(Product.price.desc())
            ).scalars().all()
            assert results == sorted(results, reverse=True)

    def test_order_by_multiple(self, engine):
        with Session(engine) as session:
            results = session.execute(
                select(Product.category, Product.price)
                .order_by(Product.category.asc(), Product.price.desc())
            ).all()
            assert len(results) == 6


class TestSubqueries:
    def test_scalar_subquery(self, engine):
        with Session(engine) as session:
            avg_price = select(func.avg(Product.price)).scalar_subquery()
            results = session.execute(
                select(Product.name)
                .where(Product.price > avg_price)
                .order_by(Product.name)
            ).scalars().all()
            assert "Gadget A" in results
            assert "Gadget B" in results

    def test_in_subquery(self, engine):
        with Session(engine) as session:
            expensive_categories = (
                select(Product.category)
                .group_by(Product.category)
                .having(func.avg(Product.price) > 200)
            ).subquery()
            results = session.execute(
                select(Product.name)
                .where(Product.category.in_(
                    select(expensive_categories.c.category)
                ))
                .order_by(Product.name)
            ).scalars().all()
            assert "Gadget A" in results
            assert "Widget A" not in results

    def test_exists_subquery(self, engine):
        with Session(engine) as session:
            from sqlalchemy import exists
            expensive_exists = (
                exists()
                .where(Product.category == "gadgets")
                .where(Product.price > 200)
            )
            results = session.execute(
                select(Product.name).where(expensive_exists)
            ).scalars().all()
            # EXISTS is always true here, so all products returned
            assert len(results) == 6

    def test_derived_table(self, engine):
        """Subquery in FROM clause."""
        with Session(engine) as session:
            subq = (
                select(
                    Product.category,
                    func.max(Product.price).label("max_price")
                )
                .group_by(Product.category)
            ).subquery()

            results = session.execute(
                select(subq.c.category, subq.c.max_price)
                .order_by(subq.c.max_price.desc())
            ).all()
            assert len(results) == 3
            assert results[0][1] == 300  # gadgets max


class TestSetOperations:
    def test_union(self, engine):
        with engine.connect() as conn:
            q1 = select(Product.name).where(Product.category == "widgets")
            q2 = select(Product.name).where(Product.category == "gadgets")
            result = conn.execute(union(q1, q2)).fetchall()
            names = [r[0] for r in result]
            assert len(names) == 5

    def test_union_all(self, engine):
        with engine.connect() as conn:
            q1 = select(Product.name).where(Product.price > 100)
            q2 = select(Product.name).where(Product.category == "widgets")
            result = conn.execute(union_all(q1, q2)).fetchall()
            # May have duplicates
            assert len(result) >= 5

    def test_intersect(self, engine):
        with engine.connect() as conn:
            q1 = select(Product.name).where(Product.price > 100)
            q2 = select(Product.name).where(Product.category == "widgets")
            result = conn.execute(intersect(q1, q2)).fetchall()
            names = [r[0] for r in result]
            # Widget B (200) and Widget C (150) are > 100 and widgets
            assert "Widget B" in names
            assert "Widget C" in names
            assert "Widget A" not in names  # price is 100, not > 100

    def test_except(self, engine):
        with engine.connect() as conn:
            q1 = select(Product.name).where(Product.category == "widgets")
            q2 = select(Product.name).where(Product.price > 150)
            result = conn.execute(except_(q1, q2)).fetchall()
            names = [r[0] for r in result]
            # widgets minus those with price > 150
            assert "Widget A" in names
            assert "Widget C" in names
            assert "Widget B" not in names  # price 200 > 150
