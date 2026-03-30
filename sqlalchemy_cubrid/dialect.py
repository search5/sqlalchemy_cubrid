# sqlalchemy_cubrid/dialect.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

import json
import re

from sqlalchemy import exc as sa_exc
from sqlalchemy import text
from sqlalchemy.engine import default, reflection

from sqlalchemy_cubrid.base import (
    CubridExecutionContext,
    CubridIdentifierPreparer,
)
from sqlalchemy_cubrid.compiler import (
    CubridCompiler,
    CubridDDLCompiler,
    CubridTypeCompiler,
)

# CUBRID isolation level numeric codes → standard names
_ISOLATION_LEVEL_MAP = {
    4: "READ COMMITTED",
    5: "REPEATABLE READ",
    6: "SERIALIZABLE",
}

_ISOLATION_LEVEL_REVERSE = {v: k for k, v in _ISOLATION_LEVEL_MAP.items()}


class CubridDialect(default.DefaultDialect):
    """SQLAlchemy dialect for the CUBRID object-relational database.

    Supports CUBRID 10.2 through 11.4 via the pycubrid pure-Python driver.

    Connection URL format::

        cubrid://user:password@host:port/database

    Example::

        engine = create_engine("cubrid://dba:@localhost:33000/testdb")
    """

    name = "cubrid"
    driver = "pycubrid"

    supports_statement_cache = True

    # CUBRID supports SERIAL (equivalent to SQL SEQUENCE)
    supports_sequences = True
    sequences_optional = False
    default_sequence_base = 1

    # CUBRID supports savepoints but not RELEASE SAVEPOINT
    supports_savepoints = True

    # CUBRID does not support RETURNING clause (per official docs)
    insert_returning = False
    update_returning = False
    delete_returning = False

    # CUBRID uses '?' as parameter placeholder (qmark style)
    default_paramstyle = "qmark"

    # pycubrid returns Decimal natively for NUMERIC columns
    supports_native_decimal = True

    # JSON serialization
    _json_serializer = staticmethod(json.dumps)
    _json_deserializer = staticmethod(json.loads)

    def __init__(self, json_serializer=None, json_deserializer=None, **kwargs):
        super().__init__(**kwargs)
        if json_serializer is not None:
            self._json_serializer = json_serializer
        if json_deserializer is not None:
            self._json_deserializer = json_deserializer

    statement_compiler = CubridCompiler
    ddl_compiler = CubridDDLCompiler
    type_compiler_cls = CubridTypeCompiler

    preparer = CubridIdentifierPreparer
    execution_ctx_cls = CubridExecutionContext

    construct_arguments = [
        (
            __import__("sqlalchemy").schema.Table,
            {"dont_reuse_oid": False},
        ),
        (
            __import__("sqlalchemy").schema.Index,
            {
                "reverse": False,
                "filtered": None,
                "function": None,
            },
        ),
    ]

    @classmethod
    def import_dbapi(cls):
        import pycubrid

        return pycubrid

    def create_connect_args(self, url):
        opts = url.translate_connect_args(
            host="host",
            port="port",
            database="database",
            username="user",
            password="password",
        )
        opts.update(url.query)

        # pycubrid uses keyword arguments for connect()
        connect_args = {
            "host": opts.get("host", "localhost"),
            "port": int(opts.get("port", 33000)),
            "database": opts.get("database", ""),
            "user": opts.get("user", "dba"),
            "password": opts.get("password", ""),
        }

        return ([], connect_args)

    # --- Isolation level support ---

    _isolation_lookup = _ISOLATION_LEVEL_REVERSE

    def get_default_isolation_level(self, dbapi_conn):
        return "READ COMMITTED"

    def get_isolation_level_values(self, dbapi_conn):
        return ["AUTOCOMMIT"] + list(_ISOLATION_LEVEL_REVERSE)

    def get_isolation_level(self, dbapi_connection):
        # CUBRID CCI resets the cached isolation level on commit/rollback,
        # so we track it on the connection object.
        return getattr(
            dbapi_connection, "_sa_isolation_level", "READ COMMITTED"
        )

    def reset_isolation_level(self, dbapi_connection):
        # Override to support engine-level non-default isolation levels.
        # DefaultDialect.reset_isolation_level asserts _on_connect_isolation_level
        # is AUTOCOMMIT or the default, but CUBRID engines may be configured
        # with other levels (e.g. SERIALIZABLE).
        target = (
            self._on_connect_isolation_level or self.default_isolation_level
        )
        self._assert_and_set_isolation_level(dbapi_connection, target)

    def set_isolation_level(self, dbapi_connection, level):
        if level == "AUTOCOMMIT":
            dbapi_connection.autocommit = True
            dbapi_connection._sa_isolation_level = "AUTOCOMMIT"
            return

        # Restore transactional mode if switching from AUTOCOMMIT
        if (
            getattr(dbapi_connection, "_sa_isolation_level", None)
            == "AUTOCOMMIT"
        ):
            dbapi_connection.autocommit = False

        code = _ISOLATION_LEVEL_REVERSE.get(level)
        if code is None:
            raise ValueError(
                "Invalid isolation level: %r. "
                "Valid levels: %s" % (level, list(_ISOLATION_LEVEL_REVERSE))
            )
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL %d" % code)
        finally:
            cursor.close()
        dbapi_connection._sa_isolation_level = level

    # --- Connection lifecycle ---

    def on_connect(self):
        def connect(dbapi_connection):
            # Disable autocommit for transactional behavior
            dbapi_connection.autocommit = False
            # Initialize isolation level tracking
            dbapi_connection._sa_isolation_level = "READ COMMITTED"

        return connect

    def do_ping(self, dbapi_connection):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT 1 FROM db_root")
            return True
        except self.loaded_dbapi.Error:
            return False
        finally:
            cursor.close()

    def do_release_savepoint(self, connection, name):
        # CUBRID does not support RELEASE SAVEPOINT — silently skip
        pass

    def is_disconnect(self, e, connection, cursor):
        if isinstance(e, self.loaded_dbapi.InterfaceError):
            msg = str(e).lower()
            if "closed" in msg or "connection" in msg:
                return True
        if isinstance(e, self.loaded_dbapi.OperationalError):
            msg = str(e).lower()
            if "communication" in msg or "connection" in msg:
                return True
        # Check pycubrid numeric error codes
        if hasattr(e, "args") and e.args:
            code = e.args[0] if isinstance(e.args[0], int) else None
            if code in (
                -4,  # Communication error
                -11,  # Handle is closed
                -21003,  # Connection refused
            ):
                return True
        return False

    def initialize(self, connection):
        super().initialize(connection)
        # Cache server version for version-conditional logic
        self._cubrid_version = self.server_version_info or (0,)

    @property
    def _serial_attr_column(self):
        """Column name for the attribute reference in db_serial.

        Renamed from att_name to attr_name in CUBRID 11.4.
        """
        if self._cubrid_version >= (11, 4):
            return "attr_name"
        return "att_name"

    def _has_object(self, connection, name):
        """Check if a table or view exists."""
        result = connection.execute(
            text(
                "SELECT COUNT(*) FROM db_class "
                "WHERE class_name = :name "
                "AND is_system_class = 'NO'"
            ),
            {"name": name.lower()},
        )
        return result.scalar() > 0

    def _is_view(self, connection, view_name):
        result = connection.execute(
            text(
                "SELECT COUNT(*) FROM db_class "
                "WHERE class_name = :name "
                "AND is_system_class = 'NO' "
                "AND class_type = 'VCLASS'"
            ),
            {"name": view_name.lower()},
        )
        return result.scalar() > 0

    def has_table(self, connection, table_name, schema=None, **kw):
        # Pop info_cache so it doesn't propagate to execute()
        kw.pop("info_cache", None)
        result = connection.execute(
            text(
                "SELECT COUNT(*) FROM db_class "
                "WHERE class_name = :name "
                "AND is_system_class = 'NO' "
                "AND class_type = 'CLASS'"
            ),
            {"name": table_name.lower()},
        )
        return result.scalar() > 0

    def has_index(self, connection, table_name, index_name, schema=None, **kw):
        info_cache = kw.get("info_cache")
        cache_key = ("get_indexes", schema, table_name)
        if info_cache is not None and cache_key in info_cache:
            indexes = info_cache[cache_key]
        else:
            try:
                indexes = self.get_indexes(
                    connection, table_name, schema=schema, **kw
                )
            except (
                sa_exc.ProgrammingError,
                sa_exc.DatabaseError,
                sa_exc.NoSuchTableError,
            ):
                indexes = []
            if info_cache is not None:
                info_cache[cache_key] = indexes
        return any(idx["name"] == index_name for idx in indexes)

    @reflection.cache
    def get_table_names(self, connection, schema=None, **kw):
        result = connection.execute(
            text(
                "SELECT class_name FROM db_class "
                "WHERE is_system_class = 'NO' "
                "AND class_type = 'CLASS' "
                "ORDER BY class_name"
            )
        )
        return [row[0] for row in result]

    # CUBRID type name -> SQLAlchemy type mapping (eagerly initialized)
    from sqlalchemy import types as _sqltypes

    from sqlalchemy_cubrid.types import CubridList, CubridMultiset, CubridSet

    _type_map = {
        "INTEGER": _sqltypes.INTEGER,
        "INT": _sqltypes.INTEGER,
        "BIGINT": _sqltypes.BIGINT,
        "SHORT": _sqltypes.SMALLINT,
        "SMALLINT": _sqltypes.SMALLINT,
        "FLOAT": _sqltypes.FLOAT,
        "REAL": _sqltypes.FLOAT,
        "DOUBLE": _sqltypes.DOUBLE,
        "DOUBLE PRECISION": _sqltypes.DOUBLE,
        "NUMERIC": _sqltypes.NUMERIC,
        "DECIMAL": _sqltypes.NUMERIC,
        "STRING": _sqltypes.VARCHAR,
        "CHARACTER VARYING": _sqltypes.VARCHAR,
        "VARCHAR": _sqltypes.VARCHAR,
        "CHAR": _sqltypes.CHAR,
        "CHARACTER": _sqltypes.CHAR,
        "DATE": _sqltypes.DATE,
        "TIME": _sqltypes.TIME,
        "DATETIME": _sqltypes.DATETIME,
        "TIMESTAMP": _sqltypes.TIMESTAMP,
        "DATETIMELTZ": _sqltypes.DATETIME,
        "DATETIMETZ": _sqltypes.DATETIME,
        "TIMESTAMPLTZ": _sqltypes.TIMESTAMP,
        "TIMESTAMPTZ": _sqltypes.TIMESTAMP,
        "BLOB": _sqltypes.BLOB,
        "CLOB": _sqltypes.CLOB,
        "BIT": _sqltypes.LargeBinary,
        "BIT VARYING": _sqltypes.LargeBinary,
        "ENUM": _sqltypes.Enum,
        "JSON": _sqltypes.JSON,
        "SET": CubridSet,
        "SET_OF": CubridSet,
        "MULTISET": CubridMultiset,
        "MULTISET_OF": CubridMultiset,
        "LIST": CubridList,
        "LIST_OF": CubridList,
        "SEQUENCE": CubridList,
        "SEQUENCE_OF": CubridList,
    }

    del _sqltypes

    # Collection type base names for detection
    _COLLECTION_BASES = frozenset(
        {
            "SET",
            "SET_OF",
            "MULTISET",
            "MULTISET_OF",
            "LIST",
            "LIST_OF",
            "SEQUENCE",
            "SEQUENCE_OF",
        }
    )

    def _resolve_type(self, type_str):
        """Convert a CUBRID type string to a SQLAlchemy type instance.

        Parses strings like ``VARCHAR(100)``, ``NUMERIC(15,2)``,
        ``ENUM('a','b')``, or ``SET_OF(VARCHAR(50))`` and returns the
        corresponding SQLAlchemy type.
        Unknown types are mapped to :class:`~sqlalchemy.types.NullType`.
        """
        from sqlalchemy import types as sqltypes

        # Handle types with length like VARCHAR(100)
        match = re.match(r"(\w[\w\s]*?)(?:\((.+)\))?$", type_str)
        if not match:
            return sqltypes.NullType()

        base_type = match.group(1).strip().upper()
        params = match.group(2)

        type_cls = self._type_map.get(base_type)
        if type_cls is None:
            return sqltypes.NullType()

        try:
            if base_type in self._COLLECTION_BASES:
                # Collection types: pass element type string
                element_type = params if params else "VARCHAR(1073741823)"
                return type_cls(element_type)
            elif params and base_type in ("NUMERIC", "DECIMAL"):
                parts = [int(x.strip()) for x in params.split(",")]
                return type_cls(*parts)
            elif params and base_type in (
                "VARCHAR",
                "CHARACTER VARYING",
                "CHAR",
                "CHARACTER",
                "STRING",
            ):
                return type_cls(int(params))
            elif params and base_type == "ENUM":
                values = re.findall(r"'([^']*)'", params)
                return type_cls(*values)
            elif params and base_type in ("FLOAT", "REAL"):
                return type_cls(precision=int(params))
            elif params and base_type == "DOUBLE":
                return type_cls()
            elif params and base_type in ("BIT", "BIT VARYING"):
                return type_cls(int(params))
            else:
                return type_cls()
        except (ValueError, TypeError):
            return type_cls()

    @reflection.cache
    def get_columns(self, connection, table_name, schema=None, **kw):
        try:
            result = connection.execute(
                text(
                    "SHOW COLUMNS FROM "
                    + self.identifier_preparer.quote_identifier(table_name)
                )
            )
        except (sa_exc.ProgrammingError, sa_exc.DatabaseError) as e:
            raise sa_exc.NoSuchTableError(table_name) from e

        # Fetch column comments from db_attribute catalog
        comment_map = {}
        try:
            comments = connection.execute(
                text(
                    "SELECT attr_name, comment FROM db_attribute "
                    "WHERE class_name = :name ORDER BY def_order"
                ),
                {"name": table_name.lower()},
            )
            for crow in comments:
                comment_map[crow[0]] = crow[1] if crow[1] else None
        except (sa_exc.ProgrammingError, sa_exc.DatabaseError):
            pass

        columns = []
        for row in result:
            # row: (Field, Type, Null, Key, Default, Extra)
            col_name = row[0]
            col_type_str = row[1]
            nullable = row[2] == "YES"
            default = row[4]
            extra = row[5] if row[5] else ""

            col_type = self._resolve_type(col_type_str)
            autoincrement = "auto_increment" in extra

            col_info = {
                "name": col_name,
                "type": col_type,
                "nullable": nullable,
                "default": str(default) if default is not None else None,
                "autoincrement": autoincrement,
                "comment": comment_map.get(col_name),
            }
            columns.append(col_info)
        return columns

    @reflection.cache
    def get_pk_constraint(self, connection, table_name, schema=None, **kw):
        if not self._has_object(connection, table_name):
            from sqlalchemy.exc import NoSuchTableError

            raise NoSuchTableError(table_name)
        result = connection.execute(
            text(
                "SELECT i.index_name, k.key_attr_name, k.key_order "
                "FROM db_index i "
                "JOIN db_index_key k "
                "  ON i.index_name = k.index_name "
                "  AND i.class_name = k.class_name "
                "WHERE i.class_name = :name "
                "AND i.is_primary_key = 'YES' "
                "ORDER BY k.key_order"
            ),
            {"name": table_name.lower()},
        )
        pk_name = None
        pk_cols = []
        for row in result:
            pk_name = row[0]
            pk_cols.append(row[1])
        return {"constrained_columns": pk_cols, "name": pk_name}

    @reflection.cache
    def get_foreign_keys(self, connection, table_name, schema=None, **kw):
        # CUBRID doesn't expose FK reference info in catalog views,
        # so we parse the DDL from SHOW CREATE TABLE.
        # For views, SHOW CREATE TABLE fails — return empty list.
        try:
            result = connection.execute(
                text(
                    "SHOW CREATE TABLE "
                    + self.identifier_preparer.quote_identifier(table_name)
                )
            )
        except (sa_exc.ProgrammingError, sa_exc.DatabaseError) as e:
            # SHOW CREATE TABLE fails for views — views have no foreign keys
            if self._is_view(connection, table_name):
                return []
            raise sa_exc.NoSuchTableError(table_name) from e
        row = result.fetchone()
        if not row:
            return []

        ddl = row[1]
        # Capture: constraint name, local cols, referred table, referred cols,
        # and any trailing ON DELETE / ON UPDATE actions.
        fk_pattern = re.compile(
            r"CONSTRAINT\s+\[([^\]]+)\]\s+FOREIGN\s+KEY\s*\(([^)]+)\)\s+"
            r"REFERENCES\s+\[(?:[^\]]+\.)?([^\]]+)\]\s*\(([^)]+)\)"
            r"(?:\s+ON\s+DELETE\s+(CASCADE|SET\s+NULL|NO\s+ACTION|RESTRICT))?"
            r"(?:\s+ON\s+UPDATE\s+(CASCADE|SET\s+NULL|NO\s+ACTION|RESTRICT))?",
            re.IGNORECASE,
        )
        fks = []
        for match in fk_pattern.finditer(ddl):
            fk_name = match.group(1)
            constrained = [
                c.strip().strip("[]") for c in match.group(2).split(",")
            ]
            referred_table = match.group(3)
            referred_cols = [
                c.strip().strip("[]") for c in match.group(4).split(",")
            ]
            on_delete = match.group(5)
            on_update = match.group(6)

            options = {}
            if on_delete:
                options["ondelete"] = " ".join(on_delete.upper().split())
            if on_update:
                options["onupdate"] = " ".join(on_update.upper().split())

            fks.append(
                {
                    "name": fk_name,
                    "constrained_columns": constrained,
                    "referred_schema": schema,
                    "referred_table": referred_table,
                    "referred_columns": referred_cols,
                    "options": options,
                }
            )
        fks.sort(key=lambda x: x["name"])
        return fks

    @reflection.cache
    def get_unique_constraints(
        self, connection, table_name, schema=None, **kw
    ):
        if not self._has_object(connection, table_name):
            from sqlalchemy.exc import NoSuchTableError

            raise NoSuchTableError(table_name)
        result = connection.execute(
            text(
                "SELECT i.index_name, k.key_attr_name, k.key_order "
                "FROM db_index i "
                "JOIN db_index_key k "
                "  ON i.index_name = k.index_name "
                "  AND i.class_name = k.class_name "
                "WHERE i.class_name = :name "
                "AND i.is_unique = 'YES' "
                "AND i.is_primary_key = 'NO' "
                "AND i.is_foreign_key = 'NO' "
                "ORDER BY i.index_name, k.key_order"
            ),
            {"name": table_name.lower()},
        )
        constraints = {}
        for row in result:
            name = row[0]
            col = row[1]
            if name not in constraints:
                constraints[name] = {
                    "name": name,
                    "column_names": [],
                    "duplicates_index": name,
                }
            constraints[name]["column_names"].append(col)
        return list(constraints.values())

    @reflection.cache
    def get_indexes(self, connection, table_name, schema=None, **kw):
        if not self._has_object(connection, table_name):
            from sqlalchemy.exc import NoSuchTableError

            raise NoSuchTableError(table_name)
        result = connection.execute(
            text(
                "SELECT i.index_name, i.is_unique, "
                "       i.is_reverse, i.filter_expression, i.have_function, "
                "       k.key_attr_name, k.key_order, k.asc_desc, k.func "
                "FROM db_index i "
                "JOIN db_index_key k "
                "  ON i.index_name = k.index_name "
                "  AND i.class_name = k.class_name "
                "WHERE i.class_name = :name "
                "AND i.is_primary_key = 'NO' "
                "AND i.is_foreign_key = 'NO' "
                "ORDER BY i.index_name, k.key_order"
            ),
            {"name": table_name.lower()},
        )
        indexes = {}
        for row in result:
            idx_name = row[0]
            is_unique = row[1] == "YES"
            is_reverse = row[2] == "YES"
            filter_expr = row[3]
            have_function = row[4] == "YES"
            col_name = row[5]
            asc_desc = row[7]  # 'ASC' or 'DESC'
            func_expr = row[8]

            if idx_name not in indexes:
                dialect_options = {}
                if is_reverse:
                    dialect_options["cubrid_reverse"] = True
                if filter_expr:
                    dialect_options["cubrid_filtered"] = filter_expr
                if have_function and func_expr:
                    dialect_options["cubrid_function"] = func_expr

                indexes[idx_name] = {
                    "name": idx_name,
                    "unique": is_unique,
                    "column_names": [],
                    "column_sorting": {},
                    "dialect_options": dialect_options,
                }

            indexes[idx_name]["column_names"].append(col_name)
            if asc_desc and asc_desc.upper() != "ASC":
                indexes[idx_name]["column_sorting"][col_name] = (
                    asc_desc.lower(),
                )

        return list(indexes.values())

    @reflection.cache
    def get_view_names(self, connection, schema=None, **kw):
        result = connection.execute(
            text(
                "SELECT class_name FROM db_class "
                "WHERE is_system_class = 'NO' "
                "AND class_type = 'VCLASS' "
                "ORDER BY class_name"
            )
        )
        return [row[0] for row in result]

    @reflection.cache
    def get_view_definition(self, connection, view_name, schema=None, **kw):
        result = connection.execute(
            text("SELECT vclass_def FROM db_vclass WHERE vclass_name = :name"),
            {"name": view_name.lower()},
        )
        row = result.fetchone()
        if row:
            return row[0]
        from sqlalchemy.exc import NoSuchTableError

        raise NoSuchTableError(view_name)

    @reflection.cache
    def get_check_constraints(self, connection, table_name, schema=None, **kw):
        # CUBRID parses CHECK constraints but does not enforce or store them.
        # No catalog table exists for CHECK constraints.
        if not self._has_object(connection, table_name):
            from sqlalchemy.exc import NoSuchTableError

            raise NoSuchTableError(table_name)
        return []

    @reflection.cache
    def get_table_comment(self, connection, table_name, schema=None, **kw):
        result = connection.execute(
            text(
                "SELECT comment FROM db_class "
                "WHERE class_name = :name "
                "AND is_system_class = 'NO'"
            ),
            {"name": table_name.lower()},
        )
        row = result.fetchone()
        if row is None:
            from sqlalchemy.exc import NoSuchTableError

            raise NoSuchTableError(table_name)
        return {"text": row[0] if row[0] else None}

    @reflection.cache
    def get_sequence_names(self, connection, schema=None, **kw):
        # Exclude auto-generated serials created for AUTO_INCREMENT columns.
        # Column renamed: att_name (10.2~11.3) -> attr_name (11.4+).
        # The column name is not user input — it is derived from the server
        # version, so direct interpolation is safe here.
        attr_col = self._serial_attr_column
        assert attr_col in ("att_name", "attr_name"), attr_col
        result = connection.execute(
            text(
                "SELECT name FROM db_serial "
                "WHERE %s IS NULL "
                "ORDER BY name" % attr_col
            )
        )
        return [row[0] for row in result]

    def has_sequence(self, connection, sequence_name, schema=None, **kw):
        info_cache = kw.get("info_cache")
        cache_key = ("get_sequence_names", schema)
        if info_cache is not None and cache_key in info_cache:
            seq_names = info_cache[cache_key]
        else:
            seq_names = self.get_sequence_names(
                connection, schema=schema, **kw
            )
            if info_cache is not None:
                info_cache[cache_key] = seq_names
        return sequence_name in seq_names

    # -- Inheritance (UNDER) introspection --

    @reflection.cache
    def get_super_class_name(self, connection, table_name, schema=None, **kw):
        """Return the parent class name if this table uses UNDER, else None."""
        result = connection.execute(
            text(
                "SELECT super_class_name FROM db_direct_super_class "
                "WHERE class_name = :name"
            ),
            {"name": table_name.lower()},
        )
        row = result.fetchone()
        return row[0] if row else None

    @reflection.cache
    def get_sub_class_names(self, connection, table_name, schema=None, **kw):
        """Return direct child class names of a table."""
        result = connection.execute(
            text(
                "SELECT class_name FROM db_direct_super_class "
                "WHERE super_class_name = :name "
                "ORDER BY class_name"
            ),
            {"name": table_name.lower()},
        )
        return [row[0] for row in result]

    # -- OID reference introspection --

    @reflection.cache
    def get_oid_columns(self, connection, table_name, schema=None, **kw):
        """Return OID reference columns for a table.

        Each item is a dict with keys: ``name`` (column name) and
        ``referenced_class`` (the class name the OID points to).

        :param connection: A SQLAlchemy connection.
        :param table_name: Table name to inspect.
        :returns: List of dicts.
        """
        result = connection.execute(
            text(
                "SELECT a.attr_name, a.domain_class_name "
                "FROM db_attribute a "
                "WHERE a.class_name = :name "
                "AND a.domain_class_name IS NOT NULL "
                "AND a.domain_class_name != '' "
                "ORDER BY a.def_order"
            ),
            {"name": table_name.lower()},
        )
        return [{"name": row[0], "referenced_class": row[1]} for row in result]

    def _get_server_version_info(self, connection):
        dbapi_conn = connection.connection.dbapi_connection
        version_str = dbapi_conn.get_server_version()
        # Extract only numeric parts (handles suffixes like "11.4.0-beta")
        parts = []
        for x in version_str.split("."):
            match = re.match(r"(\d+)", x)
            if match:
                parts.append(int(match.group(1)))
        return tuple(parts) or (0,)


dialect = CubridDialect
