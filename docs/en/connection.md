# Connection

This page covers engine URL format, connection options, isolation levels, connection pooling, and disconnect detection.

## Engine URL Format

The CUBRID connection URL follows the standard SQLAlchemy format:

```
cubrid://user:password@host:port/database
```

| Component  | Default     | Description                        |
|------------|-------------|------------------------------------|
| `user`     | `dba`       | CUBRID database user               |
| `password` | (empty)     | User password                      |
| `host`     | `localhost` | CUBRID broker host                 |
| `port`     | `33000`     | CUBRID broker port                 |
| `database` | (empty)     | Database name                      |

### Examples

```python
from sqlalchemy import create_engine

# Default DBA user with empty password
engine = create_engine("cubrid://dba:@localhost:33000/testdb")

# With explicit credentials
engine = create_engine("cubrid://myuser:mypassword@db.example.com:33000/production")

# Explicit driver name (pycubrid is the only supported driver)
engine = create_engine("cubrid+pycubrid://dba:@localhost:33000/testdb")
```

## Connection Options

The `create_engine()` function accepts standard SQLAlchemy options:

```python
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    echo=True,              # Log all SQL statements
    pool_size=5,            # Number of persistent connections
    max_overflow=10,        # Extra connections beyond pool_size
    pool_timeout=30,        # Seconds to wait for a connection
    pool_recycle=3600,      # Recycle connections after N seconds
    pool_pre_ping=True,     # Test connections before checkout
)
```

### JSON serialization

Custom JSON serializer/deserializer can be passed for the JSON column type:

```python
import orjson

engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    json_serializer=lambda obj: orjson.dumps(obj).decode(),
    json_deserializer=orjson.loads,
)
```

## Isolation Levels

CUBRID supports three transaction isolation levels plus an autocommit mode. The dialect maps these to the CUBRID numeric codes internally.

| SQLAlchemy Name     | CUBRID Code | Description                              |
|---------------------|-------------|------------------------------------------|
| `READ COMMITTED`    | 4           | Default. Reads see committed data only.  |
| `REPEATABLE READ`   | 5           | Reads within a transaction are stable.   |
| `SERIALIZABLE`      | 6           | Full isolation. Strictest level.         |
| `AUTOCOMMIT`        | --          | Each statement commits immediately.      |

!!! note
    CUBRID does not support `READ UNCOMMITTED`. The lowest isolation level is `READ COMMITTED`.

### Setting the isolation level

#### At engine creation

```python
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    isolation_level="REPEATABLE READ",
)
```

#### Per connection

```python
with engine.connect().execution_options(
    isolation_level="SERIALIZABLE"
) as conn:
    # This connection uses SERIALIZABLE isolation
    result = conn.execute(text("SELECT ..."))
```

#### Autocommit mode

```python
with engine.connect().execution_options(
    isolation_level="AUTOCOMMIT"
) as conn:
    # DDL or statements that need immediate commit
    conn.execute(text("CREATE TABLE ..."))
```

!!! warning
    When switching from `AUTOCOMMIT` back to a transactional level, the dialect automatically disables autocommit on the underlying pycubrid connection.

## Connection Pooling

SQLAlchemy provides built-in connection pooling. The dialect works with all standard pool implementations.

### Recommended configuration for CUBRID

```python
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    pool_size=5,          # Keep 5 connections open
    max_overflow=10,      # Allow up to 15 total
    pool_recycle=1800,    # Recycle after 30 minutes
    pool_pre_ping=True,   # Validate connections on checkout
)
```

### NullPool (no pooling)

For short-lived scripts or serverless environments:

```python
from sqlalchemy.pool import NullPool

engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    poolclass=NullPool,
)
```

## do_ping()

The dialect implements `do_ping()` to validate connections. This method is used by SQLAlchemy's `pool_pre_ping` feature and runs:

```sql
SELECT 1 FROM db_root
```

If the query succeeds, the connection is alive. If it raises a `pycubrid.Error`, the connection is considered dead and will be replaced.

```python
# Enable pre-ping to auto-recover dead connections
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    pool_pre_ping=True,
)
```

## is_disconnect()

The dialect detects broken connections by inspecting exceptions from pycubrid. A connection is classified as disconnected when:

- `InterfaceError` contains "closed" or "connection" in the message
- `OperationalError` contains "communication" or "connection" in the message
- pycubrid numeric error codes match known disconnect codes:
    - `-4` -- Communication error
    - `-11` -- Handle is closed
    - `-21003` -- Connection refused

When `is_disconnect()` returns `True`, SQLAlchemy invalidates the connection and removes it from the pool.

## on_connect()

When a new raw DBAPI connection is created, the dialect runs an `on_connect` callback that:

1. Disables autocommit (for transactional behavior by default)
2. Initializes isolation level tracking to `READ COMMITTED`

This ensures all connections start in a consistent state.

## Savepoints

CUBRID supports `SAVEPOINT` and `ROLLBACK TO SAVEPOINT`, but does not support `RELEASE SAVEPOINT`. The dialect silently skips the release operation so that SQLAlchemy's nested transaction (savepoint) support works correctly.

```python
with engine.connect() as conn:
    conn.begin()
    conn.begin_nested()  # SAVEPOINT
    conn.execute(text("INSERT INTO ..."))
    conn.rollback()      # ROLLBACK TO SAVEPOINT
    conn.commit()        # COMMIT outer transaction
```

## Server Version Detection

The dialect reads the server version from pycubrid on initialization and makes it available as a tuple:

```python
with engine.connect() as conn:
    pass  # Triggers initialize()

print(engine.dialect._cubrid_version)  # (11, 4, 0)
print(engine.dialect.server_version_info)  # (11, 4, 0)
```

This version information is used internally for conditional behavior (e.g., the `db_serial` catalog column was renamed from `att_name` to `attr_name` in CUBRID 11.4).
