# Changelog

All notable changes to sqlalchemy-cubrid are documented in this file.

---

## [1.0.0] — 2026-03-30

### 0.9.1 — Error & Edge Case Tests
- Connection disconnect recovery tests (`is_disconnect()`, `pool_pre_ping`, `do_ping()`)
- Invalid SQL exception type verification (ProgrammingError, IntegrityError, DatabaseError)
- Timeout behavior tests (cross-join completion, pool timeout exhaustion)
- Bulk data tests (1000-row insert, 5000-char VARCHAR round-trip, batch update/delete)
- Concurrent connection tests (5-thread insert, 10-thread read, transaction isolation)

### 0.9.0 — Cross-Version Compatibility
- Full test pass on CUBRID 10.2, 11.0, 11.2, 11.3, 11.4 (0 failures)
- Collection binary parser fix — last element null terminator omission handled
- `DONT_REUSE_OID` version guard (11.0+ only, omitted on 10.2)
- `reset_isolation_level()` override for SQLAlchemy 2.0.48 compatibility
- `CUBRID_TEST_URL` environment variable for multi-version test execution
- Cross-version feature support tests (CTE, Window Function, JSON, Isolation Level)
- `att_name` / `attr_name` branching verified across all versions

### 0.8.2 — Bug Fixes & Missing Features (21 items)

**Bug Fixes:**
- **FK reflection:** `get_foreign_keys()` now captures `ON DELETE` / `ON UPDATE` referential actions (CASCADE, SET NULL, NO ACTION, RESTRICT) in the `options` dict
- **CAST type mapping:** Added `visit_cast()` — `CAST(x AS TEXT)` correctly renders as `CAST(x AS STRING)`, `BOOLEAN` as `SMALLINT`, etc.
- **Exception handling:** Narrowed `except Exception` to specific `ProgrammingError`/`DatabaseError` in `has_index()` and `get_columns()` comment fetch
- **Collection parser:** Added bounds checking in `_parse_collection_bytes()` to prevent silent data corruption on malformed binary input
- **Collection type reflection:** `_type_map` now maps SET/MULTISET/LIST to `CubridSet`/`CubridMultiset`/`CubridList` (previously returned `NullType`)
- **Collection fallback:** Result processors now return empty collections instead of `set(bytes)` → integer set on parse failure
- **SYS_CONNECT_BY_PATH:** Separator escaping now uses `render_literal_value()` for proper handling of quotes and special characters
- **get_sequence_names:** Added assertion guard for `att_name`/`attr_name` column whitelist
- **get_lastrowid:** Added `AttributeError` safety guard for pycubrid cursors without `lastrowid`
- **_type_map:** Changed from lazy init to eager class-level initialization (thread safety)
- **index_ddl_if_exists:** Confirmed CUBRID does not support IF [NOT] EXISTS for indexes; removed IF EXISTS from `visit_drop_index()`
- **visit_create_index:** New DDL compiler for CUBRID-specific index types (REVERSE, FILTERED, FUNCTION-based)

**New Features:**
- **TRUNCATE TABLE:** `truncate()` DDL element and `Truncate` class (`dml.py`)
- **ROWNUM:** `rownum()` pseudo-column for row numbering (`hierarchical.py`)
- **MERGE DELETE:** `when_matched_then_delete(condition=)` method; conditional WHEN clauses with `condition=` parameter on all WHEN methods
- **REGEXP/RLIKE:** `visit_regexp_match_op_binary` — `column.regexp_match()` generates `REGEXP` operator
- **Built-in functions:** `group_concat`, `nvl`, `nvl2`, `decode`, `if_`, `ifnull` (`functions.py`)
- **Partitioning:** `PartitionByRange`, `PartitionByHash`, `PartitionByList` DDL elements (`partition.py`)
- **DBLINK (11.2+):** `CreateServer`, `DropServer`, `DbLink` for remote database access (`dblink.py`)

**Tests:**
- 67 compile-only tests covering all 21 fixes (`tests/test_082_fixes.py`)
- SQLAlchemy test suite: 736 passed, 19 failed (unchanged), 878 skipped, 22 errors

**Documentation:**
- Updated en/ko docs: index, dml, queries, cubrid-features, introspection, limitations
- Added sections: TRUNCATE, REGEXP, CAST mapping, ROWNUM, MERGE DELETE, built-in functions, partitioning, DBLINK, FK options

### 0.8.1 — Limitations Documentation
- Added `KNOWN_LIMITATIONS.md` — categorized 19 test failures, CUBRID/pycubrid limits
- Updated `CHANGELOG.md` — full version history from 0.1.0 to 0.8.0

### 0.8.0 — Package Metadata & Documentation
- Rewrote `README.md` with full usage guide and code examples
- Added MkDocs documentation site (mkdocs-material + mkdocs-static-i18n)
- English and Korean documentation (11 pages each)
- Updated `pyproject.toml`: homepage, repository, documentation URLs, classifiers
- Added docstrings to core modules (dialect.py, compiler.py, base.py)

---

## 0.7.x — CUBRID Object-Relational Features

### 0.7.1 — OID References
- `CubridOID` type for OID reference columns
- `deref()` path expression for OID dereferencing (chainable)
- `CreateTableDontReuseOID` DDL construct
- `get_oid_columns()` introspection method
- 18 integration tests

### 0.7.0 — Class Inheritance
- `CreateTableUnder` / `DropTableInheritance` DDL constructs
- `get_super_class()`, `get_sub_classes()`, `get_inherited_columns()` helpers
- `get_super_class_name()`, `get_sub_class_names()` dialect methods
- Multi-level inheritance and ORM reflected CRUD support

---

## 0.6.x — pycubrid Driver & Code Quality

### 0.6.6 — Alembic Integration & Query Tracing
- `CubridImpl` for Alembic with `transactional_ddl = False`
- `render_type()` for collection types, `compare_type()` case-insensitive
- Registered as `alembic.ddl` entry point
- `trace_query()` and `QueryTracer` utilities (TEXT/JSON output)

### 0.6.5 — DML Extensions
- `INSERT ... ON DUPLICATE KEY UPDATE` (explicit values, no `VALUES()` function)
- `REPLACE INTO` support
- `FOR UPDATE` clause (OF columns, no SHARE mode)

### 0.6.4 — Connection Lifecycle & Cache
- Isolation level support (`get/set_isolation_level`, AUTOCOMMIT)
- `on_connect()` — autocommit disable and isolation tracking
- `do_ping()` — `SELECT 1 FROM db_root` pool validation
- `@reflection.cache` on 12 introspection methods

### 0.6.3 — Error Handling Hardening
- `_resolve_type()` exception handling for malformed type strings
- Narrowed `except Exception` to specific exception types
- Added `from e` exception chaining in `get_view_definition()`

### 0.6.2 — CHECK Constraints & Comments
- `get_check_constraints()` (returns empty — CUBRID parses but ignores CHECK)
- `get_table_comment()` / column comment support via `db_attribute`
- DDL COMMENT clause on tables and columns

### 0.6.1 — Collection Types & Driver Compatibility
- `_parse_collection_bytes()` for pycubrid raw binary format
- `is_disconnect()` with pycubrid error code detection
- Fixed `cache_ok` warnings on collection type subclasses

### 0.6.0 — pycubrid Driver Switch
- Switched from CUBRIDdb to pycubrid (pure-Python driver)
- Inspector cache (`info_cache`) for `has_index` / `has_sequence`
- `Float()` → DOUBLE mapping for better precision

---

## 0.5.x — Stabilization

### 0.5.2 — SQLAlchemy Test Suite
- Passed SQLAlchemy official dialect test suite (667 passed, 18 failed)
- CI/CD configuration

### 0.5.1 — Version Compatibility
- CUBRID 10.2 ~ 11.4 cross-version testing
- Version-conditional logic (`att_name` vs `attr_name` in 11.4+)

### 0.5.0 — Indexes, Views & Reserved Words
- UNIQUE, REVERSE, FILTERED, FUNCTION index support
- `get_view_names()`, `get_view_definition()`
- Reserved words updated for 10.2 ~ 11.4 (349 keywords)

---

## 0.4.x — CUBRID-Specific Features

### 0.4.2 — Advanced Queries
- `CONNECT BY` hierarchical queries with all pseudo-columns
- `MERGE` statement support

### 0.4.1 — SERIAL & CLICK COUNTER
- SERIAL (sequence) DDL and introspection
- CLICK COUNTER type with `incr()` / `decr()` functions

### 0.4.0 — Collection Types
- SET, MULTISET, LIST (SEQUENCE) type support
- Collection type CRUD operations

---

## 0.3.x — SQL Compiler & ORM

### 0.3.2 — Complex Queries
- Subqueries, GROUP BY / HAVING / ORDER BY
- UNION / INTERSECT (INTERSECTION) / EXCEPT (DIFFERENCE)

### 0.3.1 — SQL Functions & Joins
- String concatenation (`||` / `CONCAT`)
- CUBRID date and string function mappings
- JOIN syntax support

### 0.3.0 — SQL Compiler
- SELECT, INSERT, UPDATE, DELETE compilation
- LIMIT / OFFSET syntax
- Basic ORM CRUD

---

## 0.2.x — DDL & Type System

### 0.2.2 — Constraints & Special Types
- BOOLEAN → SMALLINT mapping
- ENUM type support
- NULL/NOT NULL, DEFAULT value handling

### 0.2.1 — Date/Time & Binary Types
- DATETIME, TIMESTAMP, DATE, TIME mapping
- BLOB, CLOB, BIT, BIT VARYING mapping

### 0.2.0 — DDL & Basic Types
- `CubridTypeCompiler` for basic type mapping
- `CubridDDLCompiler` for CREATE/DROP TABLE
- AUTO_INCREMENT support

---

## 0.1.x — Connection & Introspection

### 0.1.2 — Schema Reflection
- `get_columns()`, `get_pk_constraint()`, `get_foreign_keys()`, `get_indexes()`
- `metadata.reflect()` support

### 0.1.1 — Basic Introspection
- `has_table()`, `get_table_names()`

### 0.1.0 — Initial Connection
- `import_dbapi()` for SQLAlchemy 2.x
- `create_connect_args()` URL parsing
- Docker-based CUBRID test environment

---

## Test Suite Summary (1.0.0)

| Category | Tests |
|----------|-------|
| Custom tests (11.4) | 410 passed, 0 failed |
| Cross-version compat (5 versions) | 85 passed, 0 failed |
| SQLAlchemy official suite (11.4) | 737 passed, 18 failed, 878 skipped, 22 errors |

### Version Compatibility Matrix

| Version | Passed | Failed | Skipped |
|---------|--------|--------|---------|
| 10.2 | 288 | 0 | 11 (OID) |
| 11.0 | 299 | 0 | 0 |
| 11.2 | 299 | 0 | 0 |
| 11.3 | 299 | 0 | 0 |
| 11.4 | 384 | 0 | 0 |
