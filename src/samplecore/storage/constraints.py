from __future__ import annotations

from sqlalchemy import ColumnElement, and_, column


def non_negative(column_name: str) -> ColumnElement[bool]:
    """A CHECK expression requiring a column to never go negative.

    DuckDB's own unsigned integer types (``UTINYINT``, ``USMALLINT``, ``UINTEGER``, ``UBIGINT``)
    enforced this at the type level for free; Postgres has no unsigned integer type at all, so every
    column that relied on that now needs it spelled out here instead.
    """
    return column(column_name) >= 0


def all_null_together(first_column_name: str, *other_column_names: str) -> ColumnElement[bool]:
    """A CHECK expression requiring a group of columns to be either all NULL or all filled in.

    Every other column's nullability is compared against the first's; boolean equality is
    transitive, so this enforces the same all-or-none constraint as comparing each consecutive
    pair, without needing that specific chain to read the intent off the expression.
    """
    first_is_null = column(first_column_name).is_(None)
    return and_(*(first_is_null == column(name).is_(None) for name in other_column_names))
