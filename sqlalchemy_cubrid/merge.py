# sqlalchemy_cubrid/merge.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID MERGE statement support.

CUBRID MERGE syntax::

    MERGE INTO target [alias]
    USING source [alias]
    ON (join_condition)
    [WHEN MATCHED [AND cond] THEN UPDATE SET col = expr, ...]
    [WHEN MATCHED [AND cond] THEN DELETE]
    [WHEN NOT MATCHED [AND cond] THEN INSERT (cols) VALUES (exprs)]

Usage::

    from sqlalchemy_cubrid.merge import Merge

    stmt = (
        Merge(target_table)
        .using(source_table)
        .on(target_table.c.id == source_table.c.id)
        .when_matched_then_update({
            target_table.c.name: source_table.c.name,
        })
        .when_not_matched_then_insert({
            target_table.c.id: source_table.c.id,
            target_table.c.name: source_table.c.name,
        })
    )
    conn.execute(stmt)

    # Conditional WHEN and DELETE:
    stmt = (
        Merge(target)
        .using(source)
        .on(target.c.id == source.c.id)
        .when_matched_then_update(
            {target.c.name: source.c.name},
            condition=source.c.active == 1,
        )
        .when_matched_then_delete(
            condition=source.c.active == 0,
        )
    )
"""

from sqlalchemy.sql.elements import ClauseElement, Executable


class Merge(Executable, ClauseElement):
    """CUBRID MERGE statement construct.

    Builder-style API for constructing MERGE INTO ... USING ... ON ...
    """

    __visit_name__ = "cubrid_merge"
    inherit_cache = False

    def __init__(self, target):
        self.target = target
        self._source = None
        self._on_condition = None
        self._update_values = None
        self._update_condition = None
        self._delete = False
        self._delete_condition = None
        self._insert_values = None
        self._insert_condition = None

    def using(self, source):
        """Set the USING source table or subquery."""
        self._source = source
        return self

    def on(self, condition):
        """Set the ON join condition."""
        self._on_condition = condition
        return self

    def when_matched_then_update(self, values, condition=None):
        """Set WHEN MATCHED THEN UPDATE SET values.

        Args:
            values: dict mapping target columns to source expressions.
            condition: optional AND condition for WHEN MATCHED clause.
        """
        self._update_values = values
        self._update_condition = condition
        return self

    def when_matched_then_delete(self, condition=None):
        """Set WHEN MATCHED THEN DELETE.

        Args:
            condition: optional AND condition for WHEN MATCHED clause.
        """
        self._delete = True
        self._delete_condition = condition
        return self

    def when_not_matched_then_insert(self, values, condition=None):
        """Set WHEN NOT MATCHED THEN INSERT values.

        Args:
            values: dict mapping target columns to source expressions.
            condition: optional AND condition for WHEN NOT MATCHED clause.
        """
        self._insert_values = values
        self._insert_condition = condition
        return self


# Compiler visit method is registered on CubridCompiler in compiler.py
