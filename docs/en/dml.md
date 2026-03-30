# DML Extensions

This page covers CUBRID-specific Data Manipulation Language constructs: INSERT ... ON DUPLICATE KEY UPDATE, REPLACE INTO, and FOR UPDATE.

## INSERT ... ON DUPLICATE KEY UPDATE

CUBRID supports `ON DUPLICATE KEY UPDATE` for upsert operations. Use the CUBRID-specific `insert()` function from `sqlalchemy_cubrid`:

```python
from sqlalchemy_cubrid import insert

stmt = insert(users).values(id=1, name="Alice", email="alice@example.com")
stmt = stmt.on_duplicate_key_update(
    name="Alice Updated",
    email="alice_new@example.com",
)

with engine.connect() as conn:
    conn.execute(stmt)
    conn.commit()
```

Generated SQL:

```sql
INSERT INTO users (id, name, email)
VALUES (?, ?, ?)
ON DUPLICATE KEY UPDATE name = ?, email = ?
```

!!! warning
    CUBRID does **not** support the `VALUES()` function in ON DUPLICATE KEY UPDATE (unlike MySQL). You must pass explicit values or column expressions. Do not reference `stmt.inserted` columns -- use literal values instead.

### Using a dictionary

```python
from sqlalchemy_cubrid import insert

stmt = insert(users).values(id=1, name="Alice", email="alice@example.com")
stmt = stmt.on_duplicate_key_update({
    "name": "Alice Updated",
    "email": "alice_new@example.com",
})
```

### Using a list of tuples (ordered)

```python
stmt = insert(users).values(id=1, name="Alice", email="alice@example.com")
stmt = stmt.on_duplicate_key_update([
    ("name", "Alice Updated"),
    ("email", "alice_new@example.com"),
])
```

### Using column expressions

```python
from sqlalchemy import literal

stmt = insert(users).values(id=1, name="Alice", email="alice@example.com")
stmt = stmt.on_duplicate_key_update(
    name=literal("Alice") + " (updated)",
)
```

## REPLACE INTO

`REPLACE INTO` deletes the existing row on duplicate key and inserts a new one. This is different from ON DUPLICATE KEY UPDATE, which modifies the row in place.

```python
from sqlalchemy_cubrid import replace

stmt = replace(users).values(id=1, name="Alice", email="alice@example.com")

with engine.connect() as conn:
    conn.execute(stmt)
    conn.commit()
```

Generated SQL:

```sql
REPLACE INTO users (id, name, email) VALUES (?, ?, ?)
```

!!! note
    `REPLACE INTO` first deletes any existing row that conflicts on a primary key or unique index, then inserts the new row. This means auto-increment values may change and triggers on DELETE will fire.

### Bulk replace

```python
from sqlalchemy_cubrid import replace

stmt = replace(users)

with engine.connect() as conn:
    conn.execute(stmt, [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
        {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
    ])
    conn.commit()
```

## FOR UPDATE

CUBRID supports `SELECT ... FOR UPDATE` for row-level locking. The standard SQLAlchemy `with_for_update()` is supported:

```python
from sqlalchemy import select

stmt = select(users).where(users.c.id == 1).with_for_update()

with engine.connect() as conn:
    row = conn.execute(stmt).first()
```

Generated SQL:

```sql
SELECT users.id, users.name, users.email
FROM users
WHERE users.id = ?
FOR UPDATE
```

### FOR UPDATE OF (column-level locking)

CUBRID supports the `OF` clause to lock specific columns:

```python
stmt = (
    select(users)
    .where(users.c.id == 1)
    .with_for_update(of=[users.c.name, users.c.email])
)
```

Generated SQL:

```sql
SELECT users.id, users.name, users.email
FROM users
WHERE users.id = ?
FOR UPDATE OF name, email
```

### FOR SHARE (not supported)

!!! warning
    CUBRID does **not** support `FOR SHARE` or `LOCK IN SHARE MODE`. If `with_for_update(read=True)` is used, the FOR UPDATE clause is silently omitted.

```python
# This will NOT generate a FOR SHARE clause -- it is silently ignored
stmt = select(users).with_for_update(read=True)
```

## TRUNCATE TABLE

CUBRID supports `TRUNCATE TABLE` to remove all rows from a table efficiently. The dialect provides a custom DDL element:

```python
from sqlalchemy_cubrid import truncate

with engine.connect() as conn:
    conn.execute(truncate("my_table"))
    conn.commit()
```

Generated SQL:

```sql
TRUNCATE TABLE "my_table"
```

!!! note
    `TRUNCATE TABLE` is faster than `DELETE FROM` because it does not log individual row deletions. However, it cannot be rolled back (CUBRID auto-commits DDL).

## REGEXP / RLIKE Operator

CUBRID supports `REGEXP` and `RLIKE` for regular expression matching. Use SQLAlchemy's `regexp_match()`:

```python
from sqlalchemy import select, column

stmt = select(column("name")).where(
    column("name").regexp_match(r"^[A-Z][a-z]+$")
)
```

Generated SQL:

```sql
SELECT name WHERE name REGEXP ?
```

Negation is also supported:

```python
stmt = select(column("name")).where(
    ~column("name").regexp_match(r"^test")
)
```

Generated SQL:

```sql
SELECT name WHERE NOT (name REGEXP ?)
```

## CAST Type Mapping

When using `CAST()`, the dialect automatically maps SQLAlchemy types to their CUBRID equivalents:

```python
from sqlalchemy import cast, literal_column, Text, Boolean

# CAST(x AS TEXT) -> CAST(x AS STRING)
stmt = cast(literal_column("description"), Text)

# CAST(x AS BOOLEAN) -> CAST(x AS SMALLINT)
stmt = cast(literal_column("flag"), Boolean)
```

| SQLAlchemy Type | CUBRID CAST Type |
|-----------------|------------------|
| `Text`          | `STRING`         |
| `Boolean`       | `SMALLINT`       |
| `Float`         | `DOUBLE`         |
| `NCHAR`         | `CHAR`           |
| `NVARCHAR`      | `VARCHAR`        |
| `LargeBinary`   | `BIT VARYING`    |

## Import Reference

All CUBRID DML constructs are importable from the top-level package:

```python
from sqlalchemy_cubrid import insert, Insert, replace, Replace, truncate, Truncate
```

Or from the `dml` submodule:

```python
from sqlalchemy_cubrid.dml import insert, Insert, replace, Replace, truncate, Truncate
```
