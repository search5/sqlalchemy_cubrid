# Known Limitations

## SQLAlchemy Official Test Suite Results

**737 passed** / 18 failed / 878 skipped / 22 errors (SQLAlchemy 2.0.48, CUBRID 11.4)

### 18 Failed Tests — Categorized

| Count | Category | Root Cause | Tests |
|-------|----------|------------|-------|
| 8 | Identifier lowercasing | CUBRID DB | `ComponentReflectionTest::test_get_pk_constraint_quoted_name` (2), `test_get_foreign_keys_quoted_name` (2), `test_get_indexes_quoted_name` (2), `test_get_unique_constraints_quoted_name` (2) |
| 6 | FK parsing with parenthesized column names | SQLAlchemy core regex | `BizarroCharacterTest::test_fk_ref` — `plain-(3)`, `(2)-(3)`, `per % cent-(3)` (x2 each for composite/non-composite) |
| 1 | CTE INSERT not supported | CUBRID DB | `CTETest::test_insert_from_select_round_trip` |
| 1 | ROWS BETWEEN with bind parameters | CUBRID DB | `WindowFunctionTest::test_window_rows_between` |
| 1 | JSON whitespace normalization | CUBRID DB | `JSONTest::test_round_trip_custom_json` |
| 1 | ENUM non-ASCII (iso-8859-1) | CUBRID DB | `EnumTest::test_round_trip_executemany` |

### 22 Errors

All 22 errors occur in CTE and HasTable tests where SQLAlchemy's test fixtures
use `data` as a column name. `data` is a CUBRID reserved word and the test
framework does not quote it, causing syntax errors. This is a test fixture
issue, not a dialect bug.

---

## CUBRID Database Limitations

### Identifier Handling
- **All identifiers are stored lowercase.** Even when created with `quoted_name("MixedCase", quote=True)`, CUBRID stores and returns the name in lowercase. This causes 8 test failures in the reflection suite where mixed-case names are expected to round-trip.

### SQL Feature Gaps
- **No CTE INSERT** — `INSERT INTO ... WITH ... SELECT ...` is not supported. CTE is only supported in SELECT statements.
- **No ROWS BETWEEN with bind parameters** — Window function frame clauses like `ROWS BETWEEN ? PRECEDING AND ? FOLLOWING` reject bind parameters; only literal integers are accepted.
- **No RETURNING clause** — INSERT/UPDATE/DELETE do not support RETURNING.
- **No temporary tables** — `CREATE TEMPORARY TABLE` is not supported.
- **No RELEASE SAVEPOINT** — SAVEPOINT is supported but RELEASE SAVEPOINT is not. The dialect silently skips it.
- **No FOR SHARE** — `SELECT ... FOR UPDATE` is supported, but `FOR SHARE` / `LOCK IN SHARE MODE` is not.

### Type System
- **No BOOLEAN column type** — Mapped to SMALLINT. Works correctly but reflected type is SMALLINT, not BOOLEAN.
- **DATETIME has millisecond precision** — 3 digits, not microsecond (6 digits) like MySQL/PostgreSQL.
- **No TEXT type** — Mapped to STRING (= VARCHAR(1,073,741,823)).
- **No TINYINT** — Not available.
- **No UNSIGNED** — Not supported on any integer type.
- **FLOAT(p) with p > 7 becomes DOUBLE** — CUBRID automatically promotes single-precision floats.
- **NCHAR/NCHAR VARYING removed** — Removed since CUBRID 9.0; mapped to CHAR/VARCHAR.
- **JSON whitespace normalization** — CUBRID may reformat JSON strings, causing round-trip comparison failures for custom serializers.
- **ENUM non-ASCII** — Default collation (iso-8859-1) does not support multi-byte characters in ENUM values.

### DDL Constraints
- **AUTO_INCREMENT does not create UNIQUE** — Unlike MySQL, CUBRID's AUTO_INCREMENT does not automatically add a UNIQUE constraint.
- **One AUTO_INCREMENT per table** — Only a single auto-increment column is allowed per table.
- **CHECK constraints parsed but not enforced** — CHECK clauses are accepted in DDL but have no runtime effect.

### OID References
- **REUSE_OID is the default since CUBRID 10.x** — Tables must be explicitly created with `DONT_REUSE_OID` to be used as OID reference targets.
- **DONT_REUSE_OID requires CUBRID 11.0+** — The `DONT_REUSE_OID` DDL keyword is not supported on CUBRID 10.2. The dialect automatically omits it on versions below 11.0.

---

## pycubrid Driver Limitations

- **Collection types return raw bytes** — SET, MULTISET, LIST values are returned as raw binary data instead of Python collections. The dialect includes a binary parser (`_parse_collection_bytes`) that correctly decodes the wire format including the last-element null terminator omission.

---

## SQLAlchemy Core / FK Parsing Issue

- **FK reference parsing with parenthesized column names** — `get_foreign_keys()` parses `SHOW CREATE TABLE` output with regex. Column names containing parentheses (e.g., `col(3)`) are not parsed correctly. This affects 6 BizarroCharacterTest failures and is a regex limitation in the dialect's FK parser.
