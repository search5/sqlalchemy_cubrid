# sqlalchemy_cubrid/inheritance.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID class inheritance (UNDER) support.

CUBRID is an object-relational DBMS that supports class inheritance.
A child table created with ``UNDER`` automatically inherits all columns
from the parent table.

Usage::

    from sqlalchemy_cubrid.inheritance import CreateTableUnder

    # Create parent via standard SA
    parent = Table("parent", metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
    )

    # Create child inheriting from parent, adding own columns
    child_ddl = CreateTableUnder(
        "child", metadata, "parent",
        Column("grade", Integer),
    )
    child_ddl.create(engine)
"""

from sqlalchemy import Table, Column, text
from sqlalchemy.schema import DDLElement
from sqlalchemy.ext.compiler import compiles


class CreateTableUnder(DDLElement):
    """DDL construct for ``CREATE TABLE child UNDER parent (local_columns)``.

    :param name: Name of the child table.
    :param parent_name: Name of the parent (super) table.
    :param columns: Local columns to add (not inherited).
    """

    def __init__(self, name, parent_name, *columns):
        self.name = name
        self.parent_name = parent_name
        self.columns = columns


class DropTableInheritance(DDLElement):
    """DDL construct for ``DROP TABLE child`` (inheritance-aware)."""

    def __init__(self, name):
        self.name = name


@compiles(CreateTableUnder, "cubrid")
def visit_create_table_under(element, compiler, **kw):
    preparer = compiler.preparer
    table_name = preparer.quote_identifier(element.name)
    parent_name = preparer.quote_identifier(element.parent_name)

    text = "CREATE TABLE %s UNDER %s" % (table_name, parent_name)

    if element.columns:
        col_specs = []
        for col in element.columns:
            col_spec = compiler.get_column_specification(col)
            col_specs.append(col_spec)
        text += " (%s)" % ", ".join(col_specs)

    return text


@compiles(DropTableInheritance, "cubrid")
def visit_drop_table_inheritance(element, compiler, **kw):
    preparer = compiler.preparer
    table_name = preparer.quote_identifier(element.name)
    return "DROP TABLE IF EXISTS %s" % table_name


def get_super_class(connection, table_name):
    """Return the parent class name of a CUBRID table, or None.

    :param connection: A SQLAlchemy connection.
    :param table_name: Table name to check.
    :returns: Parent class name string, or None if no parent.
    """
    result = connection.execute(
        text(
            "SELECT super_class_name FROM db_direct_super_class "
            "WHERE class_name = :name"
        ),
        {"name": table_name.lower()},
    )
    row = result.fetchone()
    return row[0] if row else None


def get_sub_classes(connection, table_name):
    """Return a list of direct child class names of a CUBRID table.

    :param connection: A SQLAlchemy connection.
    :param table_name: Parent table name.
    :returns: List of child class name strings.
    """
    result = connection.execute(
        text(
            "SELECT class_name FROM db_direct_super_class "
            "WHERE super_class_name = :name "
            "ORDER BY class_name"
        ),
        {"name": table_name.lower()},
    )
    return [row[0] for row in result]


def get_inherited_columns(connection, table_name):
    """Return column info with inheritance source.

    Each item is a dict with keys: ``name``, ``from_class`` (parent class
    name or None for local columns), ``def_order``.

    :param connection: A SQLAlchemy connection.
    :param table_name: Table name to inspect.
    :returns: List of dicts.
    """
    result = connection.execute(
        text(
            "SELECT attr_name, from_class_name, def_order "
            "FROM db_attribute "
            "WHERE class_name = :name "
            "ORDER BY def_order"
        ),
        {"name": table_name.lower()},
    )
    return [
        {
            "name": row[0],
            "from_class": row[1],
            "def_order": row[2],
        }
        for row in result
    ]
