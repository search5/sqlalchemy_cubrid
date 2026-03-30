# sqlalchemy_cubrid/dblink.py
# Copyright (C) 2026 by Andrew Ji-ho Lee
#
# This module is part of sqlalchemy-cubrid and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""CUBRID DBLINK support (11.2+).

CUBRID 11.2 introduced DBLINK for querying remote CUBRID databases::

    CREATE SERVER remote_srv (
        HOST='192.168.1.10', PORT=33000, DBNAME='demodb',
        USER='dba', PASSWORD=''
    );

    SELECT * FROM DBLINK(remote_srv, 'SELECT id, name FROM t') AS t(id INT, name VARCHAR(50));

Usage::

    from sqlalchemy_cubrid.dblink import CreateServer, DropServer, DbLink

    # Create a remote server reference
    ddl = CreateServer("remote_srv", host="192.168.1.10", port=33000,
                       dbname="demodb", user="dba", password="")
    conn.execute(ddl)

    # Use DBLINK in a FROM clause
    link = DbLink("remote_srv", "SELECT id, name FROM t",
                   columns=[("id", "INT"), ("name", "VARCHAR(50)")])
    # Use link.as_text() to get the FROM clause string
"""

from sqlalchemy.schema import DDLElement
from sqlalchemy.ext.compiler import compiles


class CreateServer(DDLElement):
    """DDL construct for CREATE SERVER (CUBRID 11.2+).

    Generates::

        CREATE SERVER name (
            HOST='host', PORT=port, DBNAME='dbname',
            USER='user', PASSWORD='password'
        )
    """

    def __init__(self, name, host, port=33000, dbname="", user="dba", password=""):
        self.name = name
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password


class DropServer(DDLElement):
    """DDL construct for DROP SERVER (CUBRID 11.2+)."""

    def __init__(self, name, if_exists=True):
        self.name = name
        self.if_exists = if_exists


class DbLink:
    """Helper for constructing DBLINK table expressions.

    Produces a FROM clause fragment::

        DBLINK(server_name, 'query') AS alias(col1 TYPE1, col2 TYPE2)

    :param server: Server name (string).
    :param query: Remote SQL query string.
    :param columns: List of (name, type_str) tuples for the result schema.
    """

    def __init__(self, server, query, columns=None):
        self.server = server
        self.query = query
        self.columns = columns or []

    def as_text(self, alias="t"):
        """Return a raw SQL text fragment for use in text() or select_from().

        :param alias: Table alias for the DBLINK result (default 't').
        """
        col_defs = ", ".join(
            "%s %s" % (name, type_str) for name, type_str in self.columns
        )
        escaped_query = self.query.replace("'", "''")
        if col_defs:
            return "DBLINK(%s, '%s') AS %s(%s)" % (
                self.server, escaped_query, alias, col_defs,
            )
        return "DBLINK(%s, '%s')" % (self.server, escaped_query)


@compiles(CreateServer, "cubrid")
def visit_create_server(element, compiler, **kw):
    return (
        "CREATE SERVER %s ("
        "HOST='%s', PORT=%d, DBNAME='%s', USER='%s', PASSWORD='%s'"
        ")" % (
            compiler.preparer.quote_identifier(element.name),
            element.host.replace("'", "''"),
            element.port,
            element.dbname.replace("'", "''"),
            element.user.replace("'", "''"),
            element.password.replace("'", "''"),
        )
    )


@compiles(DropServer, "cubrid")
def visit_drop_server(element, compiler, **kw):
    text = "DROP SERVER "
    if element.if_exists:
        text += "IF EXISTS "
    text += compiler.preparer.quote_identifier(element.name)
    return text
