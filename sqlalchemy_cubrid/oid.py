# sqlalchemy_cubrid/oid.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID OID (Object Identifier) reference support.

CUBRID is an object-relational DBMS where every row has an OID. A column
can reference another class by using that class name as the column type,
storing OID references to instances of the referenced class.

Only tables created with ``DONT_REUSE_OID`` can be referenced by OID
columns (the default since CUBRID 10.x is ``REUSE_OID``).

Usage::

    from sqlalchemy_cubrid.oid import (
        CubridOID, deref, CreateTableDontReuseOID,
    )

    # Create a referable table
    ddl = CreateTableDontReuseOID(
        "person",
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
    )
    ddl.create(engine)

    # Create a table with OID reference column
    conn.execute(text(
        "CREATE TABLE department ("
        "  id INT PRIMARY KEY,"
        "  manager person"
        ")"
    ))

    # Query with path expression (dereferencing)
    from sqlalchemy import select, literal_column
    stmt = select(deref(literal_column("manager"), "name")).select_from(
        text("department")
    )
    # Compiles to: SELECT manager.name FROM department
"""

from sqlalchemy import String
from sqlalchemy import types as sa_types
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import DDLElement
from sqlalchemy.sql.elements import ColumnElement


class CubridOID(sa_types.UserDefinedType):
    """CUBRID OID reference type.

    The column stores an OID reference to an instance of the specified class.
    In DDL, the type is rendered as the bare class name::

        Column("manager", CubridOID("person"))
        # DDL: manager person

    :param class_name: Name of the referenced CUBRID class (table).
    """

    cache_ok = True

    def __init__(self, class_name):
        self.class_name = class_name

    def get_col_spec(self):
        return self.class_name

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return value

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            return value

        return process


class OIDDeref(ColumnElement):
    """Path expression for OID dereferencing.

    Compiles to ``column.attr_name`` in SQL, allowing navigation through
    OID references::

        deref(table.c.manager, "name")
        # SQL: manager.name

    Chainable for multi-level dereferencing::

        deref(deref(table.c.dept, "head"), "name")
        # SQL: dept.head.name
    """

    __visit_name__ = "oid_deref"
    inherit_cache = False

    def __init__(self, oid_column, attr_name, type_=None):
        self.oid_column = oid_column
        self.attr_name = attr_name
        self.type = type_ if type_ is not None else String()


class CreateTableDontReuseOID(DDLElement):
    """DDL construct for creating a referable table (DONT_REUSE_OID).

    Tables must be created with DONT_REUSE_OID to be used as OID reference
    targets. This construct generates::

        CREATE TABLE name (columns) DONT_REUSE_OID

    :param name: Table name.
    :param columns: Column definitions.
    """

    def __init__(self, name, *columns):
        self.name = name
        self.columns = columns


@compiles(CreateTableDontReuseOID, "cubrid")
def visit_create_table_dont_reuse_oid(element, compiler, **kw):
    preparer = compiler.preparer
    table_name = preparer.quote_identifier(element.name)

    col_specs = []
    for col in element.columns:
        col_spec = compiler.get_column_specification(col)
        col_specs.append(col_spec)

    # DONT_REUSE_OID is supported on CUBRID 11.0+
    version = getattr(compiler.dialect, "_cubrid_version", (0,))
    suffix = " DONT_REUSE_OID" if version >= (11, 0) else ""
    text = "CREATE TABLE %s (%s)%s" % (
        table_name,
        ", ".join(col_specs),
        suffix,
    )
    return text


def deref(oid_column, attr_name, type_=None):
    """Create an OID dereference (path expression).

    :param oid_column: The OID column or a previous deref expression.
    :param attr_name: Attribute name to dereference.
    :param type_: Optional SQLAlchemy type for the result (defaults to String).
    :returns: OIDDeref expression that compiles to ``column.attr_name``.
    """
    return OIDDeref(oid_column, attr_name, type_=type_)
