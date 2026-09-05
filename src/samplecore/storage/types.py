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
    """DuckDB's signed 8-bit ``TINYINT``, for fields like XM tuning that can go negative."""

    impl = SmallInteger
    cache_ok = True


class UTinyInt(TypeDecorator[int]):
    """DuckDB's unsigned 8-bit ``UTINYINT``, for small always-non-negative fields (bit depth, volume)."""

    impl = SmallInteger
    cache_ok = True


class USmallInt(TypeDecorator[int]):
    """DuckDB's unsigned 16-bit ``USMALLINT``, for counts that comfortably exceed a byte."""

    impl = Integer
    cache_ok = True


class UInteger(TypeDecorator[int]):
    """DuckDB's unsigned 32-bit ``UINTEGER``, for frame counts and sample rates."""

    impl = BigInteger
    cache_ok = True


class UBigInt(TypeDecorator[int]):
    """DuckDB's unsigned 64-bit ``UBIGINT``, for file sizes in bytes."""

    impl = BigInteger
    cache_ok = True


@compiles(TinyInt, "duckdb")
def _compile_tinyint(_type: TinyInt, _compiler: object, **_kwargs: object) -> str:
    return "TINYINT"


@compiles(UTinyInt, "duckdb")
def _compile_utinyint(_type: UTinyInt, _compiler: object, **_kwargs: object) -> str:
    return "UTINYINT"


@compiles(USmallInt, "duckdb")
def _compile_usmallint(_type: USmallInt, _compiler: object, **_kwargs: object) -> str:
    return "USMALLINT"


@compiles(UInteger, "duckdb")
def _compile_uinteger(_type: UInteger, _compiler: object, **_kwargs: object) -> str:
    return "UINTEGER"


@compiles(UBigInt, "duckdb")
def _compile_ubigint(_type: UBigInt, _compiler: object, **_kwargs: object) -> str:
    return "UBIGINT"
