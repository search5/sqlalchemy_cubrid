# sqlalchemy_cubrid/__init__.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy.dialects import registry

from sqlalchemy_cubrid.functions import incr, decr  # noqa: F401
from sqlalchemy_cubrid.hierarchical import (  # noqa: F401
    HierarchicalSelect,
    prior,
    level_col,
    sys_connect_by_path,
    connect_by_root,
    connect_by_isleaf,
    connect_by_iscycle,
)
from sqlalchemy_cubrid.merge import Merge  # noqa: F401

__version__ = "0.1.0.dev1"

registry.register("cubrid", "sqlalchemy_cubrid.dialect", "CubridDialect")
registry.register("cubrid.pycubrid", "sqlalchemy_cubrid.dialect", "CubridDialect")
