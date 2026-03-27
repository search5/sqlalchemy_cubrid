# sqlalchemy_cubrid/types.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy.sql import sqltypes
from sqlalchemy import types as sa_types


class _NumericType(object):
    """Base for CUBRID numeric types."""

    def __init__(self, **kw):
        super().__init__(**kw)


class NUMERIC(_NumericType, sqltypes.NUMERIC):
    """CUBRID NUMERIC type.
    Default value is NUMERIC(15,0)
    """

    __visit_name__ = "NUMERIC"

    def __init__(self, precision=None, scale=None, **kw):
        super().__init__(precision=precision, scale=scale, **kw)


class _CollectionType(sa_types.UserDefinedType):
    """Base for CUBRID collection types (SET, MULTISET, LIST)."""

    cache_ok = True
    _collection_keyword = None

    def __init__(self, element_type="VARCHAR(1073741823)"):
        self.element_type = element_type

    def get_col_spec(self):
        return f"{self._collection_keyword} {self.element_type}"

    def bind_processor(self, dialect):
        # Python collection -> CUBRID literal string for raw binding
        def process(value):
            if value is None:
                return None
            return value
        return process


class CubridSet(_CollectionType):
    """CUBRID SET type. Unordered, no duplicates."""

    _collection_keyword = "SET"

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, set):
                return value
            return set(value)
        return process


class CubridMultiset(_CollectionType):
    """CUBRID MULTISET type. Unordered, allows duplicates."""

    _collection_keyword = "MULTISET"

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return value
            return list(value)
        return process


class CubridList(_CollectionType):
    """CUBRID LIST/SEQUENCE type. Ordered, allows duplicates."""

    _collection_keyword = "LIST"

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return value
            return list(value)
        return process
