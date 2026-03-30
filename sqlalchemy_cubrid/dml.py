# sqlalchemy_cubrid/dml.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID-specific DML constructs.

- INSERT ... ON DUPLICATE KEY UPDATE
- REPLACE INTO
- TRUNCATE TABLE
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import exc, util
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import DDLElement
from sqlalchemy.sql._typing import _DMLTableArgument
from sqlalchemy.sql.base import (
    ColumnCollection,
    ReadOnlyColumnCollection,
    _exclusive_against,
    _generative,
)
from sqlalchemy.sql.dml import Insert as StandardInsert
from sqlalchemy.sql.elements import ClauseElement, KeyedColumnElement
from sqlalchemy.sql.expression import alias
from sqlalchemy.sql.selectable import NamedFromClause
from sqlalchemy.util.typing import Self

__all__ = ("Insert", "insert", "Replace", "replace", "Truncate", "truncate")


_UpdateArg = (
    Mapping[Any, Any] | list[tuple[str, Any]] | ColumnCollection[Any, Any]
)


def insert(table: _DMLTableArgument) -> Insert:
    """Construct a CUBRID-specific INSERT with ON DUPLICATE KEY UPDATE."""
    return Insert(table)


def replace(table: _DMLTableArgument) -> Replace:
    """Construct a CUBRID REPLACE INTO statement."""
    return Replace(table)


class Insert(StandardInsert):
    """CUBRID-specific INSERT with ON DUPLICATE KEY UPDATE support.

    Use :func:`sqlalchemy_cubrid.dml.insert` to create instances.
    """

    stringify_dialect = "cubrid"
    inherit_cache = False

    @property
    def inserted(
        self,
    ) -> ReadOnlyColumnCollection[str, KeyedColumnElement[Any]]:
        """Provide the "inserted" namespace for ON DUPLICATE KEY UPDATE.

        Columns referenced via this attribute render as ``VALUES(col)``
        inside the ON DUPLICATE KEY UPDATE clause.
        """
        return self.inserted_alias.columns

    @util.memoized_property
    def inserted_alias(self) -> NamedFromClause:
        return alias(self.table, name="inserted")

    @_generative
    @_exclusive_against(
        "_post_values_clause",
        msgs={
            "_post_values_clause": "This Insert construct already "
            "has an ON DUPLICATE KEY clause present"
        },
    )
    def on_duplicate_key_update(self, *args: _UpdateArg, **kw: Any) -> Self:
        """Specify the ON DUPLICATE KEY UPDATE clause.

        :param \\**kw: Column keys linked to UPDATE values.
        :param \\*args: A dictionary or list of 2-tuples as a single
            positional argument.
        """
        if args and kw:
            raise exc.ArgumentError(
                "Can't pass kwargs and positional arguments simultaneously"
            )

        if args:
            if len(args) > 1:
                raise exc.ArgumentError(
                    "Only a single dictionary or list of tuples "
                    "is accepted positionally."
                )
            values = args[0]
        else:
            values = kw

        self._post_values_clause = OnDuplicateClause(
            self.inserted_alias, values
        )
        return self


class OnDuplicateClause(ClauseElement):
    """Represents ON DUPLICATE KEY UPDATE clause."""

    __visit_name__ = "on_duplicate_key_update"

    _parameter_ordering: list[str] | None = None
    update: dict[str, Any]
    stringify_dialect = "cubrid"

    def __init__(
        self, inserted_alias: NamedFromClause, update: _UpdateArg
    ) -> None:
        self.inserted_alias = inserted_alias

        if isinstance(update, list) and (
            update and isinstance(update[0], tuple)
        ):
            self._parameter_ordering = [key for key, value in update]
            update = dict(update)

        if isinstance(update, dict):
            if not update:
                raise ValueError(
                    "update parameter dictionary must not be empty"
                )
        elif isinstance(update, ColumnCollection):
            update = dict(update)
        else:
            raise ValueError(
                "update parameter must be a non-empty dictionary "
                "or a ColumnCollection such as the `.c.` collection "
                "of a Table object"
            )
        self.update = update


class Replace(StandardInsert):
    """CUBRID REPLACE INTO statement.

    Behaves like INSERT, but deletes and re-inserts on duplicate key.
    Use :func:`sqlalchemy_cubrid.dml.replace` to create instances.
    """

    stringify_dialect = "cubrid"
    inherit_cache = False


class Truncate(DDLElement):
    """CUBRID TRUNCATE TABLE statement.

    Removes all rows from a table without logging individual row deletions::

        from sqlalchemy_cubrid.dml import truncate
        conn.execute(truncate("my_table"))
    """

    def __init__(self, table_name):
        self.table_name = table_name


def truncate(table_name: str) -> Truncate:
    """Construct a CUBRID TRUNCATE TABLE statement."""
    return Truncate(table_name)


@compiles(Truncate, "cubrid")
def visit_truncate(element, compiler, **kw):
    return "TRUNCATE TABLE %s" % compiler.preparer.quote_identifier(
        element.table_name
    )
