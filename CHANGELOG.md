# Changelog — sqlalchemy-cubrid

All notable changes to this project are documented in this file.

---

## 0.4.2 — CONNECT BY & MERGE (2026-03-28)

### CONNECT BY (Hierarchical Query)

CUBRID supports Oracle-style hierarchical queries. Added `HierarchicalSelect` construct and helper functions.

**New file:** `sqlalchemy_cubrid/hierarchical.py`

**Constructs:**

| Construct | Description | Generated SQL |
|---|---|---|
| `HierarchicalSelect(table, ...)` | Hierarchical SELECT statement | `SELECT ... FROM ... START WITH ... CONNECT BY ...` |
| `prior(column)` | Parent-row reference in CONNECT BY | `PRIOR column` |
| `level_col()` | Hierarchy depth pseudo-column | `LEVEL` |
| `sys_connect_by_path(col, sep)` | Full path from root to current row | `SYS_CONNECT_BY_PATH(col, 'sep')` |
| `connect_by_root(column)` | Root ancestor's column value | `CONNECT_BY_ROOT column` |
| `connect_by_isleaf()` | Leaf node indicator (1/0) | `CONNECT_BY_ISLEAF` |
| `connect_by_iscycle()` | Cycle indicator (requires NOCYCLE) | `CONNECT_BY_ISCYCLE` |

**Usage:**

```python
from sqlalchemy_cubrid.hierarchical import (
    HierarchicalSelect, prior, level_col,
    sys_connect_by_path, connect_by_root, connect_by_isleaf,
)

stmt = HierarchicalSelect(
    tree_table,
    columns=[tree_table.c.id, tree_table.c.name, level_col()],
    connect_by=prior(tree_table.c.id) == tree_table.c.parent_id,
    start_with=tree_table.c.parent_id == None,
    order_siblings_by=[tree_table.c.name],
    nocycle=False,
)
rows = conn.execute(stmt).fetchall()
```

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `table` | `Table` | Source table |
| `columns` | `list` | Columns to select (can include `level_col()`, `connect_by_root()`, etc.) |
| `connect_by` | `ClauseElement` | CONNECT BY condition (use `prior()` for parent reference) |
| `start_with` | `ClauseElement` | Root row condition (optional) |
| `where` | `ClauseElement` | Additional WHERE filter (optional) |
| `order_siblings_by` | `list` | Sort order within same-level siblings (optional) |
| `nocycle` | `bool` | Enable NOCYCLE to handle cyclic data (default: `False`) |

**CUBRID-specific notes:**

- `SYS_CONNECT_BY_PATH` requires the separator to be a **string literal**, not a bind parameter. The construct handles this automatically.
- `CONNECT_BY_ISCYCLE` is only valid when `nocycle=True`.
- CUBRID does not support `CONNECT BY LEVEL + 1 < N` (arithmetic expressions in CONNECT BY).

**Tests:** `tests/test_hierarchical.py` (13 tests)

### MERGE Statement

Added `Merge` construct for CUBRID's conditional INSERT/UPDATE statement.

**New file:** `sqlalchemy_cubrid/merge.py`

**Usage:**

```python
from sqlalchemy_cubrid.merge import Merge

stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_matched_then_update({
        target_table.c.name: source_table.c.name,
        target_table.c.score: source_table.c.score,
    })
    .when_not_matched_then_insert({
        target_table.c.id: source_table.c.id,
        target_table.c.name: source_table.c.name,
        target_table.c.score: source_table.c.score,
    })
)
conn.execute(stmt)
```

**Generated SQL:**

```sql
MERGE INTO target_table
USING source_table
ON (target_table.id = source_table.id)
WHEN MATCHED THEN UPDATE SET target_table.name = source_table.name, target_table.score = source_table.score
WHEN NOT MATCHED THEN INSERT (id, name, score) VALUES (source_table.id, source_table.name, source_table.score)
```

**API:**

| Method | Description |
|---|---|
| `Merge(target)` | Create MERGE targeting `target` table |
| `.using(source)` | Set USING source (table or subquery) |
| `.on(condition)` | Set ON join condition |
| `.when_matched_then_update(values)` | Set UPDATE clause (`dict` of column: expression) |
| `.when_not_matched_then_insert(values)` | Set INSERT clause (`dict` of column: expression) |

Both `when_matched_then_update` and `when_not_matched_then_insert` are individually optional, but at least one must be present.

**Tests:** `tests/test_merge.py` (8 tests)

---

## 0.4.1 — SERIAL & CLICK COUNTER (2026-03-28)

### SERIAL (Sequence)

CUBRID uses `SERIAL` instead of the SQL standard `SEQUENCE`. Mapped SQLAlchemy's built-in `Sequence` class to CUBRID SERIAL syntax.

**Modified files:** `dialect.py`, `compiler.py`, `base.py`

**Dialect flags:**

```python
supports_sequences = True
sequences_optional = False
default_sequence_base = 1
```

**DDL mapping (SQLAlchemy -> CUBRID):**

| SQLAlchemy | CUBRID |
|---|---|
| `CREATE SEQUENCE` | `CREATE SERIAL` |
| `DROP SEQUENCE` | `DROP SERIAL IF EXISTS` |
| `NEXTVAL FOR seq` | `seq.NEXT_VALUE` |

**Sequence options supported:** `START WITH`, `INCREMENT BY`, `MINVALUE`/`NOMINVALUE`, `MAXVALUE`/`NOMAXVALUE`, `CYCLE`/`NOCYCLE`, `CACHE`/`NOCACHE`

**Usage:**

```python
from sqlalchemy import Sequence, Column, Integer, Table, MetaData

seq = Sequence("user_id_seq", start=1000, increment=1)
metadata = MetaData()
users = Table("users", metadata,
    Column("id", Integer, seq, primary_key=True),
    Column("name", String(50)),
)
metadata.create_all(engine)

# Insert auto-generates id from serial
conn.execute(users.insert().values(name="alice"))  # id = 1000
conn.execute(users.insert().values(name="bob"))    # id = 1001

# Manual next_value
val = conn.execute(seq.next_value()).scalar()
```

**Introspection:**

| Inspector method | Implementation |
|---|---|
| `get_sequence_names()` | `SELECT name FROM db_serial WHERE attr_name IS NULL` |
| `has_sequence(name)` | `SELECT COUNT(*) FROM db_serial WHERE name = :name AND attr_name IS NULL` |

The `attr_name IS NULL` filter excludes auto-generated serials that CUBRID creates internally for AUTO_INCREMENT columns.

**Execution context:** `CubridExecutionContext.fire_sequence()` pre-executes `SELECT serial_name.NEXT_VALUE` before INSERT to obtain the generated ID (since CUBRID has no RETURNING clause).

**Tests:** `tests/test_serial.py` (13 tests)

### CLICK COUNTER (INCR/DECR)

CUBRID's Click Counter is a set of SQL functions that atomically increment/decrement integer columns within a SELECT statement. Designed for page view counters, read counts, etc.

**New file:** `sqlalchemy_cubrid/functions.py`

**Functions:**

| Function | SQL | Description |
|---|---|---|
| `incr(column)` | `INCR(column)` | Atomically increment by 1, return old value |
| `decr(column)` | `DECR(column)` | Atomically decrement by 1, return old value |

**Usage:**

```python
from sqlalchemy import select
from sqlalchemy_cubrid.functions import incr, decr

# Increment read_count and get old value in one query
stmt = select(board.c.title, incr(board.c.read_count)).where(board.c.id == 1)
row = conn.execute(stmt).fetchone()
# row = ("Post Title", 0)  -- returns value *before* increment
# Database now stores: read_count = 1
```

**Restrictions (CUBRID behavior):**

- Only works on `SMALLINT`, `INT`, `BIGINT` columns
- Result set must contain **exactly one row** (multi-row results cause an error)
- The increment/decrement operates as a system "top operation", **independent of transaction COMMIT/ROLLBACK**
- Overflow resets to 0 (does not error)

**Tests:** `tests/test_click_counter.py` (8 tests)

---

## 0.4.0 — Collection Types (prior to this session)

### SET, MULTISET, LIST

Custom SQLAlchemy types for CUBRID collection columns.

**File:** `sqlalchemy_cubrid/types.py`

| Type class | SQL | Python type | Behavior |
|---|---|---|---|
| `CubridSet(element_type)` | `SET VARCHAR(50)` | `set` | Unordered, no duplicates |
| `CubridMultiset(element_type)` | `MULTISET INT` | `list` | Unordered, duplicates allowed |
| `CubridList(element_type)` | `LIST VARCHAR(50)` | `list` | Ordered, duplicates allowed |

**Tests:** `tests/test_collection_types.py` (10 tests)

---

## 0.3.x — SQL Compiler (prior to this session)

### 0.3.0 — ORM CRUD & LIMIT/OFFSET

- `CubridCompiler` handles SELECT, INSERT, UPDATE, DELETE
- LIMIT / OFFSET native support
- **Tests:** `tests/test_orm_crud.py` (9 tests)

### 0.3.1 — String/Date Functions & JOINs

- String functions: CONCAT, UPPER, LOWER, LENGTH, SUBSTR, TRIM, REPLACE
- Date functions: NOW(), SYS_DATE
- JOIN types: INNER, LEFT/OUTER, CROSS
- **Tests:** `tests/test_sql_features.py` (13 tests)

### 0.3.2 — Complex Queries

- Subqueries: scalar, IN, EXISTS, derived tables
- GROUP BY / HAVING / ORDER BY
- Set operations mapped to CUBRID keywords:

| SQLAlchemy | CUBRID |
|---|---|
| `EXCEPT` | `DIFFERENCE` |
| `EXCEPT ALL` | `DIFFERENCE ALL` |
| `INTERSECT` | `INTERSECTION` |
| `INTERSECT ALL` | `INTERSECTION ALL` |

- **Tests:** `tests/test_complex_queries.py` (15 tests)

---

## 0.2.x — DDL & Type System (prior to this session)

### 0.2.0 — DDL & Basic Types

- `CubridDDLCompiler`: CREATE TABLE, DROP TABLE
- `CubridTypeCompiler`: basic type mappings
- AUTO_INCREMENT support for integer primary keys
- **Tests:** `tests/test_ddl.py` (7 tests)

**Type mappings (CubridTypeCompiler):**

| SQLAlchemy type | CUBRID SQL | Notes |
|---|---|---|
| `Boolean` | `SMALLINT` | CUBRID has no BOOLEAN column type |
| `Text` | `STRING` | STRING = VARCHAR(1,073,741,823) |
| `FLOAT(p>7)` | `DOUBLE` | CUBRID auto-promotes FLOAT with precision > 7 |
| `LargeBinary` | `BIT VARYING(1073741823)` | Inline binary storage |
| `DATETIME` | `DATETIME` | Millisecond precision (3 digits, not microseconds) |
| Other standard types | Pass-through | INTEGER, BIGINT, VARCHAR, CHAR, etc. |

### 0.2.1 — Date/Time & LOB Types

- DATETIME, TIMESTAMP, DATE, TIME mapping
- BLOB, CLOB mapping
- BIT, BIT VARYING mapping
- **Tests:** `tests/test_types.py` (4 tests)

### 0.2.2 — Constraints

- BOOLEAN -> SMALLINT round-trip
- ENUM type support
- NULL/NOT NULL, DEFAULT constraints
- **Tests:** `tests/test_constraints.py` (6 tests)

---

## 0.1.x — Connection & Introspection (prior to this session)

### 0.1.0 — DB Connection

- `import_dbapi()` (SQLAlchemy 2.x compatible)
- `create_connect_args()` with URL parameter parsing -> `CUBRID:host:port:database:::` DSN format
- `CubridExecutionContext` with autocommit detection and `get_lastrowid()`
- Python 2 `super()` calls cleaned up
- Docker-based test environment (`docker-compose.yml` with `cubrid/cubrid:11.4`)
- **Tests:** `tests/test_connection.py` (3 tests)

### 0.1.1 — Basic Introspection

- `has_table()` via `db_class` catalog
- `get_table_names()` via `db_class` catalog
- **Tests:** `tests/test_introspection.py` (6 tests)

### 0.1.2 — Schema Reflection

- `get_columns()` via `SHOW COLUMNS FROM`
- `get_pk_constraint()` via `db_index` + `db_index_key`
- `get_foreign_keys()` by parsing `SHOW CREATE TABLE` DDL
- `get_indexes()` via `db_index` + `db_index_key` (excludes PK and FK indexes)
- **Tests:** `tests/test_reflection.py` (14 tests)

---

## Architecture

### Module Structure

```
sqlalchemy_cubrid/
  __init__.py          — Package entry, dialect registry, public exports
  dialect.py           — CubridDialect (connection, introspection, type map)
  compiler.py          — CubridCompiler, CubridDDLCompiler, CubridTypeCompiler
  base.py              — CubridIdentifierPreparer, CubridExecutionContext, reserved words
  types.py             — NUMERIC, CubridSet, CubridMultiset, CubridList
  functions.py         — incr(), decr() click counter functions
  hierarchical.py      — HierarchicalSelect, prior(), level_col(), etc.
  merge.py             — Merge statement construct
```

### CUBRID System Catalog Tables Used

| Table | Purpose |
|---|---|
| `db_class` | `has_table()`, `get_table_names()` |
| `db_index` + `db_index_key` | `get_pk_constraint()`, `get_indexes()` |
| `db_serial` | `get_sequence_names()`, `has_sequence()` |

### CUBRID-Specific Design Decisions

1. **CUBRID syntax priority**: When both standard SQL and CUBRID-native syntax are valid, CUBRID syntax is used (e.g., `DIFFERENCE` instead of `EXCEPT`, `SERIAL` instead of `SEQUENCE`).

2. **No RETURNING**: CUBRID does not support `INSERT ... RETURNING`. For auto-generated IDs, `LAST_INSERT_ID()` is used for AUTO_INCREMENT, and `serial.NEXT_VALUE` is pre-executed for SERIAL-based defaults.

3. **Parameter style**: CUBRID uses `qmark` (`?`) parameter placeholders.

4. **SYS_CONNECT_BY_PATH separator**: CUBRID requires the separator argument to be a string literal, not a bind parameter. The `sys_connect_by_path` construct handles this by embedding the separator directly in the SQL string.

5. **Foreign key introspection**: CUBRID does not expose FK reference info in catalog views. `get_foreign_keys()` parses the DDL output of `SHOW CREATE TABLE`.

---

## Test Summary

| Test file | Tests | Version | Scope |
|---|---|---|---|
| `test_connection.py` | 3 | 0.1.0 | DB connection, raw SQL, server version |
| `test_introspection.py` | 6 | 0.1.1 | has_table, get_table_names |
| `test_reflection.py` | 14 | 0.1.2 | get_columns, PK, FK, indexes |
| `test_ddl.py` | 7 | 0.2.0 | CREATE/DROP TABLE, types, AUTO_INCREMENT |
| `test_types.py` | 4 | 0.2.1 | DATETIME, DATE, BLOB, BIT round-trip |
| `test_constraints.py` | 6 | 0.2.2 | BOOLEAN, ENUM, NULL, DEFAULT |
| `test_orm_crud.py` | 9 | 0.3.0 | ORM INSERT/SELECT/UPDATE/DELETE, LIMIT/OFFSET |
| `test_sql_features.py` | 13 | 0.3.1 | String/date functions, JOINs |
| `test_complex_queries.py` | 15 | 0.3.2 | Subqueries, GROUP BY, set operations |
| `test_collection_types.py` | 10 | 0.4.0 | SET, MULTISET, LIST |
| `test_serial.py` | 13 | 0.4.1 | SERIAL DDL, next_value, introspection |
| `test_click_counter.py` | 8 | 0.4.1 | INCR/DECR functions |
| `test_hierarchical.py` | 13 | 0.4.2 | CONNECT BY, LEVEL, SYS_CONNECT_BY_PATH |
| `test_merge.py` | 8 | 0.4.2 | MERGE UPDATE/INSERT |
| **Total** | **136** | | |
