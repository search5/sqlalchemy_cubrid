# sqlalchemy_cubrid/functions.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy.sql import functions
from sqlalchemy import Integer, String


class incr(functions.GenericFunction):
    """CUBRID INCR() click counter function.

    Atomically increments an integer column by 1 within a SELECT statement.
    Returns the value *before* the increment.
    Only works on SMALLINT, INT, BIGINT columns.
    Result set must contain exactly one row.
    """

    type = Integer()
    name = "INCR"
    inherit_cache = True


class decr(functions.GenericFunction):
    """CUBRID DECR() click counter function.

    Atomically decrements an integer column by 1 within a SELECT statement.
    Returns the value *before* the decrement.
    Only works on SMALLINT, INT, BIGINT columns.
    Result set must contain exactly one row.
    """

    type = Integer()
    name = "DECR"
    inherit_cache = True


class group_concat(functions.GenericFunction):
    """CUBRID GROUP_CONCAT() aggregate function.

    Concatenates values from a group into a single string.
    Supports ORDER BY and SEPARATOR options::

        func.group_concat(table.c.name, separator=', ')
    """

    type = String()
    name = "GROUP_CONCAT"
    inherit_cache = True


class nvl(functions.GenericFunction):
    """CUBRID NVL(expr, default) — returns *default* when *expr* is NULL."""

    name = "NVL"
    inherit_cache = True


class nvl2(functions.GenericFunction):
    """CUBRID NVL2(expr, not_null_val, null_val).

    Returns *not_null_val* when *expr* is not NULL, else *null_val*.
    """

    name = "NVL2"
    inherit_cache = True


class decode(functions.GenericFunction):
    """CUBRID DECODE(expr, search1, result1, ..., default).

    Equivalent to a CASE expression with equality comparisons.
    """

    name = "DECODE"
    inherit_cache = True


class if_(functions.GenericFunction):
    """CUBRID IF(condition, true_val, false_val)."""

    name = "IF"
    identifier = "if_"
    inherit_cache = True


class ifnull(functions.GenericFunction):
    """CUBRID IFNULL(expr, default) — alias for NVL."""

    name = "IFNULL"
    inherit_cache = True
