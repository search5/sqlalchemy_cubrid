# sqlalchemy_cubrid/requirements.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID-specific requirements for the SQLAlchemy dialect test suite."""

from sqlalchemy.testing import exclusions
from sqlalchemy.testing.requirements import SuiteRequirements


class Requirements(SuiteRequirements):
    """CUBRID capability declarations for the SQLAlchemy test suite.

    Each property returns ``exclusions.open()`` (supported) or
    ``exclusions.closed()`` (not supported) to inform the test runner
    which features CUBRID provides.
    """

    # -- Features CUBRID supports --

    @property
    def foreign_keys(self):
        return exclusions.open()

    @property
    def self_referential_foreign_keys(self):
        return exclusions.open()

    @property
    def on_update_cascade(self):
        return exclusions.open()

    @property
    def subqueries(self):
        return exclusions.open()

    @property
    def offset(self):
        return exclusions.open()

    @property
    def window_functions(self):
        return exclusions.open()

    @property
    def window_functions_rows_between(self):
        """CUBRID does not support ROWS BETWEEN with bind parameters."""
        return exclusions.closed()

    @property
    def ctes(self):
        return exclusions.open()

    @property
    def views(self):
        return exclusions.open()

    @property
    def sequences(self):
        """CUBRID uses SERIAL (mapped to SQLAlchemy Sequence)."""
        return exclusions.open()

    @property
    def has_sequence(self):
        return exclusions.open()

    @property
    def sequences_as_server_defaults(self):
        return exclusions.closed()

    @property
    def implements_get_lastrowid(self):
        return exclusions.open()

    @property
    def table_ddl_if_exists(self):
        return exclusions.open()

    @property
    def json_type(self):
        """CUBRID supports JSON since 10.2."""
        return exclusions.open()

    # -- Features CUBRID does NOT support --

    @property
    def returning(self):
        return exclusions.closed()

    @property
    def insert_returning(self):
        return exclusions.closed()

    @property
    def update_returning(self):
        return exclusions.closed()

    @property
    def delete_returning(self):
        return exclusions.closed()

    @property
    def schemas(self):
        """CUBRID 11.2+ has user schemas but not standard SQL schemas."""
        return exclusions.closed()

    @property
    def temp_table(self):
        return exclusions.closed()

    @property
    def temporary_tables(self):
        return exclusions.closed()

    @property
    def temporary_views(self):
        return exclusions.closed()

    @property
    def temp_table_reflection(self):
        return exclusions.closed()

    @property
    def has_temp_table(self):
        return exclusions.closed()

    @property
    def uuid_data_type(self):
        return exclusions.closed()

    @property
    def array_type(self):
        return exclusions.closed()

    @property
    def datetime_microseconds(self):
        """CUBRID DATETIME has millisecond (3-digit) precision, not microsecond."""
        return exclusions.closed()

    @property
    def timestamp_microseconds(self):
        return exclusions.closed()

    @property
    def time_microseconds(self):
        return exclusions.closed()

    @property
    def duplicate_key_raises_integrity_error(self):
        return exclusions.open()

    @property
    def nullable_booleans(self):
        """CUBRID maps BOOLEAN to SMALLINT, which is nullable."""
        return exclusions.open()

    @property
    def empty_strings_varchar(self):
        """CUBRID preserves empty strings in VARCHAR columns."""
        return exclusions.open()

    @property
    def savepoints(self):
        """CUBRID supports SAVEPOINT but not RELEASE SAVEPOINT."""
        return exclusions.open()

    @property
    def savepoints_w_release(self):
        return exclusions.closed()

    @property
    def deferrable_fks(self):
        return exclusions.closed()

    @property
    def comment_reflection(self):
        return exclusions.open()

    @property
    def cross_schema_fk_reflection(self):
        return exclusions.closed()

    @property
    def index_ddl_if_exists(self):
        """CUBRID does not support IF [NOT] EXISTS for CREATE/DROP INDEX."""
        return exclusions.closed()

    @property
    def reflects_pk_names(self):
        return exclusions.open()

    @property
    def unique_constraint_reflection(self):
        return exclusions.open()

    @property
    def unique_constraints_reflect_as_index(self):
        """CUBRID implements unique constraints as unique indexes."""
        return exclusions.open()

    @property
    def unique_index_reflect_as_unique_constraints(self):
        """CUBRID reflects unique indexes as unique constraints (no distinction)."""
        return exclusions.open()

    @property
    def server_side_cursors(self):
        return exclusions.closed()

    @property
    def independent_connections(self):
        return exclusions.open()

    @property
    def autocommit(self):
        """CUBRID supports autocommit via pycubrid connection property."""
        return exclusions.open()

    @property
    def autocommit_isolation(self):
        return exclusions.open()

    @property
    def isolation_level(self):
        """CUBRID supports READ COMMITTED, REPEATABLE READ, SERIALIZABLE."""
        return exclusions.open()

    @property
    def sane_rowcount(self):
        return exclusions.open()

    @property
    def sane_multi_rowcount(self):
        return exclusions.open()

    @property
    def empty_inserts(self):
        """CUBRID may not support INSERT with no values."""
        return exclusions.closed()

    @property
    def insert_from_select(self):
        return exclusions.open()

    @property
    def tuple_in(self):
        """CUBRID supports row value constructor IN since 11.0."""
        return exclusions.open()

    @property
    def order_by_col_from_union(self):
        return exclusions.open()

    @property
    def mod_operator_as_percent_sign(self):
        return exclusions.closed()

    @property
    def intersect(self):
        """CUBRID uses INTERSECTION keyword (mapped in compiler)."""
        return exclusions.open()

    @property
    def except_(self):
        """CUBRID uses DIFFERENCE keyword (mapped in compiler)."""
        return exclusions.open()

    @property
    def literal_float_coercion(self):
        return exclusions.open()

    @property
    def precision_numerics_enotation_large(self):
        return exclusions.closed()

    @property
    def precision_numerics_enotation_small(self):
        return exclusions.closed()

    @property
    def precision_numerics_many_significant_digits(self):
        return exclusions.closed()

    @property
    def precision_numerics_retains_significant_digits(self):
        return exclusions.closed()

    @property
    def precision_numerics_general(self):
        return exclusions.open()

    @property
    def implicit_decimal_binds(self):
        return exclusions.open()

    @property
    def precision_generic_float_type(self):
        return exclusions.open()

    @property
    def floats_to_four_decimals(self):
        return exclusions.open()

    @property
    def float_is_numeric(self):
        return exclusions.open()

    @property
    def like_escapes(self):
        return exclusions.open()

    @property
    def fetch_rows_post_commit(self):
        return exclusions.open()

    @property
    def supports_is_distinct_from(self):
        """CUBRID does not support IS DISTINCT FROM syntax."""
        return exclusions.closed()

    @property
    def symbol_names_w_double_quote(self):
        """CUBRID uses double quotes for identifiers, not as data."""
        return exclusions.closed()

    @property
    def unnamed_constraints(self):
        return exclusions.open()

    @property
    def implicitly_named_constraints(self):
        return exclusions.open()
