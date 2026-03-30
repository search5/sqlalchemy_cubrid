# DDL

This page covers Data Definition Language operations: creating and dropping tables, AUTO_INCREMENT, SERIAL (sequence), indexes, and table/column comments.

## CREATE TABLE and DROP TABLE

Standard SQLAlchemy table definition works as expected:

```python
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String

engine = create_engine("cubrid://dba:@localhost:33000/testdb")
metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("email", String(200)),
)

# CREATE TABLE
metadata.create_all(engine)

# DROP TABLE
metadata.drop_all(engine)
```

## AUTO_INCREMENT

CUBRID supports `AUTO_INCREMENT` on integer primary key columns. Important differences from MySQL:

!!! warning
    - CUBRID allows **only one** AUTO_INCREMENT column per table.
    - AUTO_INCREMENT does **not** automatically create a UNIQUE index. You must add uniqueness explicitly if needed.

```python
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100)),
)
```

Generated DDL:

```sql
CREATE TABLE users (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(100),
    PRIMARY KEY (id)
)
```

### AUTO_INCREMENT with seed and increment

CUBRID supports `AUTO_INCREMENT(seed, increment)` syntax. SQLAlchemy's `Identity` is rendered as AUTO_INCREMENT:

```python
from sqlalchemy import Identity

Table(
    "counters", metadata,
    Column("id", Integer, Identity(start=100, increment=10), primary_key=True),
)
```

!!! note
    The `Identity()` construct is mapped to `AUTO_INCREMENT` in the DDL since CUBRID does not have SQL-standard `GENERATED AS IDENTITY`.

### Sequence-based defaults

If a column has a `Sequence` default, AUTO_INCREMENT is suppressed and the serial is used instead:

```python
from sqlalchemy import Sequence

my_seq = Sequence("my_seq", start=1)

Table(
    "items", metadata,
    Column("id", Integer, my_seq, primary_key=True),
)
```

## DONT_REUSE_OID Table Option

CUBRID defaults to `REUSE_OID` since version 10.x. To make a table referable by OID columns (for object-relational references), use the `cubrid_dont_reuse_oid` dialect option:

```python
person = Table(
    "person", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(50)),
    cubrid_dont_reuse_oid=True,
)
```

Generated DDL:

```sql
CREATE TABLE person (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(50),
    PRIMARY KEY (id)
) DONT_REUSE_OID
```

## SERIAL (Sequence)

CUBRID uses `SERIAL` instead of the SQL-standard `SEQUENCE`. The dialect automatically translates SQLAlchemy's `Sequence` construct to `CREATE SERIAL` / `DROP SERIAL`.

### Creating a serial

```python
from sqlalchemy import Sequence

my_serial = Sequence("my_serial", start=1, increment=1)
metadata.create_all(engine)  # Emits CREATE SERIAL my_serial START WITH 1 INCREMENT BY 1
```

### Serial options

| Option        | Description                          | Example                |
|---------------|--------------------------------------|------------------------|
| `start`       | Initial value                        | `start=100`            |
| `increment`   | Step between values                  | `increment=5`          |
| `minvalue`    | Minimum value                        | `minvalue=1`           |
| `maxvalue`    | Maximum value                        | `maxvalue=999999`      |
| `cycle`       | Wrap around when max/min is reached  | `cycle=True`           |
| `cache`       | Number of values to pre-allocate     | `cache=20`             |
| `nominvalue`  | Explicitly no minimum value          | `nominvalue=True`      |
| `nomaxvalue`  | Explicitly no maximum value          | `nomaxvalue=True`      |

```python
from sqlalchemy import Sequence

order_seq = Sequence(
    "order_seq",
    start=1000,
    increment=1,
    minvalue=1000,
    maxvalue=9999999,
    cycle=True,
    cache=50,
)
```

Generated DDL:

```sql
CREATE SERIAL order_seq START WITH 1000 INCREMENT BY 1 MINVALUE 1000 MAXVALUE 9999999 CYCLE CACHE 50
```

### Using a serial in a column

```python
order_seq = Sequence("order_seq", start=1000)

orders = Table(
    "orders", metadata,
    Column("id", Integer, order_seq, primary_key=True),
    Column("description", String(200)),
)
```

The column default calls `order_seq.NEXT_VALUE` to obtain the next serial value.

### Dropping a serial

Serials are dropped with `IF EXISTS`:

```sql
DROP SERIAL IF EXISTS order_seq
```

## CREATE INDEX and DROP INDEX

### Standard index

```python
from sqlalchemy import Index

Index("idx_users_email", users.c.email)
```

### UNIQUE index

```python
Index("idx_users_email_unique", users.c.email, unique=True)
```

### REVERSE index

CUBRID supports reverse indexes for optimizing descending-order queries. Use the `cubrid_reverse` dialect option:

```python
Index("idx_users_name_rev", users.c.name, cubrid_reverse=True)
```

!!! note
    Reverse indexes in CUBRID are B-tree indexes that store keys in reverse order. They optimize queries with `ORDER BY column DESC`.

### FILTERED index (partial index)

CUBRID supports filtered indexes with a WHERE clause. Use the `cubrid_filtered` dialect option:

```python
Index(
    "idx_active_users", users.c.name,
    cubrid_filtered="email IS NOT NULL",
)
```

### FUNCTION-based index

CUBRID supports function-based indexes. Use the `cubrid_function` dialect option:

```python
Index(
    "idx_users_lower_name", users.c.name,
    cubrid_function="LOWER(name)",
)
```

### Composite index

```python
Index("idx_users_name_email", users.c.name, users.c.email)
```

### Dropping an index

CUBRID requires the table name when dropping an index:

```sql
DROP INDEX idx_users_email ON users
```

The dialect handles this automatically.

## Table Comments

```python
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
    comment="User accounts table",
)
```

Generated DDL appends the comment:

```sql
CREATE TABLE users (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(100),
    PRIMARY KEY (id)
) COMMENT='User accounts table'
```

### Altering table comments

```python
from sqlalchemy import inspect

# Via DDL
with engine.connect() as conn:
    conn.execute(text("ALTER TABLE users COMMENT='Updated comment'"))
    conn.commit()
```

## Column Comments

```python
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), comment="Full name of the user"),
    Column("email", String(200), comment="Primary email address"),
)
```

Generated DDL includes inline comments:

```sql
CREATE TABLE users (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(100) COMMENT 'Full name of the user',
    email VARCHAR(200) COMMENT 'Primary email address',
    PRIMARY KEY (id)
)
```

### Altering column comments

The dialect generates `ALTER TABLE ... MODIFY ... COMMENT ...` for column comment changes:

```sql
ALTER TABLE users MODIFY name COMMENT 'Updated column comment'
```

### Dropping comments

Setting a comment to an empty string effectively removes it:

```sql
ALTER TABLE users COMMENT=''
ALTER TABLE users MODIFY name COMMENT ''
```
