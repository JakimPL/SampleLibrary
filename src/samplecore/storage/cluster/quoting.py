from __future__ import annotations

from typing import Final

from psycopg import sql

# Postgres holds an identifier in a `name`, which is 63 bytes wide. A longer one is cut to that on
# the way in, and every later comparison cuts its own operand the same way, so an over-long name
# stays consistent with itself and needs no guard here.
MAXIMUM_IDENTIFIER_BYTES: Final[int] = 63

_NUL: Final[str] = "\x00"


class UnsafeValueError(ValueError):
    """Raised when a value would reach Postgres as something other than the value it stands for."""


def identifier(value: str) -> sql.Identifier:
    """One role or database name, quoted for the statement it is about to travel in.

    Quoting doubles an embedded quote mark, which covers every character a name may carry save one:
    the driver ends a name at a NUL byte, so a name holding one arrives naming something shorter
    than what was asked for. Rejecting it here is what keeps the name that reaches the server the
    name the caller meant. An empty name is rejected for the same reason -- Postgres answers one
    with a bare syntax error, which says nothing about where it came from.

    Raises:
        UnsafeValueError: the name is empty, or holds a NUL byte.
    """
    if not value:
        raise UnsafeValueError("A Postgres identifier holds at least one character.")

    if _NUL in value:
        readable = value.replace(_NUL, "\\0")
        raise UnsafeValueError(f"The identifier {readable!r} holds a NUL byte, which would cut it short.")

    return sql.Identifier(value)


def literal(value: str) -> sql.Literal:
    """One string value, quoted for the statement it is about to travel in.

    The driver escapes the quote marks and backslashes a value carries, and emits it in Postgres's
    own ``E'...'`` form, so a value stands for itself whatever the server's ``standard_conforming_strings``
    says. A NUL byte is the one thing that form has no spelling for.

    Raises:
        UnsafeValueError: the value holds a NUL byte, which Postgres keeps in no text field.
    """
    if _NUL in value:
        raise UnsafeValueError("A Postgres text value holds no NUL byte.")

    return sql.Literal(value)
