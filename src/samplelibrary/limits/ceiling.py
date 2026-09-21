from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

UNCAPPED: Final[str] = "none"
_UNIT_FACTORS: Final[dict[str, int]] = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
_CEILING_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(?P<amount>\d+)(?P<unit>[KMGT])?$", re.IGNORECASE)


class MalformedCeiling(ValueError):
    """Raised when a memory ceiling is written in a way this project does not read."""


@dataclass(frozen=True)
class MemoryCeiling:
    """How much memory one process, and everything it starts, may hold between them.

    ``none`` runs a process with whatever the machine has, which is what a system with no way to
    enforce a ceiling is left with.
    """

    byte_count: int | None

    @classmethod
    def parse(cls, value: str) -> MemoryCeiling:
        """A ceiling written as a whole number of bytes, or with a K, M, G or T suffix, or as ``none``.

        Raises:
            MalformedCeiling: the value is written some other way, or names no memory at all.
        """
        if value.strip().lower() == UNCAPPED:
            return cls(byte_count=None)
        match = _CEILING_PATTERN.match(value.strip())
        if match is None:
            raise MalformedCeiling(f"a memory ceiling reads as 16G, 512M, 1073741824 or {UNCAPPED!r}, not {value!r}")
        amount = int(match.group("amount"))
        byte_count = amount * _UNIT_FACTORS.get((match.group("unit") or "").upper(), 1)
        if byte_count < 1:
            raise MalformedCeiling(f"a memory ceiling holds at least one byte, or reads {UNCAPPED!r}, not {value!r}")
        return cls(byte_count=byte_count)

    @property
    def enforced(self) -> bool:
        """Whether this ceiling bounds anything."""
        return self.byte_count is not None

    def __str__(self) -> str:
        if self.byte_count is None:
            return UNCAPPED
        for suffix, factor in reversed(_UNIT_FACTORS.items()):
            if self.byte_count % factor == 0 and self.byte_count >= factor:
                return f"{self.byte_count // factor}{suffix}"
        return str(self.byte_count)
