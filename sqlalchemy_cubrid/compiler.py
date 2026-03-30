# sqlalchemy_cubrid/compiler.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy import types as sqltypes
from sqlalchemy.sql import coercions, compiler, roles
from sqlalchemy.sql.schema import Identity, Sequence
from sqlalchemy.sql.selectable import _CompoundSelectKeyword


class CubridCompiler(compiler.SQLCompiler):
    """SQL statement compiler for CUBRID.

    Handles CUBRID-specific syntax including LIMIT/OFFSET, SERIAL
    references, hierarchical queries (CONNECT BY), REPLACE INTO,
    FOR UPDATE, ON DUPLICATE KEY UPDATE, MERGE, and OID path
    expressions.
    """

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
            text += "\n LIMIT " + self.process(select._limit_clause, **kw)
        if select._offset_clause is not None:
            if select._limit_clause is None:
                # CUBRID OFFSET requires LIMIT; use large number
                text += "\n LIMIT 9999999999"
            text += " OFFSET " + self.process(select._offset_clause, **kw)
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

    def visit_rownum(self, element, **kw):
        return "ROWNUM"

    def visit_sys_connect_by_path(self, element, **kw):
        # Separator must be a string literal in CUBRID (not a bind param).
        # Use render_literal_value for proper escaping.
        sep_literal = self.render_literal_value(
            element.separator, sqltypes.String()
        )
        return "SYS_CONNECT_BY_PATH(%s, %s)" % (
            self.process(element.column, **kw),
            sep_literal,
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
            siblings = [
                self.process(col, **kw) for col in element.order_siblings_by
            ]
            text += " ORDER SIBLINGS BY " + ", ".join(siblings)
        return text

    # -- OID dereference (path expression) --

    def visit_oid_deref(self, element, **kw):
        col_str = self.process(element.oid_column, **kw)
        return "%s.%s" % (col_str, element.attr_name)

    # -- REPLACE INTO --

    def visit_insert(self, insert_stmt, **kw):
        from sqlalchemy_cubrid.dml import Replace

        text = super().visit_insert(insert_stmt, **kw)
        if isinstance(insert_stmt, Replace):
            text = "REPLACE" + text[len("INSERT") :]
        return text

    # -- FOR UPDATE clause --

    def for_update_clause(self, select, **kw):
        if select._for_update_arg is None:
            return ""

        if select._for_update_arg.read:
            # CUBRID does not support FOR SHARE / LOCK IN SHARE MODE
            return ""

        tmp = " FOR UPDATE"

        if select._for_update_arg.of:
            tmp += " OF " + ", ".join(
                self.process(col, ashint=True, use_schema=False, **kw)
                for col in select._for_update_arg.of
            )

        return tmp

    # -- ON DUPLICATE KEY UPDATE --

    def visit_on_duplicate_key_update(self, on_duplicate, **kw):
        # CUBRID does not support VALUES() function in ON DUPLICATE KEY UPDATE.
        # Users should pass explicit values or column expressions instead of
        # referencing stmt.inserted.
        statement = self.current_executable

        if on_duplicate._parameter_ordering:
            parameter_ordering = [
                coercions.expect(roles.DMLColumnRole, key)
                for key in on_duplicate._parameter_ordering
            ]
            ordered_keys = set(parameter_ordering)
            cols = [
                statement.table.c[key]
                for key in parameter_ordering
                if key in statement.table.c
            ] + [c for c in statement.table.c if c.key not in ordered_keys]
        else:
            cols = list(statement.table.c)

        clauses = []
        for col in cols:
            if col.key in on_duplicate.update:
                val = on_duplicate.update[col.key]
                clauses.append(
                    "%s = %s"
                    % (
                        self.preparer.quote(col.name),
                        self.process(
                            coercions.expect(roles.ExpressionElementRole, val),
                            **kw,
                        ),
                    )
                )

        return "ON DUPLICATE KEY UPDATE " + ", ".join(clauses)

    # -- MERGE statement visit method --

    def visit_cubrid_merge(self, element, **kw):
        text = "MERGE INTO " + self.process(element.target, asfrom=True, **kw)
        text += " USING " + self.process(element._source, asfrom=True, **kw)
        text += " ON (" + self.process(element._on_condition, **kw) + ")"

        # WHEN MATCHED THEN UPDATE
        if element._update_values:
            text += " WHEN MATCHED"
            if element._update_condition is not None:
                text += " AND " + self.process(element._update_condition, **kw)
            text += " THEN UPDATE SET "
            assignments = []
            for col, val in element._update_values.items():
                assignments.append(
                    self.process(col, **kw) + " = " + self.process(val, **kw)
                )
            text += ", ".join(assignments)

        # WHEN MATCHED THEN DELETE
        if element._delete:
            text += " WHEN MATCHED"
            if element._delete_condition is not None:
                text += " AND " + self.process(element._delete_condition, **kw)
            text += " THEN DELETE"

        # WHEN NOT MATCHED THEN INSERT
        if element._insert_values:
            cols = []
            vals = []
            for col, val in element._insert_values.items():
                cols.append(self.process(col, **kw))
                vals.append(self.process(val, **kw))
            text += " WHEN NOT MATCHED"
            if element._insert_condition is not None:
                text += " AND " + self.process(element._insert_condition, **kw)
            text += " THEN INSERT (%s) VALUES (%s)" % (
                ", ".join(cols),
                ", ".join(vals),
            )
        return text

    # -- CAST: map SQLAlchemy types to CUBRID DDL names --

    def visit_cast(self, cast, **kw):
        # Delegate type rendering to the CUBRID type compiler so that
        # CAST(x AS TEXT) becomes CAST(x AS STRING), etc.
        type_clause = cast.typeclause._compiler_dispatch(self, **kw)
        return "CAST(%s AS %s)" % (
            self.process(cast.clause, **kw),
            type_clause,
        )

    # -- REGEXP / RLIKE operators --

    def visit_regexp_match_op_binary(self, binary, operator, **kw):
        return self._generate_generic_binary(binary, " REGEXP ", **kw)

    def visit_not_regexp_match_op_binary(self, binary, operator, **kw):
        return "NOT (%s)" % self.visit_regexp_match_op_binary(
            binary, operator, **kw
        )


class CubridDDLCompiler(compiler.DDLCompiler):
    """DDL compiler for CUBRID.

    Generates CUBRID-specific DDL for SERIAL (sequence), index, table,
    and column operations. Handles AUTO_INCREMENT, DONT_REUSE_OID,
    and column/table comments.
    """

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

    def visit_create_index(self, create, **kw):
        index = create.element
        text = "CREATE "
        if index.unique:
            text += "UNIQUE "

        # CUBRID-specific: REVERSE index
        if index.dialect_options.get("cubrid", {}).get("reverse"):
            text += "REVERSE "

        text += "INDEX "
        text += "%s ON %s " % (
            self._prepared_index_name(index),
            self.preparer.format_table(index.table),
        )

        # CUBRID-specific: function-based index
        func_expr = index.dialect_options.get("cubrid", {}).get("function")
        if func_expr:
            text += "(%s)" % func_expr
        else:
            columns = [
                self.sql_compiler.process(
                    col, include_table=False, literal_binds=True
                )
                for col in index.expressions
            ]
            text += "(%s)" % ", ".join(columns)

        # CUBRID-specific: filtered (partial) index
        filter_expr = index.dialect_options.get("cubrid", {}).get("filtered")
        if filter_expr:
            text += " WHERE %s" % filter_expr

        return text

    def visit_drop_index(self, drop, **kw):
        # CUBRID requires: DROP INDEX index_name ON table_name
        # Note: CUBRID does not support IF EXISTS for DROP INDEX.
        index = drop.element
        text = "DROP INDEX %s ON %s" % (
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
        if (
            not has_sequence
            and column.primary_key
            and column.autoincrement is not False
            and column.type._type_affinity is sqltypes.Integer
            and (column.server_default is None or has_identity)
            and (
                column.table is None
                or column is column.table._autoincrement_column
            )
        ):
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
        # DONT_REUSE_OID makes the table referable by OID columns (11.0+)
        if table.dialect_options.get("cubrid", {}).get("dont_reuse_oid"):
            version = getattr(self.dialect, "_cubrid_version", (0,))
            if version >= (11, 0):
                table_opts.append("DONT_REUSE_OID")
        if table.comment is not None:
            table_opts.append(
                "COMMENT="
                + self.sql_compiler.render_literal_value(
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
    """Type compiler for CUBRID.

    Maps SQLAlchemy abstract types to CUBRID DDL type names. Notable
    mappings: BOOLEAN → SMALLINT, TEXT → STRING, LargeBinary → BIT
    VARYING, Float (no precision) → DOUBLE, NCHAR → CHAR.
    """

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

    # CUBRID OID reference: column type is the referenced class name
    def visit_cubrid_oid(self, type_, **kw):
        return type_.class_name
