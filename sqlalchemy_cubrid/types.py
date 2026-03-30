# sqlalchemy_cubrid/types.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy import types as sa_types
from sqlalchemy.sql import sqltypes


class _NumericType:
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
        return f"{self._collection_keyword}_OF({self.element_type})"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return value

        return process

    @staticmethod
    def _parse_collection_bytes(raw):
        """Parse pycubrid's raw collection binary format.

        Wire format: type(4LE) + count(4LE) + elements
        Each element: size(1byte, includes null) + data(size bytes) + 3-byte pad
        Last element has no trailing pad.
        """
        import struct

        if isinstance(raw, str):
            data = raw.encode("latin-1")
        elif isinstance(raw, bytes):
            data = raw
        else:
            return None

        if len(data) < 8:
            return None

        count = struct.unpack_from("<I", data, 4)[0]
        offset = 8
        results = []
        for i in range(count):
            if offset >= len(data):
                break
            size = data[offset]
            offset += 1
            is_last = i == count - 1
            # Last element may lack null terminator, so only size-1 bytes.
            available = len(data) - offset
            if size > 1:
                read_len = min(size - 1, available)
                val = data[offset : offset + read_len].decode(
                    "utf-8", errors="replace"
                )
            else:
                val = ""
            offset += min(size, available)
            if not is_last:
                offset += 3  # inter-element padding
            results.append(val)
        return results


class CubridSet(_CollectionType):
    """CUBRID SET type. Unordered, no duplicates."""

    cache_ok = True
    _collection_keyword = "SET"

    def result_processor(self, dialect, coltype):
        parse = self._parse_collection_bytes

        def process(value):
            if value is None:
                return None
            if isinstance(value, set):
                return value
            parsed = parse(value)
            if parsed is not None:
                return set(parsed)
            # Fallback: convert to strings to avoid set(bytes) → {int, ...}
            if isinstance(value, (bytes, bytearray)):
                return set()
            return set(str(v) for v in value)

        return process


class CubridMultiset(_CollectionType):
    """CUBRID MULTISET type. Unordered, allows duplicates."""

    cache_ok = True
    _collection_keyword = "MULTISET"

    def result_processor(self, dialect, coltype):
        parse = self._parse_collection_bytes

        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return value
            parsed = parse(value)
            if parsed is not None:
                return parsed
            if isinstance(value, (bytes, bytearray)):
                return []
            return [str(v) for v in value]

        return process


class CubridList(_CollectionType):
    """CUBRID LIST/SEQUENCE type. Ordered, allows duplicates.

    Uses SEQUENCE_OF() DDL syntax (CUBRID does not support LIST_OF).
    """

    cache_ok = True
    _collection_keyword = "SEQUENCE"

    def result_processor(self, dialect, coltype):
        parse = self._parse_collection_bytes

        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return value
            parsed = parse(value)
            if parsed is not None:
                return parsed
            if isinstance(value, (bytes, bytearray)):
                return []
            return [str(v) for v in value]

        return process
