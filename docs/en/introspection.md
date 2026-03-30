# Introspection

This page documents the Inspector methods available for reflecting CUBRID database objects. All reflection methods use `@reflection.cache` for performance.

## Overview

The CUBRID dialect provides a comprehensive set of introspection methods that let you discover database structure at runtime. These methods are accessible through SQLAlchemy's `inspect()` interface or directly via the dialect.

```python
from sqlalchemy import inspect, create_engine

engine = create_engine("cubrid://dba:@localhost:33000/testdb")
insp = inspect(engine)
```

## Table Methods

### get_table_names()

Returns a list of all user table names (excludes system tables and views):

```python
tables = insp.get_table_names()
# ['employees', 'departments', 'orders', ...]
```

The query uses:

```sql
SELECT class_name FROM db_class
WHERE is_system_class = 'NO' AND class_type = 'CLASS'
ORDER BY class_name
```

### has_table()

Checks if a specific table exists:

```python
exists = insp.has_table("employees")  # True or False
```

!!! note
    CUBRID lowercases all identifiers. The check is performed against the lowercased name.

## Column Methods

### get_columns()

Returns column information for a table. Each column is a dictionary with:

| Key               | Type     | Description                                 |
|-------------------|----------|---------------------------------------------|
| `name`            | str      | Column name                                 |
| `type`            | TypeObj  | SQLAlchemy type instance                    |
| `nullable`        | bool     | Whether NULL is allowed                     |
| `default`         | str/None | Default value expression                    |
| `autoincrement`   | bool     | Whether AUTO_INCREMENT is set               |
| `comment`         | str/None | Column comment                              |

```python
columns = insp.get_columns("employees")
for col in columns:
    print(f"{col['name']}: {col['type']} "
          f"{'NULL' if col['nullable'] else 'NOT NULL'}")
    # id: INTEGER NOT NULL
    # name: VARCHAR(100) NULL
    # salary: NUMERIC(10, 2) NULL
```

Column comments are fetched separately from the `db_attribute` catalog table.

!!! note
    CUBRID's `SHOW COLUMNS` reports `SHORT` instead of `SMALLINT` and `INTEGER` instead of `INT`. The dialect normalizes these during type parsing.

## Constraint Methods

### get_pk_constraint()

Returns the primary key constraint:

```python
pk = insp.get_pk_constraint("employees")
print(pk)
# {'constrained_columns': ['id'], 'name': 'pk_employees_id'}
```

### get_foreign_keys()

Returns foreign key constraints including ON DELETE / ON UPDATE referential actions. CUBRID does not expose FK reference information in catalog views, so the dialect parses `SHOW CREATE TABLE` output:

```python
fks = insp.get_foreign_keys("orders")
for fk in fks:
    print(fk)
# {
#     'name': 'fk_orders_customer',
#     'constrained_columns': ['customer_id'],
#     'referred_schema': None,
#     'referred_table': 'customers',
#     'referred_columns': ['id'],
#     'options': {'ondelete': 'CASCADE', 'onupdate': 'SET NULL'},
# }
```

The `options` dictionary contains `ondelete` and `onupdate` keys when the FK defines referential actions (CASCADE, SET NULL, NO ACTION, RESTRICT). If no action is specified, the key is omitted.

!!! note
    For views, `SHOW CREATE TABLE` fails. The dialect detects this and returns an empty list since views have no foreign keys.

### get_unique_constraints()

Returns unique constraints (excluding primary keys and foreign keys):

```python
uqs = insp.get_unique_constraints("employees")
for uq in uqs:
    print(uq)
# {
#     'name': 'uq_employees_email',
#     'column_names': ['email'],
#     'duplicates_index': 'uq_employees_email',
# }
```

### get_check_constraints()

CUBRID parses CHECK constraints but does **not** enforce or store them. This method always returns an empty list:

```python
checks = insp.get_check_constraints("employees")
print(checks)  # []
```

!!! warning
    Even if you define CHECK constraints in your DDL, CUBRID will accept the syntax but silently ignore the constraint. There is no catalog table for CHECK constraints.

## Index Methods

### get_indexes()

Returns index information with CUBRID-specific dialect options:

```python
indexes = insp.get_indexes("employees")
for idx in indexes:
    print(idx)
```

Each index dictionary contains:

| Key               | Type      | Description                                 |
|-------------------|-----------|---------------------------------------------|
| `name`            | str       | Index name                                  |
| `unique`          | bool      | Whether it is a unique index                |
| `column_names`    | list[str] | Indexed column names                        |
| `column_sorting`  | dict      | Column sort directions (if not ASC)         |
| `dialect_options` | dict      | CUBRID-specific options (see below)         |

#### Dialect options in get_indexes()

| Key                | Type     | Description                                  |
|--------------------|----------|----------------------------------------------|
| `cubrid_reverse`   | bool     | True if this is a reverse index              |
| `cubrid_filtered`  | str      | Filter expression for filtered indexes       |
| `cubrid_function`  | str      | Function expression for function-based indexes |

```python
indexes = insp.get_indexes("employees")
for idx in indexes:
    if idx["dialect_options"].get("cubrid_reverse"):
        print(f"{idx['name']} is a reverse index")
    if "cubrid_filtered" in idx["dialect_options"]:
        print(f"{idx['name']} filter: {idx['dialect_options']['cubrid_filtered']}")
    if "cubrid_function" in idx["dialect_options"]:
        print(f"{idx['name']} function: {idx['dialect_options']['cubrid_function']}")
```

### has_index()

Checks if a specific index exists on a table:

```python
from sqlalchemy import inspect

insp = inspect(engine)

# has_index is available via the dialect
with engine.connect() as conn:
    exists = engine.dialect.has_index(conn, "employees", "idx_emp_name")
```

## View Methods

### get_view_names()

Returns all user-defined view names:

```python
views = insp.get_view_names()
# ['active_employees', 'department_summary', ...]
```

### get_view_definition()

Returns the SQL definition of a view:

```python
definition = insp.get_view_definition("active_employees")
print(definition)
# "SELECT id, name, email FROM employees WHERE active = 1"
```

## Sequence Methods

### get_sequence_names()

Returns user-created serial names. Auto-generated serials (created for AUTO_INCREMENT columns) are excluded:

```python
sequences = insp.get_sequence_names()
# ['order_seq', 'invoice_seq']
```

!!! note
    The `db_serial` catalog table column for attribute reference was renamed from `att_name` to `attr_name` in CUBRID 11.4. The dialect handles this transparently.

### has_sequence()

Checks if a specific serial exists:

```python
exists = insp.has_sequence("order_seq")  # True or False
```

## Comment Methods

### get_table_comment()

Returns the table comment:

```python
comment = insp.get_table_comment("employees")
print(comment)
# {'text': 'Employee records table'}
# or {'text': None} if no comment is set
```

## Inheritance Methods

These methods are available on the dialect object, not directly on the Inspector.

### get_super_class_name()

Returns the parent class name if the table uses UNDER inheritance:

```python
with engine.connect() as conn:
    parent = engine.dialect.get_super_class_name(conn, "student")
    print(parent)  # "person" or None
```

### get_sub_class_names()

Returns direct child class names:

```python
with engine.connect() as conn:
    children = engine.dialect.get_sub_class_names(conn, "person")
    print(children)  # ["student", "employee"]
```

## OID Reference Methods

### get_oid_columns()

Returns OID reference columns for a table:

```python
with engine.connect() as conn:
    oid_cols = engine.dialect.get_oid_columns(conn, "department")
    for col in oid_cols:
        print(col)
    # {"name": "manager", "referenced_class": "person"}
    # {"name": "location", "referenced_class": "address"}
```

Each item contains:

| Key                 | Type | Description                              |
|---------------------|------|------------------------------------------|
| `name`              | str  | Column name                              |
| `referenced_class`  | str  | The CUBRID class that the OID points to  |

## Caching

All reflection methods are decorated with `@reflection.cache`, which means:

- Results are cached per connection using the `info_cache` dictionary
- Subsequent calls with the same arguments return cached results without hitting the database
- The cache is scoped to the Inspector instance (and its underlying connection)

```python
# These two calls hit the database only once:
tables1 = insp.get_table_names()
tables2 = insp.get_table_names()  # Returns cached result
```

## Internal Helpers

### _has_object()

Checks if a table or view exists (used internally before operations that require object existence):

```python
# Used internally, not part of the public API
# Raises NoSuchTableError if the object doesn't exist
```

### _is_view()

Checks if a name refers to a view (VCLASS in CUBRID terminology):

```python
# Used internally to handle view-specific behavior
# (e.g., views have no foreign keys)
```

### _resolve_type()

Parses CUBRID type strings from `SHOW COLUMNS` into SQLAlchemy type instances:

```python
# Internal: "VARCHAR(100)" -> VARCHAR(100)
# Internal: "NUMERIC(15,2)" -> NUMERIC(15, 2)
# Internal: "ENUM('a','b','c')" -> Enum('a', 'b', 'c')
# Internal: "SET_OF(VARCHAR(50))" -> CubridSet("VARCHAR(50)")
# Internal: "MULTISET_OF(INTEGER)" -> CubridMultiset("INTEGER")
# Internal: "SEQUENCE_OF(VARCHAR(100))" -> CubridList("VARCHAR(100)")
```

!!! note
    Collection types (SET, MULTISET, LIST/SEQUENCE) are now reflected as `CubridSet`, `CubridMultiset`, and `CubridList` instances with the correct `element_type`, preserving full collection semantics during reflection.
