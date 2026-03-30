# CUBRID-Specific Features

This page covers features unique to CUBRID as an object-relational database: collection types, class inheritance, and OID (Object Identifier) references.

## Collection Types

CUBRID provides three collection types for storing multiple values in a single column. The `sqlalchemy_cubrid.types` module provides custom SQLAlchemy types for each.

### CubridSet

An unordered collection with no duplicates. Python values are returned as `set`.

```python
from sqlalchemy import Table, Column, Integer, MetaData
from sqlalchemy_cubrid.types import CubridSet

metadata = MetaData()

products = Table(
    "products", metadata,
    Column("id", Integer, primary_key=True),
    Column("tags", CubridSet("VARCHAR(50)")),
)
```

Generated DDL:

```sql
CREATE TABLE products (
    id INTEGER AUTO_INCREMENT,
    tags SET_OF(VARCHAR(50)),
    PRIMARY KEY (id)
)
```

Inserting and querying:

```python
with engine.connect() as conn:
    conn.execute(
        products.insert().values(id=1, tags={"python", "database", "orm"})
    )
    conn.commit()

    row = conn.execute(products.select().where(products.c.id == 1)).first()
    print(row.tags)       # {'python', 'database', 'orm'}
    print(type(row.tags)) # <class 'set'>
```

### CubridMultiset

An unordered collection that allows duplicates. Python values are returned as `list`.

```python
from sqlalchemy_cubrid.types import CubridMultiset

scores = Table(
    "scores", metadata,
    Column("id", Integer, primary_key=True),
    Column("values", CubridMultiset("INTEGER")),
)
```

Generated DDL:

```sql
values MULTISET_OF(INTEGER)
```

### CubridList

An ordered collection that allows duplicates (also known as SEQUENCE in CUBRID). Python values are returned as `list`.

```python
from sqlalchemy_cubrid.types import CubridList

history = Table(
    "history", metadata,
    Column("id", Integer, primary_key=True),
    Column("events", CubridList("VARCHAR(200)")),
)
```

Generated DDL:

```sql
events SEQUENCE_OF(VARCHAR(200))
```

!!! note
    CUBRID uses `SEQUENCE_OF` DDL syntax internally. `LIST` and `SEQUENCE` are synonyms in CUBRID. The dialect uses `SEQUENCE_OF` for DDL generation because CUBRID does not support the `LIST_OF` syntax.

### Element type parameter

The element type is passed as a string matching CUBRID DDL syntax:

```python
CubridSet("VARCHAR(100)")
CubridSet("INTEGER")
CubridSet("DOUBLE")
CubridMultiset("VARCHAR(1073741823)")  # STRING equivalent
CubridList("NUMERIC(10,2)")
```

If no element type is specified, it defaults to `VARCHAR(1073741823)`.

### Binary format parsing

pycubrid returns collection values in a raw binary format. The dialect includes an automatic parser (`_parse_collection_bytes`) that decodes the wire format:

- 4 bytes: type identifier (little-endian)
- 4 bytes: element count (little-endian)
- Per element: 1 byte size + data bytes + 3-byte padding (last element has no padding)

This parsing is handled transparently in the `result_processor` of each collection type.

## Class Inheritance (UNDER)

CUBRID is an object-relational database that supports class inheritance. A child table created with `UNDER` inherits all columns from its parent table.

### Creating an inherited table

```python
from sqlalchemy_cubrid import CreateTableUnder

# First, create the parent table normally
parent = Table(
    "person", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
)
metadata.create_all(engine)

# Then create a child table that inherits from person
child_ddl = CreateTableUnder(
    "student",       # child table name
    "person",        # parent table name
    Column("grade", Integer),
    Column("school", String(100)),
)

with engine.connect() as conn:
    conn.execute(child_ddl)
    conn.commit()
```

Generated DDL:

```sql
CREATE TABLE student UNDER person (
    grade INTEGER,
    school VARCHAR(100)
)
```

The `student` table automatically has `id` and `name` columns inherited from `person`, plus its own `grade` and `school` columns.

### Dropping an inherited table

```python
from sqlalchemy_cubrid import DropTableInheritance

drop_ddl = DropTableInheritance("student")

with engine.connect() as conn:
    conn.execute(drop_ddl)
    conn.commit()
```

Generated DDL:

```sql
DROP TABLE IF EXISTS student
```

### Querying inheritance metadata

#### get_super_class()

Returns the parent class name, or `None` if the table has no parent:

```python
from sqlalchemy_cubrid import get_super_class

with engine.connect() as conn:
    parent = get_super_class(conn, "student")
    print(parent)  # "person"

    parent = get_super_class(conn, "person")
    print(parent)  # None
```

#### get_sub_classes()

Returns a list of direct child class names:

```python
from sqlalchemy_cubrid import get_sub_classes

with engine.connect() as conn:
    children = get_sub_classes(conn, "person")
    print(children)  # ["student"]
```

#### get_inherited_columns()

Returns column information with inheritance source:

```python
from sqlalchemy_cubrid import get_inherited_columns

with engine.connect() as conn:
    columns = get_inherited_columns(conn, "student")
    for col in columns:
        print(col)
    # {"name": "id", "from_class": "person", "def_order": 0}
    # {"name": "name", "from_class": "person", "def_order": 1}
    # {"name": "grade", "from_class": None, "def_order": 2}
    # {"name": "school", "from_class": None, "def_order": 3}
```

Columns with `from_class=None` are local (defined directly on the child table). Columns with a `from_class` value are inherited from that parent class.

### Inspector integration

The dialect also provides these methods on the Inspector object:

```python
from sqlalchemy import inspect

insp = inspect(engine)

# Get parent class name
parent = insp.dialect.get_super_class_name(conn, "student")

# Get child class names
children = insp.dialect.get_sub_class_names(conn, "person")
```

## OID References

In CUBRID, every row has an OID (Object Identifier). A column can reference another class by using that class name as the column type, storing OID references to instances of the referenced class.

### CubridOID type

The `CubridOID` type represents an OID reference column:

```python
from sqlalchemy_cubrid import CubridOID

department = Table(
    "department", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
    Column("manager", CubridOID("person")),
)
```

Generated DDL:

```sql
CREATE TABLE department (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(100),
    manager person,
    PRIMARY KEY (id)
)
```

The `manager` column stores OID references to rows in the `person` table.

!!! warning
    Only tables created with `DONT_REUSE_OID` can be referenced by OID columns. Since CUBRID 10.x, the default is `REUSE_OID`, so you must explicitly set `DONT_REUSE_OID` on referenced tables.

### CreateTableDontReuseOID

A DDL construct for creating tables that can be referenced by OID:

```python
from sqlalchemy_cubrid import CreateTableDontReuseOID
from sqlalchemy import Column, Integer, String

ddl = CreateTableDontReuseOID(
    "person",
    Column("id", Integer, primary_key=True),
    Column("name", String(50)),
)

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

Generated DDL:

```sql
CREATE TABLE person (id INTEGER, name VARCHAR(50)) DONT_REUSE_OID
```

You can also use the table dialect option:

```python
person = Table(
    "person", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(50)),
    cubrid_dont_reuse_oid=True,
)
```

### deref() -- Path Expressions

CUBRID allows navigating OID references using dot notation (path expressions). The `deref()` function creates these expressions:

```python
from sqlalchemy_cubrid import deref
from sqlalchemy import select, literal_column, text

# Single-level dereference
# SQL: SELECT manager.name FROM department
stmt = select(
    deref(literal_column("manager"), "name")
).select_from(text("department"))

with engine.connect() as conn:
    result = conn.execute(stmt)
    for row in result:
        print(row[0])  # The manager's name
```

### Chained dereferencing

For multi-level OID references, chain `deref()` calls:

```python
# If department.manager -> person, and person.address -> address_table
# SQL: SELECT manager.address.city FROM department
stmt = select(
    deref(deref(literal_column("manager"), "address"), "city")
).select_from(text("department"))
```

This compiles to:

```sql
SELECT manager.address.city FROM department
```

### Custom result type

By default, `deref()` returns `String`. Specify a type for proper Python conversion:

```python
from sqlalchemy import Integer

# Get the manager's ID (integer)
stmt = select(
    deref(literal_column("manager"), "id", type_=Integer())
).select_from(text("department"))
```

### Inspecting OID columns

Use the dialect's `get_oid_columns()` to discover OID reference columns:

```python
from sqlalchemy import inspect

insp = inspect(engine)

with engine.connect() as conn:
    oid_cols = insp.dialect.get_oid_columns(conn, "department")
    for col in oid_cols:
        print(col)
    # {"name": "manager", "referenced_class": "person"}
```

## Partitioning

CUBRID supports RANGE, HASH, and LIST partitioning. The dialect provides DDL constructs for partitioning existing tables.

### RANGE Partitioning

```python
from sqlalchemy_cubrid import PartitionByRange, RangePartition

ddl = PartitionByRange("orders", "order_date", [
    RangePartition("p2024", "'2025-01-01'"),
    RangePartition("p2025", "'2026-01-01'"),
    RangePartition("pmax", "MAXVALUE"),
])

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

Generated SQL:

```sql
ALTER TABLE "orders" PARTITION BY RANGE ("order_date") (
    PARTITION "p2024" VALUES LESS THAN ('2025-01-01'),
    PARTITION "p2025" VALUES LESS THAN ('2026-01-01'),
    PARTITION "pmax" VALUES LESS THAN (MAXVALUE)
)
```

### HASH Partitioning

```python
from sqlalchemy_cubrid import PartitionByHash

ddl = PartitionByHash("orders", "id", 4)

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

Generated SQL:

```sql
ALTER TABLE "orders" PARTITION BY HASH ("id") PARTITIONS 4
```

### LIST Partitioning

```python
from sqlalchemy_cubrid import PartitionByList, ListPartition

ddl = PartitionByList("orders", "region", [
    ListPartition("p_east", ["'east'", "'northeast'"]),
    ListPartition("p_west", ["'west'", "'southwest'"]),
])

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

Generated SQL:

```sql
ALTER TABLE "orders" PARTITION BY LIST ("region") (
    PARTITION "p_east" VALUES IN ('east', 'northeast'),
    PARTITION "p_west" VALUES IN ('west', 'southwest')
)
```

## DBLINK (11.2+)

CUBRID 11.2 introduced DBLINK for querying remote CUBRID databases.

### Creating a remote server

```python
from sqlalchemy_cubrid import CreateServer, DropServer

ddl = CreateServer(
    "remote_srv",
    host="192.168.1.10",
    port=33000,
    dbname="demodb",
    user="dba",
    password="",
)

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

Generated SQL:

```sql
CREATE SERVER "remote_srv" (
    HOST='192.168.1.10', PORT=33000, DBNAME='demodb', USER='dba', PASSWORD=''
)
```

### Dropping a server

```python
from sqlalchemy_cubrid import DropServer

with engine.connect() as conn:
    conn.execute(DropServer("remote_srv"))
    conn.commit()
```

### Using DBLINK in queries

The `DbLink` helper generates a FROM-clause fragment for use with `text()`:

```python
from sqlalchemy_cubrid import DbLink
from sqlalchemy import text

link = DbLink(
    "remote_srv",
    "SELECT id, name FROM employees",
    columns=[("id", "INT"), ("name", "VARCHAR(100)")],
)

with engine.connect() as conn:
    result = conn.execute(text(
        f"SELECT * FROM {link.as_text('t')}"
    ))
```

Generated SQL:

```sql
SELECT * FROM DBLINK(remote_srv, 'SELECT id, name FROM employees')
    AS t(id INT, name VARCHAR(100))
```

!!! note
    DBLINK requires CUBRID 11.2 or later. The remote database must also be a CUBRID instance.

## Import Reference

```python
# Collection types
from sqlalchemy_cubrid.types import CubridSet, CubridMultiset, CubridList

# Inheritance
from sqlalchemy_cubrid import (
    CreateTableUnder,
    DropTableInheritance,
    get_super_class,
    get_sub_classes,
    get_inherited_columns,
)

# OID references
from sqlalchemy_cubrid import (
    CubridOID,
    deref,
    CreateTableDontReuseOID,
)

# Partitioning
from sqlalchemy_cubrid import (
    PartitionByRange,
    PartitionByHash,
    PartitionByList,
    RangePartition,
    HashPartition,
    ListPartition,
)

# DBLINK (11.2+)
from sqlalchemy_cubrid import CreateServer, DropServer, DbLink
```
