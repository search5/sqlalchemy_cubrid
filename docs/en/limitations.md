# Known Limitations

This page documents known limitations of the CUBRID dialect, differences from other databases, and SQLAlchemy test suite results.

## Identifier Handling

### All identifiers are lowercased

CUBRID normalizes all unquoted identifiers to lowercase. Table and column names are stored in lowercase regardless of how they are specified:

```python
# These all create the same table:
Table("MyTable", metadata, ...)
Table("MYTABLE", metadata, ...)
Table("mytable", metadata, ...)
# All stored as: mytable
```

!!! note
    The dialect uses double-quote (`"`) as the identifier quote character, matching CUBRID's SQL standard quoting. However, even quoted identifiers may be lowercased depending on the CUBRID server configuration.

## Date/Time Precision

### DATETIME has millisecond precision

CUBRID DATETIME stores date and time with **millisecond** (3-digit) precision, not microsecond (6-digit) as in MySQL or PostgreSQL:

```
CUBRID:     2026-03-29 12:34:56.789       (3 digits)
MySQL:      2026-03-29 12:34:56.789123    (6 digits)
PostgreSQL: 2026-03-29 12:34:56.789123    (6 digits)
```

If your Python datetime objects have microsecond values, the sub-millisecond portion will be truncated on storage.

```python
import datetime

# Python: microseconds = 789123
dt = datetime.datetime(2026, 3, 29, 12, 34, 56, 789123)

# After storage and retrieval from CUBRID: microseconds = 789000
# The last 3 digits (123) are lost
```

## AUTO_INCREMENT Limitations

### No automatic UNIQUE index

Unlike MySQL, CUBRID's AUTO_INCREMENT does **not** automatically create a UNIQUE index on the column. If uniqueness is required (and it usually is for primary keys), you must define a PRIMARY KEY or UNIQUE constraint explicitly.

```python
# Correct: PRIMARY KEY ensures uniqueness
Column("id", Integer, primary_key=True, autoincrement=True)

# Without PRIMARY KEY, AUTO_INCREMENT alone does NOT enforce uniqueness
```

### One per table

CUBRID allows only one AUTO_INCREMENT column per table. Attempting to define multiple AUTO_INCREMENT columns will result in an error.

## CHECK Constraints

### Not enforced

CUBRID parses CHECK constraints in DDL but does **not** enforce them at runtime. Data that violates a CHECK constraint will be accepted without error:

```sql
CREATE TABLE test (
    age INTEGER CHECK (age >= 0)
);

-- This succeeds even though it violates the CHECK:
INSERT INTO test (age) VALUES (-5);
```

The dialect's `get_check_constraints()` always returns an empty list because CUBRID does not store CHECK constraints in its catalog.

## Missing SQL Features

### No BOOLEAN type

CUBRID has no native BOOLEAN column type. The dialect maps `Boolean` to `SMALLINT`:

- `True` is stored as `1`
- `False` is stored as `0`

### No RETURNING clause

CUBRID does not support `INSERT ... RETURNING`, `UPDATE ... RETURNING`, or `DELETE ... RETURNING`. The dialect explicitly sets:

```python
insert_returning = False
update_returning = False
delete_returning = False
```

Last inserted ID is obtained via `cursor.lastrowid`.

### No temporary tables

CUBRID does not support `CREATE TEMPORARY TABLE` or `CREATE TEMP TABLE`. If you need temporary storage, consider using a regular table with a session-specific naming convention and cleaning up afterward.

### No RELEASE SAVEPOINT

CUBRID supports `SAVEPOINT` and `ROLLBACK TO SAVEPOINT` but does **not** support `RELEASE SAVEPOINT`. The dialect silently skips the release operation:

```python
def do_release_savepoint(self, connection, name):
    # CUBRID does not support RELEASE SAVEPOINT -- silently skip
    pass
```

This allows SQLAlchemy's nested transaction (savepoint) support to work correctly.

### No FOR SHARE

CUBRID does not support `FOR SHARE` or `LOCK IN SHARE MODE`. The dialect silently omits the clause when `with_for_update(read=True)` is used.

### No NCHAR / NCHAR VARYING

`NCHAR` and `NCHAR VARYING` were removed in CUBRID 9.0. The dialect maps:

- `NCHAR(n)` to `CHAR(n)`
- `NVARCHAR(n)` to `VARCHAR(n)`

### FLOAT precision promotion

When `FLOAT(p)` is specified with `p > 7`, CUBRID automatically promotes the type to `DOUBLE`. The dialect mirrors this behavior in the type compiler.

### Set operations use CUBRID keywords

CUBRID uses `DIFFERENCE` instead of `EXCEPT` and `INTERSECTION` instead of `INTERSECT`:

| SQL Standard   | CUBRID            |
|----------------|-------------------|
| `EXCEPT`       | `DIFFERENCE`      |
| `EXCEPT ALL`   | `DIFFERENCE ALL`  |
| `INTERSECT`    | `INTERSECTION`    |
| `INTERSECT ALL`| `INTERSECTION ALL`|

The dialect handles this automatically in the compiler.

### DDL is non-transactional

CUBRID auto-commits all DDL statements. You cannot roll back a `CREATE TABLE`, `ALTER TABLE`, or `DROP TABLE` within a transaction.

## SQLAlchemy Test Suite Results

The dialect has been tested against the SQLAlchemy standard dialect test suite with the following results:

| Category | Count |
|----------|-------|
| Passed   | 737   |
| Failed   | 18    |
| Skipped  | 878   |
| Errors   | 22    |

### Failure Categories

The 18 test failures fall into these categories:

#### Identifier lowercasing (8 failures)

CUBRID normalizes all identifiers to lowercase. Tests that expect case-preserved identifiers (e.g., `quoted_name("MixedCase")`) fail:

- `test_get_pk_constraint_quoted_name` (2 variants)
- `test_get_foreign_keys_quoted_name` (2 variants)
- `test_get_indexes_quoted_name` (2 variants)
- `test_get_unique_constraints_quoted_name` (2 variants)

#### FK parsing with parenthesized column names (6 failures)

The FK regex cannot parse column names containing parentheses (e.g., `col(3)`) in `SHOW CREATE TABLE` output:

- `BizarroCharacterTest::test_fk_ref` (6 variants with `(3)` in column names)

#### CTE INSERT not supported (1 failure)

CUBRID does not support `INSERT ... WITH ... SELECT`:

- `CTETest::test_insert_from_select_round_trip`

#### ROWS BETWEEN with bind parameters (1 failure)

CUBRID does not allow bind parameters in window frame clauses:

- `WindowFunctionTest::test_window_rows_between`

#### JSON whitespace normalization (1 failure)

CUBRID may normalize JSON whitespace on round-trip:

- `JSONTest::test_round_trip_custom_json`

#### ENUM non-ASCII (1 failure)

CUBRID's default collation (iso-8859-1) does not support non-ASCII characters in ENUM values:

- `EnumTest::test_round_trip_executemany`

### Error Categories (22 errors)

The 22 errors are primarily caused by:

- **Reserved word conflicts:** CUBRID treats `data` as a reserved word, causing test fixture failures
- **CTE/HasTable test fixtures:** Fixtures that use `data` as a column name without quoting

## Workarounds

### For RETURNING clause

Use `cursor.lastrowid` after an INSERT to get the auto-generated ID:

```python
with engine.connect() as conn:
    result = conn.execute(
        users.insert().values(name="Alice")
    )
    new_id = result.inserted_primary_key[0]
    conn.commit()
```

### For temporary tables

Use a regular table with cleanup:

```python
temp_name = f"tmp_{session_id}"
conn.execute(text(f"CREATE TABLE {temp_name} (id INT, data VARCHAR(100))"))
# ... use the table ...
conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
```

### For microsecond precision

Round datetime values to milliseconds before storing:

```python
import datetime

def round_to_millis(dt):
    """Round a datetime to millisecond precision."""
    micro = dt.microsecond
    millis = (micro // 1000) * 1000
    return dt.replace(microsecond=millis)
```

### For BOOLEAN columns

Use explicit integer values when needed:

```python
# Instead of True/False in raw SQL:
conn.execute(text("INSERT INTO t (active) VALUES (1)"))  # True
conn.execute(text("INSERT INTO t (active) VALUES (0)"))  # False
```
