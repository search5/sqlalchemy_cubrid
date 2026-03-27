# sqlalchemy_cubrid/compiler.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy import types as sqltypes
from sqlalchemy.sql import compiler
from sqlalchemy.sql.selectable import _CompoundSelectKeyword


class CubridCompiler(compiler.SQLCompiler):
    # Use CUBRID-native keywords for set operations (10.2~11.4 compat)
    compound_keywords = {
        _CompoundSelectKeyword.UNION: "UNION",
        _CompoundSelectKeyword.UNION_ALL: "UNION ALL",
        _CompoundSelectKeyword.EXCEPT: "DIFFERENCE",
        _CompoundSelectKeyword.EXCEPT_ALL: "DIFFERENCE ALL",
        _CompoundSelectKeyword.INTERSECT: "INTERSECTION",
        _CompoundSelectKeyword.INTERSECT_ALL: "INTERSECTION ALL",
    }


class CubridDDLCompiler(compiler.DDLCompiler):
    def get_column_specification(self, column, **kwargs):
        colspec = (
            self.preparer.format_column(column)
            + " "
            + self.dialect.type_compiler_instance.process(
                column.type, type_expression=column
            )
        )

        if column.primary_key and column.autoincrement is not False \
                and column.type._type_affinity is sqltypes.Integer:
            colspec += " AUTO_INCREMENT"

        default = self.get_column_default_string(column)
        if default is not None:
            colspec += " DEFAULT " + default

        if not column.nullable:
            colspec += " NOT NULL"

        return colspec


class CubridTypeCompiler(compiler.GenericTypeCompiler):
    # CUBRID has no BOOLEAN column type (per official docs)
    def visit_BOOLEAN(self, type_, **kw):
        return "SMALLINT"

    # CUBRID has no TEXT type; use STRING (= VARCHAR max length)
    def visit_TEXT(self, type_, **kw):
        return "STRING"

    def visit_text(self, type_, **kw):
        return "STRING"

    # CUBRID DATETIME has millisecond (3-digit) precision
    def visit_DATETIME(self, type_, **kw):
        return "DATETIME"

    def visit_TIMESTAMP(self, type_, **kw):
        return "TIMESTAMP"

    def visit_DATE(self, type_, **kw):
        return "DATE"

    def visit_TIME(self, type_, **kw):
        return "TIME"

    def visit_BLOB(self, type_, **kw):
        return "BLOB"

    def visit_CLOB(self, type_, **kw):
        return "CLOB"

    # LargeBinary -> BIT VARYING (CUBRID inline binary storage)
    def visit_large_binary(self, type_, **kw):
        return "BIT VARYING(1073741823)"

    def visit_FLOAT(self, type_, **kw):
        # CUBRID: FLOAT(p>7) → DOUBLE
        if type_.precision is not None and type_.precision > 7:
            return "DOUBLE"
        return "FLOAT"

    def visit_DOUBLE(self, type_, **kw):
        return "DOUBLE"
