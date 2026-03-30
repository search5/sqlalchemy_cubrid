# sqlalchemy_cubrid/partition.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID PARTITION support.

CUBRID supports RANGE, HASH, and LIST partitioning::

    CREATE TABLE orders (
        id INT, order_date DATE
    ) PARTITION BY RANGE (order_date) (
        PARTITION p2024 VALUES LESS THAN ('2025-01-01'),
        PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
        PARTITION pmax VALUES LESS THAN MAXVALUE
    );

Usage::

    from sqlalchemy_cubrid.partition import (
        PartitionByRange, PartitionByHash, PartitionByList,
        RangePartition, HashPartition, ListPartition,
    )

    ddl = PartitionByRange(
        "orders", "order_date",
        partitions=[
            RangePartition("p2024", "'2025-01-01'"),
            RangePartition("p2025", "'2026-01-01'"),
            RangePartition("pmax", "MAXVALUE"),
        ],
    )
    conn.execute(ddl)
"""

from sqlalchemy.schema import DDLElement
from sqlalchemy.ext.compiler import compiles


class RangePartition:
    """A single RANGE partition definition.

    :param name: Partition name.
    :param less_than: Upper bound expression (literal SQL string or MAXVALUE).
    """

    def __init__(self, name, less_than):
        self.name = name
        self.less_than = less_than


class HashPartition:
    """A single HASH partition definition.

    :param name: Partition name.
    """

    def __init__(self, name):
        self.name = name


class ListPartition:
    """A single LIST partition definition.

    :param name: Partition name.
    :param values: List of literal SQL value strings.
    """

    def __init__(self, name, values):
        self.name = name
        self.values = values


class PartitionByRange(DDLElement):
    """DDL construct for RANGE partitioning an existing table.

    Generates::

        ALTER TABLE name PARTITION BY RANGE (column) (
            PARTITION p1 VALUES LESS THAN (expr), ...
        )
    """

    def __init__(self, table_name, column, partitions):
        self.table_name = table_name
        self.column = column
        self.partitions = partitions


class PartitionByHash(DDLElement):
    """DDL construct for HASH partitioning an existing table.

    Generates::

        ALTER TABLE name PARTITION BY HASH (column)
        PARTITIONS count
    """

    def __init__(self, table_name, column, count):
        self.table_name = table_name
        self.column = column
        self.count = count


class PartitionByList(DDLElement):
    """DDL construct for LIST partitioning an existing table.

    Generates::

        ALTER TABLE name PARTITION BY LIST (column) (
            PARTITION p1 VALUES IN (v1, v2), ...
        )
    """

    def __init__(self, table_name, column, partitions):
        self.table_name = table_name
        self.column = column
        self.partitions = partitions


@compiles(PartitionByRange, "cubrid")
def visit_partition_by_range(element, compiler, **kw):
    parts = []
    for p in element.partitions:
        parts.append(
            "PARTITION %s VALUES LESS THAN (%s)" % (
                compiler.preparer.quote_identifier(p.name),
                p.less_than,
            )
        )
    return "ALTER TABLE %s PARTITION BY RANGE (%s) (%s)" % (
        compiler.preparer.quote_identifier(element.table_name),
        compiler.preparer.quote_identifier(element.column),
        ", ".join(parts),
    )


@compiles(PartitionByHash, "cubrid")
def visit_partition_by_hash(element, compiler, **kw):
    return "ALTER TABLE %s PARTITION BY HASH (%s) PARTITIONS %d" % (
        compiler.preparer.quote_identifier(element.table_name),
        compiler.preparer.quote_identifier(element.column),
        element.count,
    )


@compiles(PartitionByList, "cubrid")
def visit_partition_by_list(element, compiler, **kw):
    parts = []
    for p in element.partitions:
        vals = ", ".join(str(v) for v in p.values)
        parts.append(
            "PARTITION %s VALUES IN (%s)" % (
                compiler.preparer.quote_identifier(p.name),
                vals,
            )
        )
    return "ALTER TABLE %s PARTITION BY LIST (%s) (%s)" % (
        compiler.preparer.quote_identifier(element.table_name),
        compiler.preparer.quote_identifier(element.column),
        ", ".join(parts),
    )
