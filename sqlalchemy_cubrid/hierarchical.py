# sqlalchemy_cubrid/hierarchical.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID hierarchical query (CONNECT BY) support.

CUBRID supports Oracle-style hierarchical queries:

    SELECT columns FROM table
    START WITH condition
    CONNECT BY [NOCYCLE] PRIOR parent = child
    [ORDER SIBLINGS BY columns]

Usage::

    from sqlalchemy_cubrid.hierarchical import (
        HierarchicalSelect, prior, level_col,
        sys_connect_by_path, connect_by_root, connect_by_isleaf,
    )

    stmt = HierarchicalSelect(
        table,
        columns=[table.c.id, table.c.name, level_col()],
        connect_by=prior(table.c.id) == table.c.parent_id,
        start_with=table.c.parent_id == None,
        order_siblings_by=[table.c.name],
    )
    result = conn.execute(stmt)
"""

from sqlalchemy import Integer, String
from sqlalchemy.sql.elements import ClauseElement, ColumnElement, Executable


class _Prior(ColumnElement):
    """PRIOR operator for hierarchical queries."""

    __visit_name__ = "prior"
    inherit_cache = False

    def __init__(self, column):
        self.column = column
        self.type = column.type


class _LevelCol(ColumnElement):
    """LEVEL pseudo-column for hierarchical queries."""

    __visit_name__ = "level_col"
    inherit_cache = True
    type = Integer()


class _ConnectByIsLeaf(ColumnElement):
    """CONNECT_BY_ISLEAF pseudo-column."""

    __visit_name__ = "connect_by_isleaf"
    inherit_cache = True
    type = Integer()


class _ConnectByIsCycle(ColumnElement):
    """CONNECT_BY_ISCYCLE pseudo-column (requires NOCYCLE)."""

    __visit_name__ = "connect_by_iscycle"
    inherit_cache = True
    type = Integer()


class sys_connect_by_path(ColumnElement):
    """SYS_CONNECT_BY_PATH(column, separator) function.

    CUBRID requires the separator to be a string literal (not a bind param).
    """

    __visit_name__ = "sys_connect_by_path"
    inherit_cache = False

    def __init__(self, column, separator):
        self.column = column
        self.separator = separator
        self.type = String()


class connect_by_root(ColumnElement):
    """CONNECT_BY_ROOT operator."""

    __visit_name__ = "connect_by_root"
    inherit_cache = False

    def __init__(self, column):
        self.column = column
        self.type = column.type


class HierarchicalSelect(Executable, ClauseElement):
    """CUBRID hierarchical SELECT using CONNECT BY.

    Generates::

        SELECT columns FROM table
        [WHERE filter_conditions]
        START WITH start_condition
        CONNECT BY [NOCYCLE] connect_condition
        [ORDER SIBLINGS BY columns]
    """

    __visit_name__ = "hierarchical_select"
    inherit_cache = False

    def __init__(
        self,
        table,
        columns=None,
        connect_by=None,
        start_with=None,
        where=None,
        order_siblings_by=None,
        nocycle=False,
    ):
        self.table = table
        self.columns = columns or [table]
        self.connect_by = connect_by
        self.start_with = start_with
        self.where = where
        self.order_siblings_by = order_siblings_by
        self.nocycle = nocycle


class _Rownum(ColumnElement):
    """ROWNUM pseudo-column.

    Returns the sequential number of each row in the result set,
    starting from 1.
    """

    __visit_name__ = "rownum"
    inherit_cache = True
    type = Integer()


# -- Helper functions --


def prior(column):
    """Create a PRIOR expression for CONNECT BY."""
    return _Prior(column)


def level_col():
    """Create a LEVEL pseudo-column reference."""
    return _LevelCol()


def connect_by_isleaf():
    """Create a CONNECT_BY_ISLEAF pseudo-column reference."""
    return _ConnectByIsLeaf()


def connect_by_iscycle():
    """Create a CONNECT_BY_ISCYCLE pseudo-column reference (requires NOCYCLE)."""
    return _ConnectByIsCycle()


def rownum():
    """Create a ROWNUM pseudo-column reference."""
    return _Rownum()


# Compiler visit methods are registered on CubridCompiler in compiler.py
