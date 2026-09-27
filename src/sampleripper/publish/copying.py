from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from psycopg import Connection as PsycopgConnection
from psycopg import sql
from sqlalchemy import Connection, Table

from sampleripper.publish.rules import qualified, source_query

CopyParameters = Mapping[str, list[str]]


def empty_tables(target: Connection, tables: tuple[Table, ...]) -> None:
    """Empty every table the publication writes, at once, in the transaction the publication commits."""
    listed = sql.SQL(", ").join(qualified(table) for table in tables)
    _driver(target).execute(sql.SQL("TRUNCATE {tables}").format(tables=listed))


def copy_table(source: Connection, target: Connection, table: Table, *, parameters: CopyParameters) -> int:
    """Stream the rows of ``table`` a publication carries from the library into the target, returning how many.

    Postgres's own ``COPY`` carries the rows both ways in its text form, block by block, so a table
    of tens of millions of rows travels in flat memory and reads the same on servers of another
    version. The source reads the one snapshot the whole publication reads.
    """
    query = source_query(table)
    if query is None:
        return 0
    columns = sql.SQL(", ").join(sql.Identifier(column.name) for column in table.columns)
    with _driver(source).cursor() as reading, _driver(target).cursor() as writing:
        with (
            reading.copy(sql.SQL("COPY ({query}) TO STDOUT").format(query=query), parameters) as rows,
            writing.copy(
                sql.SQL("COPY {table} ({columns}) FROM STDIN").format(table=qualified(table), columns=columns)
            ) as sink,
        ):
            for block in rows:
                sink.write(block)
        return writing.rowcount


def _driver(connection: Connection) -> PsycopgConnection:
    """The psycopg connection beneath ``connection``, inside the transaction SQLAlchemy keeps.

    Beginning the transaction through SQLAlchemy first, as ``bulk_insert`` does, keeps it in charge
    of the transaction the ``COPY`` runs in.
    """
    if connection.get_transaction() is None:
        connection.begin()
    return cast(PsycopgConnection, connection.connection.dbapi_connection)
