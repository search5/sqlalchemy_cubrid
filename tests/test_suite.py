"""SQLAlchemy official dialect test suite for sqlalchemy-cubrid.

Run with:
    pytest tests/test_suite.py -p tests.conftest_suite --dburi 'cubrid://dba:@localhost:33000/testdb' -v
"""

from sqlalchemy.testing.suite import *  # noqa: F401,F403
