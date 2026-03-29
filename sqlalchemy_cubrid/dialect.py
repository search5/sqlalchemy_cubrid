# sqlalchemy_cubrid/dialect.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

import json
import re

from sqlalchemy import text
from sqlalchemy.engine import default
from sqlalchemy_cubrid.base import CubridExecutionContext
from sqlalchemy_cubrid.base import CubridIdentifierPreparer
from sqlalchemy_cubrid.compiler import CubridCompiler
from sqlalchemy_cubrid.compiler import CubridDDLCompiler
from sqlalchemy_cubrid.compiler import CubridTypeCompiler


class CubridDialect(default.DefaultDialect):
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
                -4,      # Communication error
                -11,     # Handle is closed
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
            except Exception:
                indexes = []
            if info_cache is not None:
                info_cache[cache_key] = indexes
        return any(idx["name"] == index_name for idx in indexes)

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

    # CUBRID type name -> SQLAlchemy type mapping
    _type_map = None

    @staticmethod
    def _get_type_map():
        from sqlalchemy import types as sqltypes

        return {
            "INTEGER": sqltypes.INTEGER,
            "INT": sqltypes.INTEGER,
            "BIGINT": sqltypes.BIGINT,
            "SHORT": sqltypes.SMALLINT,
            "SMALLINT": sqltypes.SMALLINT,
            "FLOAT": sqltypes.FLOAT,
            "REAL": sqltypes.FLOAT,
            "DOUBLE": sqltypes.DOUBLE,
            "DOUBLE PRECISION": sqltypes.DOUBLE,
            "NUMERIC": sqltypes.NUMERIC,
            "DECIMAL": sqltypes.NUMERIC,
            "STRING": sqltypes.VARCHAR,
            "CHARACTER VARYING": sqltypes.VARCHAR,
            "VARCHAR": sqltypes.VARCHAR,
            "CHAR": sqltypes.CHAR,
            "CHARACTER": sqltypes.CHAR,
            "DATE": sqltypes.DATE,
            "TIME": sqltypes.TIME,
            "DATETIME": sqltypes.DATETIME,
            "TIMESTAMP": sqltypes.TIMESTAMP,
            "DATETIMELTZ": sqltypes.DATETIME,
            "DATETIMETZ": sqltypes.DATETIME,
            "TIMESTAMPLTZ": sqltypes.TIMESTAMP,
            "TIMESTAMPTZ": sqltypes.TIMESTAMP,
            "BLOB": sqltypes.BLOB,
            "CLOB": sqltypes.CLOB,
            "BIT": sqltypes.LargeBinary,
            "BIT VARYING": sqltypes.LargeBinary,
            "ENUM": sqltypes.Enum,
            "JSON": sqltypes.JSON,
            "SET": sqltypes.NullType,
            "SET_OF": sqltypes.NullType,
            "MULTISET": sqltypes.NullType,
            "MULTISET_OF": sqltypes.NullType,
            "LIST": sqltypes.NullType,
            "LIST_OF": sqltypes.NullType,
            "SEQUENCE": sqltypes.NullType,
            "SEQUENCE_OF": sqltypes.NullType,
        }

    def _resolve_type(self, type_str):
        if self._type_map is None:
            CubridDialect._type_map = self._get_type_map()

        # Handle types with length like VARCHAR(100)
        match = re.match(r"(\w[\w\s]*?)(?:\((.+)\))?$", type_str)
        if not match:
            from sqlalchemy import types as sqltypes
            return sqltypes.NullType()

        base_type = match.group(1).strip().upper()
        params = match.group(2)

        type_cls = self._type_map.get(base_type)
        if type_cls is None:
            from sqlalchemy import types as sqltypes
            return sqltypes.NullType()

        try:
            if params and base_type in ("NUMERIC", "DECIMAL"):
                parts = [int(x.strip()) for x in params.split(",")]
                return type_cls(*parts)
            elif params and base_type in ("VARCHAR", "CHARACTER VARYING", "CHAR", "CHARACTER", "STRING"):
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

    def get_columns(self, connection, table_name, schema=None, **kw):
        from sqlalchemy import exc as sa_exc
        try:
            result = connection.execute(
                text("SHOW COLUMNS FROM " + self.identifier_preparer.quote_identifier(table_name))
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
        except Exception:
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

    def get_foreign_keys(self, connection, table_name, schema=None, **kw):
        from sqlalchemy import exc as sa_exc
        # CUBRID doesn't expose FK reference info in catalog views,
        # so we parse the DDL from SHOW CREATE TABLE.
        # For views, SHOW CREATE TABLE fails — return empty list.
        try:
            result = connection.execute(
                text("SHOW CREATE TABLE " + self.identifier_preparer.quote_identifier(table_name))
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
        fk_pattern = re.compile(
            r"CONSTRAINT\s+\[([^\]]+)\]\s+FOREIGN\s+KEY\s*\(([^)]+)\)\s+"
            r"REFERENCES\s+\[(?:[^\]]+\.)?([^\]]+)\]\s*\(([^)]+)\)",
            re.IGNORECASE,
        )
        fks = []
        for match in fk_pattern.finditer(ddl):
            fk_name = match.group(1)
            constrained = [c.strip().strip("[]") for c in match.group(2).split(",")]
            referred_table = match.group(3)
            referred_cols = [c.strip().strip("[]") for c in match.group(4).split(",")]
            fks.append({
                "name": fk_name,
                "constrained_columns": constrained,
                "referred_schema": schema,
                "referred_table": referred_table,
                "referred_columns": referred_cols,
            })
        fks.sort(key=lambda x: x["name"])
        return fks

    def get_unique_constraints(self, connection, table_name, schema=None, **kw):
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

    def get_indexes(self, connection, table_name, schema=None, **kw):
        kw.pop("info_cache", None)
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
                indexes[idx_name]["column_sorting"][col_name] = (asc_desc.lower(),)

        return list(indexes.values())

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

    def get_view_definition(self, connection, view_name, schema=None, **kw):
        result = connection.execute(
            text(
                "SELECT vclass_def FROM db_vclass "
                "WHERE vclass_name = :name"
            ),
            {"name": view_name.lower()},
        )
        row = result.fetchone()
        if row:
            return row[0]
        from sqlalchemy.exc import NoSuchTableError
        raise NoSuchTableError(view_name)

    def get_check_constraints(self, connection, table_name, schema=None, **kw):
        # CUBRID parses CHECK constraints but does not enforce or store them.
        # No catalog table exists for CHECK constraints.
        kw.pop("info_cache", None)
        if not self._has_object(connection, table_name):
            from sqlalchemy.exc import NoSuchTableError
            raise NoSuchTableError(table_name)
        return []

    def get_table_comment(self, connection, table_name, schema=None, **kw):
        kw.pop("info_cache", None)
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

    def get_sequence_names(self, connection, schema=None, **kw):
        kw.pop("info_cache", None)
        # Exclude auto-generated serials created for AUTO_INCREMENT columns.
        # Column renamed: att_name (10.2~11.3) -> attr_name (11.4+)
        attr_col = self._serial_attr_column
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
