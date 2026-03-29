# sqlalchemy_cubrid/compiler.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy import types as sqltypes
from sqlalchemy.sql import compiler
from sqlalchemy.sql.schema import Identity, Sequence
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

    def default_from(self):
        # CUBRID requires FROM when WHERE is present without a table
        return " FROM db_root"

    def limit_clause(self, select, **kw):
        text = ""
        if select._limit_clause is not None:
            text += "\n LIMIT " + self.process(
                select._limit_clause, **kw
            )
        if select._offset_clause is not None:
            if select._limit_clause is None:
                # CUBRID OFFSET requires LIMIT; use large number
                text += "\n LIMIT 9999999999"
            text += " OFFSET " + self.process(
                select._offset_clause, **kw
            )
        return text

    def visit_sequence(self, seq, **kw):
        # CUBRID uses serial_name.NEXT_VALUE (not NEXTVAL FOR)
        return self.preparer.format_sequence(seq) + ".NEXT_VALUE"

    # -- Hierarchical query (CONNECT BY) visit methods --

    def visit_prior(self, element, **kw):
        return "PRIOR " + self.process(element.column, **kw)

    def visit_level_col(self, element, **kw):
        return "LEVEL"

    def visit_connect_by_isleaf(self, element, **kw):
        return "CONNECT_BY_ISLEAF"

    def visit_connect_by_iscycle(self, element, **kw):
        return "CONNECT_BY_ISCYCLE"

    def visit_sys_connect_by_path(self, element, **kw):
        # Separator must be a string literal in CUBRID (not a bind param)
        sep = element.separator.replace("'", "''")
        return "SYS_CONNECT_BY_PATH(%s, '%s')" % (
            self.process(element.column, **kw),
            sep,
        )

    def visit_connect_by_root(self, element, **kw):
        return "CONNECT_BY_ROOT " + self.process(element.column, **kw)

    def visit_hierarchical_select(self, element, **kw):
        col_strs = [self.process(col, **kw) for col in element.columns]
        text = "SELECT " + ", ".join(col_strs)
        text += " FROM " + self.process(element.table, asfrom=True, **kw)
        if element.where is not None:
            text += " WHERE " + self.process(element.where, **kw)
        if element.start_with is not None:
            text += " START WITH " + self.process(element.start_with, **kw)
        text += " CONNECT BY "
        if element.nocycle:
            text += "NOCYCLE "
        text += self.process(element.connect_by, **kw)
        if element.order_siblings_by:
            siblings = [self.process(col, **kw) for col in element.order_siblings_by]
            text += " ORDER SIBLINGS BY " + ", ".join(siblings)
        return text

    # -- MERGE statement visit method --

    def visit_cubrid_merge(self, element, **kw):
        text = "MERGE INTO " + self.process(element.target, asfrom=True, **kw)
        text += " USING " + self.process(element._source, asfrom=True, **kw)
        text += " ON (" + self.process(element._on_condition, **kw) + ")"
        if element._update_values:
            text += " WHEN MATCHED THEN UPDATE SET "
            assignments = []
            for col, val in element._update_values.items():
                assignments.append(
                    self.process(col, **kw) + " = " + self.process(val, **kw)
                )
            text += ", ".join(assignments)
        if element._insert_values:
            cols = []
            vals = []
            for col, val in element._insert_values.items():
                cols.append(self.process(col, **kw))
                vals.append(self.process(val, **kw))
            text += " WHEN NOT MATCHED THEN INSERT (%s) VALUES (%s)" % (
                ", ".join(cols),
                ", ".join(vals),
            )
        return text


class CubridDDLCompiler(compiler.DDLCompiler):
    def visit_create_sequence(self, create, prefix=None, **kw):
        # CUBRID uses CREATE SERIAL (not CREATE SEQUENCE)
        seq = create.element
        text = "CREATE SERIAL %s" % self.preparer.format_sequence(seq)

        if seq.start is not None:
            text += " START WITH %d" % seq.start
        if seq.increment is not None:
            text += " INCREMENT BY %d" % seq.increment
        if seq.minvalue is not None:
            text += " MINVALUE %d" % seq.minvalue
        elif seq.nominvalue:
            text += " NOMINVALUE"
        if seq.maxvalue is not None:
            text += " MAXVALUE %d" % seq.maxvalue
        elif seq.nomaxvalue:
            text += " NOMAXVALUE"
        if seq.cycle is not None:
            text += " CYCLE" if seq.cycle else " NOCYCLE"
        if seq.cache is not None:
            text += " CACHE %d" % seq.cache
        return text

    def visit_drop_sequence(self, drop, **kw):
        # CUBRID uses DROP SERIAL (not DROP SEQUENCE)
        return "DROP SERIAL IF EXISTS %s" % self.preparer.format_sequence(
            drop.element
        )

    def visit_drop_index(self, drop, **kw):
        # CUBRID requires: DROP INDEX index_name ON table_name
        index = drop.element
        text = "DROP INDEX "
        if drop.if_exists:
            text += "IF EXISTS "
        text += "%s ON %s" % (
            self._prepared_index_name(index),
            self.preparer.format_table(index.table),
        )
        return text

    def get_column_specification(self, column, **kwargs):
        colspec = (
            self.preparer.format_column(column)
            + " "
            + self.dialect.type_compiler_instance.process(
                column.type, type_expression=column
            )
        )

        # AUTO_INCREMENT: skip if column has Sequence default or is not the
        # designated autoincrement column (CUBRID allows only 1 per table)
        # Identity() is rendered as AUTO_INCREMENT (CUBRID has no IDENTITY).
        has_sequence = isinstance(column.default, Sequence)
        has_identity = isinstance(column.server_default, Identity)
        if not has_sequence \
                and column.primary_key and column.autoincrement is not False \
                and column.type._type_affinity is sqltypes.Integer \
                and (column.server_default is None or has_identity) \
                and (column.table is None
                     or column is column.table._autoincrement_column):
            colspec += " AUTO_INCREMENT"

        default = self.get_column_default_string(column)
        if default is not None:
            colspec += " DEFAULT " + default

        if not column.nullable:
            colspec += " NOT NULL"

        if column.comment is not None:
            colspec += " COMMENT " + self.sql_compiler.render_literal_value(
                column.comment, sqltypes.String()
            )

        return colspec

    def post_create_table(self, table):
        table_opts = []
        if table.comment is not None:
            table_opts.append(
                "COMMENT=" + self.sql_compiler.render_literal_value(
                    table.comment, sqltypes.String()
                )
            )
        if table_opts:
            return " " + " ".join(table_opts)
        return ""


    def visit_set_table_comment(self, create, **kw):
        return "ALTER TABLE %s COMMENT=%s" % (
            self.preparer.format_table(create.element),
            self.sql_compiler.render_literal_value(
                create.element.comment, sqltypes.String()
            ),
        )

    def visit_drop_table_comment(self, drop, **kw):
        return "ALTER TABLE %s COMMENT=''" % self.preparer.format_table(
            drop.element
        )

    def visit_set_column_comment(self, create, **kw):
        return "ALTER TABLE %s MODIFY %s COMMENT %s" % (
            self.preparer.format_table(create.element.table),
            self.preparer.format_column(create.element),
            self.sql_compiler.render_literal_value(
                create.element.comment, sqltypes.String()
            ),
        )

    def visit_drop_column_comment(self, drop, **kw):
        return "ALTER TABLE %s MODIFY %s COMMENT ''" % (
            self.preparer.format_table(drop.element.table),
            self.preparer.format_column(drop.element),
        )

    def visit_identity_column(self, identity, **kw):
        # CUBRID has no IDENTITY; handled via AUTO_INCREMENT in
        # get_column_specification. Return empty string to suppress
        # the default GENERATED AS IDENTITY clause.
        return ""


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
        # CUBRID FLOAT = single precision (7 significant digits).
        # Generic Float() (no precision) maps to DOUBLE for better accuracy.
        if type_.precision is not None:
            if type_.precision > 7:
                return "DOUBLE"
            return "FLOAT"
        return "DOUBLE"

    def visit_DOUBLE(self, type_, **kw):
        return "DOUBLE"

    def visit_DOUBLE_PRECISION(self, type_, **kw):
        return "DOUBLE"

    # CUBRID supports JSON since 10.2
    def visit_JSON(self, type_, **kw):
        return "JSON"

    # NCHAR/NCHAR VARYING removed since CUBRID 9.0; map to CHAR/VARCHAR
    def visit_NCHAR(self, type_, **kw):
        if type_.length:
            return "CHAR(%d)" % type_.length
        return "CHAR"

    def visit_NVARCHAR(self, type_, **kw):
        if type_.length:
            return "VARCHAR(%d)" % type_.length
        return "VARCHAR"

    def visit_unicode(self, type_, **kw):
        if type_.length:
            return "VARCHAR(%d)" % type_.length
        return "VARCHAR"

    def visit_unicode_text(self, type_, **kw):
        return "STRING"
