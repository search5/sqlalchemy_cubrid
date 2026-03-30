# sqlalchemy_cubrid/__init__.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy.dialects import registry

from sqlalchemy_cubrid.dblink import (  # noqa: F401
    CreateServer,
    DbLink,
    DropServer,
)
from sqlalchemy_cubrid.dml import (  # noqa: F401
    Insert,
    Replace,
    Truncate,
    insert,
    replace,
    truncate,
)
from sqlalchemy_cubrid.functions import (  # noqa: F401
    decode,
    decr,
    group_concat,
    if_,
    ifnull,
    incr,
    nvl,
    nvl2,
)
from sqlalchemy_cubrid.hierarchical import (  # noqa: F401
    HierarchicalSelect,
    connect_by_iscycle,
    connect_by_isleaf,
    connect_by_root,
    level_col,
    prior,
    rownum,
    sys_connect_by_path,
)
from sqlalchemy_cubrid.inheritance import (  # noqa: F401
    CreateTableUnder,
    DropTableInheritance,
    get_inherited_columns,
    get_sub_classes,
    get_super_class,
)
from sqlalchemy_cubrid.merge import Merge  # noqa: F401
from sqlalchemy_cubrid.oid import (  # noqa: F401
    CreateTableDontReuseOID,
    CubridOID,
    OIDDeref,
    deref,
)
from sqlalchemy_cubrid.partition import (  # noqa: F401
    HashPartition,
    ListPartition,
    PartitionByHash,
    PartitionByList,
    PartitionByRange,
    RangePartition,
)
from sqlalchemy_cubrid.trace import QueryTracer, trace_query  # noqa: F401

__version__ = "1.0.0"

registry.register("cubrid", "sqlalchemy_cubrid.dialect", "CubridDialect")
registry.register(
    "cubrid.pycubrid", "sqlalchemy_cubrid.dialect", "CubridDialect"
)
