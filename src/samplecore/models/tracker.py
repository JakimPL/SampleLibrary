from __future__ import annotations

from enum import StrEnum, unique


@unique
class TrackerFormat(StrEnum):
    """Which tracker format a module or a sample occurrence belongs to."""

    XM = "xm"
    IT = "it"
    MOD = "mod"
    S3M = "s3m"
