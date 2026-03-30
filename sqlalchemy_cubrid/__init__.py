# sqlalchemy_cubrid/__init__.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy.dialects import registry

from sqlalchemy_cubrid.dblink import (  # noqa: F401
    CreateServer,
    DropServer,
    DbLink,
)
from sqlalchemy_cubrid.dml import (  # noqa: F401
    insert, Insert, replace, Replace, truncate, Truncate,
)
from sqlalchemy_cubrid.functions import (  # noqa: F401
    incr, decr, group_concat, nvl, nvl2, decode, if_, ifnull,
)
from sqlalchemy_cubrid.hierarchical import (  # noqa: F401
    HierarchicalSelect,
    prior,
    level_col,
    sys_connect_by_path,
    connect_by_root,
    connect_by_isleaf,
    connect_by_iscycle,
    rownum,
)
from sqlalchemy_cubrid.inheritance import (  # noqa: F401
    CreateTableUnder,
    DropTableInheritance,
    get_super_class,
    get_sub_classes,
    get_inherited_columns,
)
from sqlalchemy_cubrid.merge import Merge  # noqa: F401
from sqlalchemy_cubrid.oid import (  # noqa: F401
    CubridOID,
    OIDDeref,
    deref,
    CreateTableDontReuseOID,
)
from sqlalchemy_cubrid.partition import (  # noqa: F401
    PartitionByRange,
    PartitionByHash,
    PartitionByList,
    RangePartition,
    HashPartition,
    ListPartition,
)
from sqlalchemy_cubrid.trace import trace_query, QueryTracer  # noqa: F401

__version__ = "1.0.0"

registry.register("cubrid", "sqlalchemy_cubrid.dialect", "CubridDialect")
registry.register("cubrid.pycubrid", "sqlalchemy_cubrid.dialect", "CubridDialect")
