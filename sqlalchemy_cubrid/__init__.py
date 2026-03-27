# sqlalchemy_cubrid/__init__.py
# Copyright (C) 2021-2022 by Yeongseon Choe
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

from sqlalchemy.dialects import registry

__version__ = "0.1.0.dev1"

registry.register("cubrid", "sqlalchemy_cubrid.dialect", "CubridDialect")
registry.register("cubrid.CUBRIDdb", "sqlalchemy_cubrid.dialect", "CubridDialect")
