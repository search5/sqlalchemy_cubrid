# sqlalchemy_cubrid/alembic_impl.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""Alembic migration support for CUBRID.

Registers ``CubridImpl`` so Alembic can emit CUBRID-compatible DDL
during ``alembic upgrade`` / ``alembic downgrade``.
"""

from alembic.ddl.impl import DefaultImpl

from sqlalchemy_cubrid.types import (
    CubridSet,
    CubridMultiset,
    CubridList,
)

_COLLECTION_CLASSES = (CubridSet, CubridMultiset, CubridList)


class CubridImpl(DefaultImpl):
    """Alembic implementation for the CUBRID dialect."""

    __dialect__ = "cubrid"

    # CUBRID auto-commits DDL; cannot roll back failed migrations.
    transactional_ddl = False

    def render_type(self, type_obj, autogen_context):
        """Render CUBRID collection types as importable Python code.

        For standard types, delegates to the parent class.
        """
        if isinstance(type_obj, _COLLECTION_CLASSES):
            mod = "sqlalchemy_cubrid.types"
            cls_name = type(type_obj).__name__
            elem = type_obj.element_type
            autogen_context.imports.add(
                "from %s import %s" % (mod, cls_name)
            )
            return "%s(%r)" % (cls_name, elem)

        # Let Alembic handle standard types
        return False

    def compare_type(self, inspector_column, metadata_column):
        """Detect type changes for CUBRID collection types.

        Collection element types are compared case-insensitively.
        For standard types, delegates to the parent class.
        """
        conn_type = inspector_column.type
        meta_type = metadata_column.type

        # Both must be collection types to do custom comparison
        if isinstance(conn_type, _COLLECTION_CLASSES) and isinstance(
            meta_type, _COLLECTION_CLASSES
        ):
            if type(conn_type) is not type(meta_type):
                return True  # Different collection kind
            # Compare element types case-insensitively
            conn_elem = str(conn_type.element_type).strip().upper()
            meta_elem = str(meta_type.element_type).strip().upper()
            return conn_elem != meta_elem

        # If only one side is a collection type, types differ
        if isinstance(conn_type, _COLLECTION_CLASSES) or isinstance(
            meta_type, _COLLECTION_CLASSES
        ):
            return True

        return super().compare_type(inspector_column, metadata_column)
