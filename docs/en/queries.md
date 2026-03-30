# Advanced Queries

This page covers CUBRID-specific query constructs: hierarchical queries (CONNECT BY), MERGE statement, and click counter functions.

## Hierarchical Queries (CONNECT BY)

CUBRID supports Oracle-style hierarchical queries for traversing tree-structured data. The `sqlalchemy_cubrid` package provides a complete set of constructs for building these queries.

### Basic example

Given an `employees` table with a self-referencing `manager_id` column:

```python
from sqlalchemy import Table, Column, Integer, String, MetaData

metadata = MetaData()
emp = Table(
    "employees", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
    Column("manager_id", Integer),
)
```

Query the hierarchy:

```python
from sqlalchemy_cubrid import HierarchicalSelect, prior, level_col

stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.id, emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)

with engine.connect() as conn:
    result = conn.execute(stmt)
    for row in result:
        print("  " * (row[2] - 1) + row[1])
```

Generated SQL:

```sql
SELECT employees.id, employees.name, LEVEL
FROM employees
START WITH employees.manager_id IS NULL
CONNECT BY PRIOR employees.id = employees.manager_id
```

### HierarchicalSelect parameters

| Parameter            | Type              | Description                                    |
|----------------------|-------------------|------------------------------------------------|
| `table`              | Table             | The source table                               |
| `columns`            | list              | Columns to select                              |
| `connect_by`         | expression        | The CONNECT BY condition (must include `prior()`) |
| `start_with`         | expression        | Root row filter condition                      |
| `where`              | expression        | Additional WHERE filter (applied before traversal) |
| `order_siblings_by`  | list              | Order siblings at each level                   |
| `nocycle`            | bool              | Prevent infinite loops in cyclic data          |

### prior()

Marks a column as the "prior" (parent) side of the hierarchical relationship:

```python
from sqlalchemy_cubrid import prior

# Parent's id matches child's manager_id
connect_by = (prior(emp.c.id) == emp.c.manager_id)
```

### level_col()

Returns the `LEVEL` pseudo-column, which indicates the depth in the hierarchy (1 for root):

```python
from sqlalchemy_cubrid import level_col

stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

### sys_connect_by_path()

Builds a path string from root to current node:

```python
from sqlalchemy_cubrid import sys_connect_by_path

stmt = HierarchicalSelect(
    emp,
    columns=[
        emp.c.name,
        sys_connect_by_path(emp.c.name, "/"),
    ],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

Generated SQL includes:

```sql
SYS_CONNECT_BY_PATH(employees.name, '/')
```

!!! note
    CUBRID requires the separator to be a string literal, not a bind parameter. The dialect handles this automatically.

### connect_by_root()

Returns the root node's column value for each row in the hierarchy:

```python
from sqlalchemy_cubrid import connect_by_root

stmt = HierarchicalSelect(
    emp,
    columns=[
        emp.c.name,
        connect_by_root(emp.c.name),  # Root employee name
    ],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

### connect_by_isleaf()

Returns 1 if the current row is a leaf node (has no children), 0 otherwise:

```python
from sqlalchemy_cubrid import connect_by_isleaf

stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, connect_by_isleaf()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

### connect_by_iscycle()

Returns 1 if the current row causes a cycle. Requires `nocycle=True`:

```python
from sqlalchemy_cubrid import connect_by_iscycle

stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, connect_by_iscycle()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
    nocycle=True,
)
```

### NOCYCLE

Prevents infinite loops when data contains cycles:

```python
stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
    nocycle=True,
)
```

Generated SQL:

```sql
CONNECT BY NOCYCLE PRIOR employees.id = employees.manager_id
```

### ORDER SIBLINGS BY

Order rows at the same level of the hierarchy:

```python
stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
    order_siblings_by=[emp.c.name],
)
```

Generated SQL:

```sql
... ORDER SIBLINGS BY employees.name
```

### rownum()

Returns the `ROWNUM` pseudo-column, which provides sequential row numbers in the result set starting from 1. Available in both hierarchical and regular queries in CUBRID:

```python
from sqlalchemy_cubrid import rownum

stmt = HierarchicalSelect(
    emp,
    columns=[rownum(), emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

Generated SQL includes:

```sql
SELECT ROWNUM, employees.name, LEVEL FROM employees ...
```

### WHERE clause

Filter rows before the hierarchical traversal:

```python
stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
    where=(emp.c.name != "Intern"),
)
```

## MERGE Statement

CUBRID supports the SQL MERGE statement for conditional insert/update (upsert based on a source table or subquery).

### Basic example

```python
from sqlalchemy_cubrid import Merge

stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_matched_then_update({
        target_table.c.name: source_table.c.name,
        target_table.c.value: source_table.c.value,
    })
    .when_not_matched_then_insert({
        target_table.c.id: source_table.c.id,
        target_table.c.name: source_table.c.name,
        target_table.c.value: source_table.c.value,
    })
)

with engine.connect() as conn:
    conn.execute(stmt)
    conn.commit()
```

Generated SQL:

```sql
MERGE INTO target_table
USING source_table
ON (target_table.id = source_table.id)
WHEN MATCHED THEN UPDATE SET
    target_table.name = source_table.name,
    target_table.value = source_table.value
WHEN NOT MATCHED THEN INSERT (target_table.id, target_table.name, target_table.value)
    VALUES (source_table.id, source_table.name, source_table.value)
```

### Merge API

| Method                                     | Description                                      |
|--------------------------------------------|--------------------------------------------------|
| `Merge(target)`                            | Create a MERGE targeting the given table         |
| `.using(source)`                           | Set the source table or subquery                 |
| `.on(condition)`                           | Set the join condition                           |
| `.when_matched_then_update(dict, condition=)` | SET clause for matched rows (optional AND condition) |
| `.when_matched_then_delete(condition=)`    | DELETE matched rows (optional AND condition)     |
| `.when_not_matched_then_insert(dict, condition=)` | INSERT clause for unmatched rows (optional AND condition) |

### WHEN MATCHED THEN DELETE

Delete matched rows instead of updating them:

```python
stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_matched_then_delete()
)
```

Generated SQL:

```sql
MERGE INTO target_table USING source_table
ON (target_table.id = source_table.id)
WHEN MATCHED THEN DELETE
```

### Conditional WHEN clauses

Add conditions to WHEN clauses using the `condition=` parameter:

```python
stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_matched_then_update(
        {target_table.c.name: source_table.c.name},
        condition=source_table.c.active == 1,
    )
    .when_matched_then_delete(
        condition=source_table.c.active == 0,
    )
    .when_not_matched_then_insert(
        {target_table.c.id: source_table.c.id,
         target_table.c.name: source_table.c.name},
    )
)
```

Generated SQL:

```sql
MERGE INTO target_table USING source_table
ON (target_table.id = source_table.id)
WHEN MATCHED AND source_table.active = ? THEN UPDATE SET ...
WHEN MATCHED AND source_table.active = ? THEN DELETE
WHEN NOT MATCHED THEN INSERT (...) VALUES (...)
```

### Update only (no insert)

```python
stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_matched_then_update({
        target_table.c.name: source_table.c.name,
    })
)
```

### Insert only (no update)

```python
stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_not_matched_then_insert({
        target_table.c.id: source_table.c.id,
        target_table.c.name: source_table.c.name,
    })
)
```

## Click Counter Functions

CUBRID provides atomic increment and decrement functions that work within `SELECT` statements. These are unique to CUBRID and are used for implementing view counters, like counts, etc.

### INCR()

Atomically increments an integer column by 1 and returns the value **before** the increment:

```python
from sqlalchemy import select
from sqlalchemy_cubrid import incr

stmt = select(incr(articles.c.view_count)).where(articles.c.id == 42)

with engine.connect() as conn:
    result = conn.execute(stmt)
    old_count = result.scalar()
    conn.commit()
```

Generated SQL:

```sql
SELECT INCR(articles.view_count) FROM articles WHERE articles.id = ?
```

### DECR()

Atomically decrements an integer column by 1 and returns the value **before** the decrement:

```python
from sqlalchemy_cubrid import decr

stmt = select(decr(articles.c.view_count)).where(articles.c.id == 42)
```

### Click counter constraints

!!! warning
    - Click counters only work on `SMALLINT`, `INT`, and `BIGINT` columns.
    - The result set **must** contain exactly one row.
    - Click counters combine a SELECT and an UPDATE into a single atomic operation.

## Built-in Functions

The dialect registers CUBRID-specific built-in functions as `GenericFunction` classes for proper type inference:

### NVL / IFNULL

```python
from sqlalchemy import func, select

# NVL(expr, default) -- returns default when expr is NULL
stmt = select(func.nvl(users.c.nickname, users.c.name))

# IFNULL(expr, default) -- alias for NVL
stmt = select(func.ifnull(users.c.nickname, "Anonymous"))
```

### NVL2

```python
# NVL2(expr, not_null_val, null_val)
stmt = select(func.nvl2(users.c.email, "Has email", "No email"))
```

### DECODE

```python
# DECODE(expr, search1, result1, ..., default)
stmt = select(func.decode(users.c.status, 1, "Active", 2, "Inactive", "Unknown"))
```

### IF

```python
# IF(condition, true_val, false_val)
stmt = select(func.if_(users.c.age >= 18, "Adult", "Minor"))
```

### GROUP_CONCAT

```python
# GROUP_CONCAT(expr) -- concatenate values in a group
stmt = select(func.group_concat(users.c.name)).group_by(users.c.department)
```

## Import Reference

All query constructs are available from the top-level package:

```python
from sqlalchemy_cubrid import (
    # Hierarchical queries
    HierarchicalSelect,
    prior,
    level_col,
    sys_connect_by_path,
    connect_by_root,
    connect_by_isleaf,
    connect_by_iscycle,
    rownum,
    # MERGE
    Merge,
    # Click counters
    incr,
    decr,
    # Built-in functions
    group_concat,
    nvl,
    nvl2,
    decode,
    if_,
    ifnull,
)
```
