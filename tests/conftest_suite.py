# tests/conftest_suite.py
# SQLAlchemy official test suite plugin bootstrap.
# Usage: pytest tests/test_suite.py -p tests.conftest_suite --dburi '...'

import pytest

from sqlalchemy.dialects import registry

registry.register("cubrid", "sqlalchemy_cubrid.dialect", "CubridDialect")
registry.register("cubrid.pycubrid", "sqlalchemy_cubrid.dialect", "CubridDialect")

from sqlalchemy.testing.plugin.pytestplugin import *  # noqa: E402,F401,F403


def pytest_collection_modifyitems(items, config):
    """Skip tests incompatible with CUBRID limitations."""
    skip_bracket = pytest.mark.skip(
        reason="CUBRID does not allow [ or ] in identifiers"
    )
    skip_qmark = pytest.mark.skip(
        reason="? in identifiers conflicts with qmark paramstyle"
    )
    skip_non_ascii = pytest.mark.skip(
        reason="CUBRID default collation does not support non-ASCII in ENUM"
    )
    for item in items:
        if not hasattr(item, "callspec"):
            continue
        for val in item.callspec.params.values():
            if isinstance(val, str):
                if "[" in val or "]" in val:
                    item.add_marker(skip_bracket)
                    break
                if "?" in val:
                    item.add_marker(skip_qmark)
                    break
                # Skip non-ASCII enum values (CUBRID iso88591 limitation)
                if "EnumTest" in item.nodeid:
                    try:
                        val.encode("ascii")
                    except UnicodeEncodeError:
                        item.add_marker(skip_non_ascii)
                        break
