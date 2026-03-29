# sqlalchemy_cubrid/functions.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy.sql import functions
from sqlalchemy import Integer


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
