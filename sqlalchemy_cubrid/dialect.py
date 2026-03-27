# sqlalchemy_cubrid/dialect.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

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
    driver = "CUBRIDdb"

    supports_statement_cache = True

    # CUBRID does not support RETURNING clause (per official docs)
    insert_returning = False
    update_returning = False
    delete_returning = False

    # CUBRID uses '?' as parameter placeholder (qmark style)
    default_paramstyle = "qmark"

    statement_compiler = CubridCompiler
    ddl_compiler = CubridDDLCompiler
    type_compiler_cls = CubridTypeCompiler

    preparer = CubridIdentifierPreparer
    execution_ctx_cls = CubridExecutionContext

    @classmethod
    def import_dbapi(cls):
        import CUBRIDdb

        return CUBRIDdb

    def create_connect_args(self, url):
        opts = url.translate_connect_args(
            host="host",
            port="port",
            database="database",
            username="username",
            password="password",
        )
        opts.update(url.query)

        host = opts.get("host", "localhost")
        port = opts.get("port", 33000)
        database = opts.get("database", "")
        username = opts.get("username", "")
        password = opts.get("password", "")

        dsn = f"CUBRID:{host}:{port}:{database}:::"

        return ([dsn, username, password], {})

    def initialize(self, connection):
        super().initialize(connection)

    def has_table(self, connection, table_name, schema=None, **kw):
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
            "DOUBLE": sqltypes.FLOAT,
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
            "BLOB": sqltypes.BLOB,
            "CLOB": sqltypes.CLOB,
            "BIT": sqltypes.LargeBinary,
            "BIT VARYING": sqltypes.LargeBinary,
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

        if params and base_type in ("NUMERIC", "DECIMAL"):
            parts = [int(x.strip()) for x in params.split(",")]
            return type_cls(*parts)
        elif params and base_type in ("VARCHAR", "CHARACTER VARYING", "CHAR", "CHARACTER", "STRING"):
            return type_cls(int(params))
        else:
            return type_cls()

    def get_columns(self, connection, table_name, schema=None, **kw):
        result = connection.execute(
            text("SHOW COLUMNS FROM " + self.identifier_preparer.quote_identifier(table_name))
        )
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
                "default": repr(default) if default is not None else None,
                "autoincrement": autoincrement,
            }
            columns.append(col_info)
        return columns

    def get_pk_constraint(self, connection, table_name, schema=None, **kw):
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
        # CUBRID doesn't expose FK reference info in catalog views,
        # so we parse the DDL from SHOW CREATE TABLE.
        result = connection.execute(
            text("SHOW CREATE TABLE " + self.identifier_preparer.quote_identifier(table_name))
        )
        row = result.fetchone()
        if not row:
            return []

        ddl = row[1]
        fk_pattern = re.compile(
            r"CONSTRAINT\s+\[(\w+)\]\s+FOREIGN\s+KEY\s+\(([^)]+)\)\s+"
            r"REFERENCES\s+\[(?:\w+\.)?(\w+)\]\s+\(([^)]+)\)",
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
        return fks

    def get_indexes(self, connection, table_name, schema=None, **kw):
        result = connection.execute(
            text(
                "SELECT i.index_name, i.is_unique, i.is_primary_key, "
                "       k.key_attr_name, k.key_order "
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
            col_name = row[3]
            if idx_name not in indexes:
                indexes[idx_name] = {
                    "name": idx_name,
                    "unique": is_unique,
                    "column_names": [],
                }
            indexes[idx_name]["column_names"].append(col_name)
        return list(indexes.values())

    def _get_server_version_info(self, connection):
        dbapi_conn = connection.connection.dbapi_connection
        version_str = dbapi_conn.server_version()
        return tuple(int(x) for x in version_str.split("."))


dialect = CubridDialect
