from __future__ import annotations

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger, Integer, SmallInteger, TypeDecorator

# Every type below only overrides its compiled DDL name via @compiles, not Python<->DB value
# conversion, so TypeDecorator's process_bind_param/process_literal_param/process_result_value/
# python_type stay at their base-class defaults by design -- pylint's abstract-method and
# too-many-ancestors checks both flag this as if it were an oversight, on a SQLAlchemy base class
# whose own inheritance depth these tiny subclasses have no control over.
# pylint: disable=abstract-method,too-many-ancestors


class TinyInt(TypeDecorator[int]):
    """A signed byte-range integer, for fields like XM tuning that can go negative."""

    impl = SmallInteger
    cache_ok = True


class UTinyInt(TypeDecorator[int]):
    """An unsigned byte-range integer, for small always-non-negative fields (bit depth, volume).

    Postgres has no byte-width integer type, signed or unsigned, so this compiles to its narrowest
    integer column (``SMALLINT``) with non-negativity enforced by a ``CheckConstraint`` on each
    column that uses it, not by the column type itself.
    """

    impl = SmallInteger
    cache_ok = True


class USmallInt(TypeDecorator[int]):
    """An unsigned 16-bit integer, for counts that comfortably exceed a byte.

    Compiles to Postgres's ``INTEGER`` -- its narrowest signed type wide enough to hold the full
    unsigned 16-bit range -- with non-negativity enforced by a ``CheckConstraint``, the same as
    ``UTinyInt``.
    """

    impl = Integer
    cache_ok = True


class UInteger(TypeDecorator[int]):
    """An unsigned 32-bit integer, for frame counts and sample rates.

    Compiles to Postgres's ``BIGINT`` -- its narrowest signed type wide enough to hold the full
    unsigned 32-bit range -- with non-negativity enforced by a ``CheckConstraint``.
    """

    impl = BigInteger
    cache_ok = True


class UBigInt(TypeDecorator[int]):
    """An unsigned 64-bit integer, for file sizes in bytes.

    Postgres has no wider signed integer to promote to, so this shares ``BIGINT`` with
    ``UInteger`` -- a value past the signed 64-bit range is rejected by the column type itself,
    same as it always would have been; non-negativity still needs its own ``CheckConstraint``.
    """

    impl = BigInteger
    cache_ok = True


@compiles(TinyInt, "postgresql")
@compiles(UTinyInt, "postgresql")
def _compile_smallint(_type: TinyInt | UTinyInt, _compiler: object, **_kwargs: object) -> str:
    """Postgres has no byte-width integer, signed or unsigned; ``SMALLINT`` is its narrowest type."""
    return "SMALLINT"


@compiles(USmallInt, "postgresql")
def _compile_integer(_type: USmallInt, _compiler: object, **_kwargs: object) -> str:
    return "INTEGER"


@compiles(UInteger, "postgresql")
@compiles(UBigInt, "postgresql")
def _compile_bigint(_type: UInteger | UBigInt, _compiler: object, **_kwargs: object) -> str:
    return "BIGINT"
