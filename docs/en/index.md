# sqlalchemy-cubrid

**CUBRID dialect for SQLAlchemy 2.x**

sqlalchemy-cubrid is a SQLAlchemy dialect plugin that enables full access to the CUBRID object-relational database from Python. It supports CUBRID versions 10.2 through 11.4 via the [pycubrid](https://pypi.org/project/pycubrid/) pure-Python driver.

## Key Features

- **Full SQLAlchemy 2.x compatibility** -- works with the modern SQLAlchemy API, ORM, and Core
- **DDL generation** -- CREATE/DROP TABLE, AUTO_INCREMENT, SERIAL (sequence), indexes (UNIQUE, REVERSE, FILTERED, FUNCTION-based), table/column comments
- **Complete type system** -- maps all CUBRID types including ENUM, JSON, collection types (SET, MULTISET, LIST), and DATETIME with millisecond precision
- **CUBRID-specific DML** -- INSERT ... ON DUPLICATE KEY UPDATE, REPLACE INTO, FOR UPDATE OF, TRUNCATE TABLE
- **Hierarchical queries** -- Oracle-style CONNECT BY / START WITH / ORDER SIBLINGS BY, ROWNUM pseudo-column
- **MERGE statement** -- MERGE INTO ... USING ... ON ... WHEN MATCHED (UPDATE / DELETE) / WHEN NOT MATCHED, conditional WHEN clauses
- **Object-relational features** -- class inheritance (UNDER), OID references with path expression dereferencing
- **Collection types** -- CubridSet, CubridMultiset, CubridList with automatic binary format parsing
- **Click counters** -- INCR() / DECR() atomic counter functions
- **Built-in functions** -- NVL, NVL2, DECODE, IF, IFNULL, GROUP_CONCAT
- **REGEXP operator** -- `column.regexp_match()` support for CUBRID's REGEXP / RLIKE
- **Partitioning** -- RANGE, HASH, LIST partition DDL support
- **DBLINK** -- remote database access via CREATE SERVER and DBLINK() (11.2+)
- **CAST type mapping** -- `CAST(x AS TEXT)` automatically becomes `CAST(x AS STRING)` for CUBRID compatibility
- **Introspection** -- full Inspector support for tables, views, columns, indexes, foreign keys (with ON DELETE/UPDATE actions), sequences, comments, inheritance, and OID columns
- **Alembic integration** -- migration support with collection type rendering and comparison
- **Query tracing** -- built-in SET TRACE ON / SHOW TRACE wrappers for performance analysis
- **Connection management** -- isolation levels, connection pooling, ping, disconnect detection

## Quick Install

```bash
pip install git+https://github.com/search5/sqlalchemy_cubrid.git
```

Or with Poetry:

```bash
poetry add git+https://github.com/search5/sqlalchemy_cubrid.git
```

## Quick Start

```python
from sqlalchemy import create_engine, text

engine = create_engine("cubrid://dba:@localhost:33000/testdb")

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1 FROM db_root"))
    print(result.scalar())  # 1
```

## Documentation

| Section | Description |
|---------|-------------|
| [Getting Started](getting-started.md) | Installation, Docker setup, first connection |
| [Connection](connection.md) | Engine URLs, isolation levels, pooling |
| [Types](types.md) | Type mapping between CUBRID and SQLAlchemy |
| [DDL](ddl.md) | Tables, sequences, indexes, comments |
| [DML](dml.md) | INSERT ON DUPLICATE KEY, REPLACE, FOR UPDATE |
| [Queries](queries.md) | Hierarchical queries, MERGE, click counters |
| [CUBRID Features](cubrid-features.md) | Collections, inheritance, OID references |
| [Introspection](introspection.md) | Inspector methods and reflection |
| [Alembic](alembic.md) | Migration support and query tracing |
| [Limitations](limitations.md) | Known limitations and test suite results |

## Links

- **Source code:** [github.com/search5/sqlalchemy_cubrid](https://github.com/search5/sqlalchemy_cubrid)
- **CUBRID documentation:** [cubrid.org/manual/ko/11.4/](https://www.cubrid.org/manual/ko/11.4/)
- **pycubrid driver:** [pypi.org/project/pycubrid/](https://pypi.org/project/pycubrid/)

## License

MIT License. See [LICENSE](https://github.com/search5/sqlalchemy_cubrid/blob/main/LICENSE) for details.
