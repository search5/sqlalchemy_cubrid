"""ORM CRUD and SQL compiler tests for sqlalchemy-cubrid dialect (0.3.0).

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
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

import os
CUBRID_URL = os.environ.get("CUBRID_TEST_URL", "cubrid://dba:@localhost:33000/testdb")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "t_orm_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), nullable=True)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(CUBRID_URL)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def setup_tables(engine):
    Base.metadata.create_all(engine)
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_orm_user"))
        conn.commit()


class TestORMInsert:
    def test_insert_single(self, engine):
        with Session(engine) as session:
            user = User(name="alice", email="alice@example.com")
            session.add(user)
            session.commit()
            assert user.id is not None
            assert user.id > 0

    def test_insert_multiple(self, engine):
        with Session(engine) as session:
            users = [
                User(name="bob", email="bob@example.com"),
                User(name="charlie", email="charlie@example.com"),
            ]
            session.add_all(users)
            session.commit()
            assert all(u.id is not None for u in users)


class TestORMSelect:
    def test_select_all(self, engine):
        with Session(engine) as session:
            session.add(User(name="dave", email="dave@example.com"))
            session.commit()

            users = session.execute(select(User)).scalars().all()
            assert len(users) >= 1

    def test_select_filter(self, engine):
        with Session(engine) as session:
            session.add(User(name="eve_unique", email="eve@example.com"))
            session.commit()

            user = session.execute(
                select(User).where(User.name == "eve_unique")
            ).scalar_one()
            assert user.name == "eve_unique"
            assert user.email == "eve@example.com"

    def test_select_limit_offset(self, engine):
        with Session(engine) as session:
            for i in range(5):
                session.add(User(name=f"limit_user_{i}", email=f"u{i}@example.com"))
            session.commit()

            users = session.execute(
                select(User)
                .where(User.name.like("limit_user_%"))
                .order_by(User.id)
                .limit(3)
                .offset(1)
            ).scalars().all()
            assert len(users) == 3


class TestORMUpdate:
    def test_update_attribute(self, engine):
        with Session(engine) as session:
            user = User(name="frank", email="frank@example.com")
            session.add(user)
            session.commit()
            user_id = user.id

            user.email = "frank_updated@example.com"
            session.commit()

        with Session(engine) as session:
            updated = session.get(User, user_id)
            assert updated.email == "frank_updated@example.com"


class TestORMDelete:
    def test_delete_single(self, engine):
        with Session(engine) as session:
            user = User(name="grace_delete", email="grace@example.com")
            session.add(user)
            session.commit()
            user_id = user.id

            session.delete(user)
            session.commit()

        with Session(engine) as session:
            deleted = session.get(User, user_id)
            assert deleted is None


class TestLimitOffset:
    def test_limit_only(self, engine):
        """LIMIT clause in raw Core query."""
        metadata = MetaData()
        metadata.reflect(bind=engine)

        with engine.connect() as conn:
            result = conn.execute(
                select(User).order_by(User.id).limit(2)
            )
            rows = result.fetchall()
            assert len(rows) <= 2

    def test_limit_with_offset(self, engine):
        """LIMIT with OFFSET clause."""
        with engine.connect() as conn:
            result = conn.execute(
                select(User).order_by(User.id).limit(2).offset(0)
            )
            rows = result.fetchall()
            assert len(rows) <= 2
