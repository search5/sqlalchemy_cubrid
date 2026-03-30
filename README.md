# sqlalchemy-cubrid

CUBRID dialect for SQLAlchemy 2.x.

Supports CUBRID 10.2, 11.0, 11.2, 11.3, and 11.4 via the
[pycubrid](https://pypi.org/project/pycubrid/) pure-Python driver.

## Installation

```bash
pip install sqlalchemy-cubrid
```

Or with Poetry:

```bash
poetry add sqlalchemy-cubrid
```

## Quick Start

```python
from sqlalchemy import create_engine, text

engine = create_engine("cubrid://dba:@localhost:33000/testdb")

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1 FROM db_root"))
    print(result.scalar())
```

## Supported Versions

| Component | Versions |
|-----------|----------|
| CUBRID    | 10.2, 11.0, 11.2, 11.3, 11.4 |
| Python    | 3.10+ |
| SQLAlchemy | 2.0+ |

## Features

### Standard SQLAlchemy

- Full type system (INTEGER, VARCHAR, DATETIME, BLOB, CLOB, JSON, ENUM, etc.)
- DDL: CREATE/DROP TABLE, INDEX, SERIAL (sequence)
- ORM CRUD (INSERT, SELECT, UPDATE, DELETE)
- Table reflection (`metadata.reflect()`)
- Introspection (columns, primary keys, foreign keys, indexes, views, comments)
- LIMIT/OFFSET, JOIN, subqueries, GROUP BY, UNION/INTERSECT/EXCEPT
- Isolation levels, savepoints, connection pooling
- Alembic migration support

### CUBRID-Specific

#### Collection Types (SET, MULTISET, LIST)

```python
from sqlalchemy_cubrid.types import CubridSet, CubridMultiset, CubridList

Column("tags", CubridSet("VARCHAR(50)"))
Column("scores", CubridList("INTEGER"))
```

#### Hierarchical Queries (CONNECT BY)

```python
from sqlalchemy_cubrid import HierarchicalSelect, prior, level_col

stmt = HierarchicalSelect(
    table,
    columns=[table.c.id, table.c.name, level_col()],
    connect_by=prior(table.c.id) == table.c.parent_id,
    start_with=table.c.parent_id == None,
)
```

#### MERGE Statement

```python
from sqlalchemy_cubrid import Merge

stmt = Merge(target).using(source).on(target.c.id == source.c.id)
stmt = stmt.when_matched_then_update({"name": source.c.name})
stmt = stmt.when_not_matched_then_insert({"id": source.c.id, "name": source.c.name})
```

#### INSERT ... ON DUPLICATE KEY UPDATE

```python
from sqlalchemy_cubrid import insert

stmt = insert(table).values(id=1, name="Alice")
stmt = stmt.on_duplicate_key_update(name="Alice Updated")
```

#### REPLACE INTO

```python
from sqlalchemy_cubrid import replace

stmt = replace(table).values(id=1, name="Alice")
```

#### SERIAL (Sequence)

```python
from sqlalchemy import Sequence, Column, Integer

Column("id", Integer, Sequence("my_serial"), primary_key=True)
```

#### Class Inheritance (UNDER)

```python
from sqlalchemy_cubrid import CreateTableUnder
from sqlalchemy import Column, Integer

ddl = CreateTableUnder("employee", "person", Column("salary", Integer))
conn.execute(ddl)
```

#### OID References

```python
from sqlalchemy_cubrid import CubridOID, deref, CreateTableDontReuseOID

# Create a referable table
ddl = CreateTableDontReuseOID("person", Column("id", Integer), Column("name", String(50)))
conn.execute(ddl)

# Dereference OID column in queries
stmt = select(deref(literal_column("manager"), "name")).select_from(text("department"))
```

#### CLICK COUNTER

```python
from sqlalchemy_cubrid import incr, decr

conn.execute(update(table).values(counter=incr(table.c.counter)))
```

## Docker Setup

Start a CUBRID test instance:

```bash
docker-compose up -d
```

Run tests:

```bash
poetry run pytest tests/ -v
```

## Known Limitations

- CUBRID lowercases all identifiers (quoted names are stored lowercase)
- DATETIME has millisecond precision (not microsecond)
- AUTO_INCREMENT does not auto-create UNIQUE constraint
- CHECK constraints are parsed but not enforced
- No BOOLEAN column type (mapped to SMALLINT)
- No RETURNING clause support
- No temporary table support

## Documentation

Full documentation: [https://cubrid-sqlalchemy.github.io/sqlalchemy-cubrid/](https://cubrid-sqlalchemy.github.io/sqlalchemy-cubrid/)

## License

MIT License. See [LICENSE](LICENSE) for details.
