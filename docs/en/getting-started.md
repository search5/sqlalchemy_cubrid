# Getting Started

This guide walks you through installing sqlalchemy-cubrid, setting up a CUBRID database with Docker, and running your first queries.

## Installation

### Using pip

```bash
pip install sqlalchemy-cubrid
```

This installs `sqlalchemy-cubrid` along with its dependencies: `sqlalchemy>=2.0` and `pycubrid>=0.6.0`.

### Using Poetry

```bash
poetry add sqlalchemy-cubrid
```

### From source

```bash
git clone https://github.com/cubrid-sqlalchemy/sqlalchemy-cubrid.git
cd sqlalchemy-cubrid
poetry install
```

## Setting Up CUBRID with Docker

The easiest way to run CUBRID for development is via Docker.

### Start a CUBRID container

```bash
docker run -d \
  --name cubrid-dev \
  -p 33000:33000 \
  -e CUBRID_DB=testdb \
  cubrid/cubrid:11.4
```

This starts CUBRID 11.4 with a database named `testdb`, exposed on port 33000. The default DBA user has an empty password.

### Verify the container is running

```bash
docker logs cubrid-dev
```

Wait until you see a message indicating the database is ready.

### Other CUBRID versions

```bash
# CUBRID 11.2
docker run -d --name cubrid-11.2 -p 33000:33000 -e CUBRID_DB=testdb cubrid/cubrid:11.2

# CUBRID 10.2
docker run -d --name cubrid-10.2 -p 33000:33000 -e CUBRID_DB=testdb cubrid/cubrid:10.2
```

## First Connection

```python
from sqlalchemy import create_engine, text

# Connect to CUBRID
engine = create_engine("cubrid://dba:@localhost:33000/testdb")

# Test the connection
with engine.connect() as conn:
    result = conn.execute(text("SELECT 1 FROM db_root"))
    print(result.scalar())  # 1
```

!!! note
    The connection URL format is `cubrid://user:password@host:port/database`. The default user is `dba` with an empty password. The default CUBRID broker port is `33000`.

## Basic ORM Example

Here is a complete example that creates a table, inserts rows, and queries them using the SQLAlchemy ORM.

### Define a model

```python
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200))

    def __repr__(self):
        return f"<User(id={self.id}, name={self.name!r})>"
```

### Create the table and add data

```python
engine = create_engine("cubrid://dba:@localhost:33000/testdb", echo=True)

# Create all tables
Base.metadata.create_all(engine)

# Insert rows
with Session(engine) as session:
    session.add_all([
        User(name="Alice", email="alice@example.com"),
        User(name="Bob", email="bob@example.com"),
        User(name="Charlie", email="charlie@example.com"),
    ])
    session.commit()
```

### Query data

```python
from sqlalchemy import select

with Session(engine) as session:
    # Select all users
    stmt = select(User).order_by(User.name)
    users = session.scalars(stmt).all()
    for user in users:
        print(user)
    # <User(id=1, name='Alice')>
    # <User(id=2, name='Bob')>
    # <User(id=3, name='Charlie')>

    # Filter
    stmt = select(User).where(User.name == "Alice")
    alice = session.scalars(stmt).first()
    print(alice.email)  # alice@example.com
```

### Update and delete

```python
with Session(engine) as session:
    # Update
    alice = session.scalars(
        select(User).where(User.name == "Alice")
    ).first()
    alice.email = "alice@newdomain.com"
    session.commit()

    # Delete
    bob = session.scalars(
        select(User).where(User.name == "Bob")
    ).first()
    session.delete(bob)
    session.commit()
```

### Clean up

```python
# Drop all tables
Base.metadata.drop_all(engine)
```

## Using SQLAlchemy Core

If you prefer the Core API over the ORM:

```python
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, select, insert

engine = create_engine("cubrid://dba:@localhost:33000/testdb")
metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("email", String(200)),
)

# Create table
metadata.create_all(engine)

with engine.connect() as conn:
    # Insert
    conn.execute(insert(users).values(name="Alice", email="alice@example.com"))
    conn.commit()

    # Query
    stmt = select(users).where(users.c.name == "Alice")
    row = conn.execute(stmt).first()
    print(row)  # (1, 'Alice', 'alice@example.com')

# Drop table
metadata.drop_all(engine)
```

## Next Steps

- [Connection](connection.md) -- learn about connection options and isolation levels
- [Types](types.md) -- understand the CUBRID type mapping
- [DDL](ddl.md) -- create tables, sequences, and indexes
- [CUBRID Features](cubrid-features.md) -- explore collection types, inheritance, and OID references
