# Type System

This page documents how CUBRID data types are mapped to SQLAlchemy types, including special mappings and CUBRID-specific behaviors.

## Type Mapping Table

### Numeric Types

| CUBRID Type        | SQLAlchemy Type       | Notes                                      |
|--------------------|-----------------------|--------------------------------------------|
| `INTEGER` / `INT`  | `Integer`             | 32-bit signed integer                      |
| `BIGINT`           | `BigInteger`          | 64-bit signed integer                      |
| `SHORT` / `SMALLINT` | `SmallInteger`     | 16-bit signed integer. SHOW COLUMNS reports `SHORT` |
| `FLOAT` / `REAL`   | `Float`               | Single precision (7 significant digits)    |
| `DOUBLE`           | `Double`              | Double precision                           |
| `NUMERIC` / `DECIMAL` | `Numeric`          | Exact numeric with precision and scale     |

### String Types

| CUBRID Type                    | SQLAlchemy Type | Notes                                  |
|--------------------------------|-----------------|----------------------------------------|
| `CHAR` / `CHARACTER`           | `CHAR`          | Fixed-length string                    |
| `VARCHAR` / `CHARACTER VARYING`| `VARCHAR`       | Variable-length string                 |
| `STRING`                       | `VARCHAR`       | Alias for `VARCHAR(1,073,741,823)`     |

### Date/Time Types

| CUBRID Type      | SQLAlchemy Type | Notes                                      |
|------------------|-----------------|--------------------------------------------|
| `DATE`           | `Date`          | Date only (no time component)              |
| `TIME`           | `Time`          | Time only (no date component)              |
| `DATETIME`       | `DateTime`      | Date + time with **millisecond** precision |
| `TIMESTAMP`      | `TIMESTAMP`     | Unix timestamp                             |
| `DATETIMELTZ`    | `DateTime`      | DATETIME with local timezone               |
| `DATETIMETZ`     | `DateTime`      | DATETIME with explicit timezone            |
| `TIMESTAMPLTZ`   | `TIMESTAMP`     | TIMESTAMP with local timezone              |
| `TIMESTAMPTZ`    | `TIMESTAMP`     | TIMESTAMP with explicit timezone           |

!!! warning
    CUBRID DATETIME has **millisecond** (3-digit) precision, not microsecond (6-digit) as in MySQL or PostgreSQL. If your application relies on microsecond precision, you will experience data loss.

### Binary Types

| CUBRID Type    | SQLAlchemy Type  | Notes                              |
|----------------|------------------|------------------------------------|
| `BIT`          | `LargeBinary`    | Fixed-length binary                |
| `BIT VARYING`  | `LargeBinary`    | Variable-length binary             |
| `BLOB`         | `BLOB`           | Binary Large Object                |
| `CLOB`         | `CLOB`           | Character Large Object             |

### Other Types

| CUBRID Type  | SQLAlchemy Type | Notes                                  |
|--------------|-----------------|----------------------------------------|
| `ENUM`       | `Enum`          | Up to 512 values                       |
| `JSON`       | `JSON`          | Available since CUBRID 10.2            |
| `SET`        | `NullType`      | Use `CubridSet` for full support       |
| `MULTISET`   | `NullType`      | Use `CubridMultiset` for full support  |
| `LIST` / `SEQUENCE` | `NullType` | Use `CubridList` for full support    |

## Special Type Mappings

The CUBRID type compiler applies several mappings for types that do not exist in CUBRID.

### BOOLEAN to SMALLINT

CUBRID has no `BOOLEAN` column type (it exists only within JSON). The dialect maps `Boolean` to `SMALLINT`:

```python
from sqlalchemy import Column, Boolean

class MyTable(Base):
    __tablename__ = "my_table"
    id = Column(Integer, primary_key=True)
    active = Column(Boolean)
    # DDL: active SMALLINT
```

### TEXT to STRING

CUBRID has no `TEXT` type. The dialect maps `Text` to `STRING` (which is `VARCHAR(1,073,741,823)`):

```python
from sqlalchemy import Column, Text

class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True)
    body = Column(Text)
    # DDL: body STRING
```

### NCHAR to CHAR

`NCHAR` and `NCHAR VARYING` were removed in CUBRID 9.0. The dialect maps these to `CHAR` and `VARCHAR`:

```python
from sqlalchemy import Column, Unicode, UnicodeText

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    title = Column(Unicode(100))   # DDL: title VARCHAR(100)
    body = Column(UnicodeText)     # DDL: body STRING
```

### Float() to DOUBLE

A generic `Float()` with no precision specified maps to `DOUBLE` for better accuracy. If a specific precision is given and it is 7 or less, it maps to `FLOAT`. If the precision exceeds 7, CUBRID automatically promotes it to `DOUBLE`:

```python
from sqlalchemy import Column, Float, Double

class Measurement(Base):
    __tablename__ = "measurements"
    id = Column(Integer, primary_key=True)
    approx = Column(Float)            # DDL: DOUBLE
    precise = Column(Float(5))        # DDL: FLOAT
    big_precise = Column(Float(10))   # DDL: DOUBLE (p > 7)
    explicit = Column(Double)         # DDL: DOUBLE
```

### LargeBinary to BIT VARYING

SQLAlchemy's `LargeBinary` maps to `BIT VARYING(1073741823)` for inline binary storage:

```python
from sqlalchemy import Column, LargeBinary

class FileStore(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True)
    data = Column(LargeBinary)
    # DDL: data BIT VARYING(1073741823)
```

## Collection Types

CUBRID provides three collection types that are mapped via custom SQLAlchemy types. See the [CUBRID Features](cubrid-features.md) page for full details.

```python
from sqlalchemy_cubrid.types import CubridSet, CubridMultiset, CubridList

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    tags = Column(CubridSet("VARCHAR(50)"))
    # DDL: tags SET_OF(VARCHAR(50))
```

## CUBRID OID Type

For object-relational references, use `CubridOID`. See [CUBRID Features](cubrid-features.md).

```python
from sqlalchemy_cubrid.oid import CubridOID

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    manager = Column(CubridOID("person"))
    # DDL: manager person
```

## JSON Type

CUBRID supports JSON since version 10.2. Standard SQLAlchemy `JSON` works out of the box:

```python
from sqlalchemy import Column, JSON

class Config(Base):
    __tablename__ = "configs"
    id = Column(Integer, primary_key=True)
    data = Column(JSON)
    # DDL: data JSON
```

Custom serializers can be configured at engine creation:

```python
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    json_serializer=my_serializer,
    json_deserializer=my_deserializer,
)
```

## ENUM Type

CUBRID supports ENUM with up to 512 values:

```python
from sqlalchemy import Column, Enum

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    status = Column(Enum("pending", "shipped", "delivered"))
    # DDL: status ENUM('pending', 'shipped', 'delivered')
```

## Introspection Type Parsing

When reflecting tables, the dialect parses CUBRID's `SHOW COLUMNS` output and maps type strings back to SQLAlchemy types. Notable parsing behaviors:

- `SHORT` is mapped to `SmallInteger` (CUBRID reports `SHORT` instead of `SMALLINT`)
- `INTEGER` is mapped to `Integer` (CUBRID reports `INTEGER` instead of `INT`)
- `NUMERIC(p,s)` extracts precision and scale
- `VARCHAR(n)` extracts length
- `ENUM('a','b','c')` extracts enum values
- `FLOAT(p)` extracts precision
- Collection types (`SET_OF`, `MULTISET_OF`, `LIST_OF`, `SEQUENCE_OF`) are mapped to `NullType` in reflection (use explicit column types for full collection support)
