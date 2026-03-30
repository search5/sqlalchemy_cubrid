# sqlalchemy_cubrid/provision.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID database provisioning for the SQLAlchemy test suite.

CUBRID does not support CREATE/DROP DATABASE via SQL statements;
databases must be created using the cubrid CLI tool. For the test suite,
we use a pre-existing database (testdb) created by the Docker container.
"""

from sqlalchemy.testing.provision import (
    create_db,
    drop_db,
    temp_table_keyword_args,
)


@create_db.for_db("cubrid")
def _cubrid_create_db(cfg, eng, ident):
    """No-op: CUBRID databases must be created via the cubrid CLI tool."""
    pass


@drop_db.for_db("cubrid")
def _cubrid_drop_db(cfg, eng, ident):
    """No-op: CUBRID databases must be dropped via the cubrid CLI tool."""
    pass


@temp_table_keyword_args.for_db("cubrid")
def _cubrid_temp_table_keyword_args(cfg, eng):
    """Return empty dict: CUBRID does not support temporary tables."""
    return {}
