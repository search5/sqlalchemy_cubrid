# sqlalchemy_cubrid/trace.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID query trace utility.

Uses ``SET TRACE ON`` / ``SHOW TRACE`` to capture execution plans
and performance statistics for SQL statements.

Usage::

    from sqlalchemy_cubrid.trace import trace_query

    with engine.connect() as conn:
        result, trace_output = trace_query(
            conn, "SELECT * FROM my_table WHERE id = :id", {"id": 1}
        )
        print(trace_output)

Or with the context manager::

    from sqlalchemy_cubrid.trace import QueryTracer

    with engine.connect() as conn:
        tracer = QueryTracer(conn, output="JSON")
        tracer.start()
        conn.execute(text("SELECT ..."))
        print(tracer.stop())
"""

from sqlalchemy import text


def trace_query(connection, sql, params=None, output="TEXT"):
    """Execute a SQL statement with tracing enabled.

    :param connection: A SQLAlchemy connection.
    :param sql: SQL string or :func:`~sqlalchemy.text` construct.
    :param params: Optional bind parameters dict.
    :param output: Trace output format — ``"TEXT"`` (default) or ``"JSON"``.
    :returns: Tuple of ``(result, trace_output)``.
    """
    if output.upper() not in ("TEXT", "JSON"):
        raise ValueError("output must be 'TEXT' or 'JSON'")

    connection.execute(text("SET TRACE ON OUTPUT %s" % output.upper()))

    if isinstance(sql, str):
        sql = text(sql)
    result = connection.execute(sql, params or {})

    trace_result = connection.execute(text("SHOW TRACE"))
    row = trace_result.fetchone()
    trace_output = row[0] if row else ""

    connection.execute(text("SET TRACE OFF"))

    return result, trace_output


class QueryTracer:
    """Context-manager style query tracer.

    Wraps ``SET TRACE ON`` / ``SHOW TRACE`` / ``SET TRACE OFF``
    around an arbitrary block of SQL operations.

    Usage::

        tracer = QueryTracer(conn, output="JSON")
        tracer.start()
        conn.execute(text("SELECT ..."))
        conn.execute(text("UPDATE ..."))
        trace_output = tracer.stop()
    """

    def __init__(self, connection, output="TEXT"):
        if output.upper() not in ("TEXT", "JSON"):
            raise ValueError("output must be 'TEXT' or 'JSON'")
        self._connection = connection
        self._output = output.upper()
        self._active = False

    def start(self):
        """Enable tracing on this connection."""
        self._connection.execute(
            text("SET TRACE ON OUTPUT %s" % self._output)
        )
        self._active = True

    def stop(self):
        """Disable tracing and return the trace output string."""
        if not self._active:
            return ""
        trace_result = self._connection.execute(text("SHOW TRACE"))
        row = trace_result.fetchone()
        trace_output = row[0] if row else ""
        self._connection.execute(text("SET TRACE OFF"))
        self._active = False
        return trace_output

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
