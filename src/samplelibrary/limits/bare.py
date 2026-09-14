from __future__ import annotations

from samplelibrary.limits.ceiling import MemoryCeiling
from samplelibrary.limits.scope import MemoryScopeUnavailable


class BareScope:  # pylint: disable=unused-argument
    """What a system with no way to bound a process's memory offers: an uncapped run.

    A command asked for no ceiling runs as it is; one asking for a ceiling here is refused, so a
    ceiling a configuration names is one the run is actually held to.
    """

    def enter(self, name: str, ceiling: MemoryCeiling, argv: list[str]) -> None:
        """Run on without a ceiling, or refuse the ceiling this system cannot hold a process to.

        Raises:
            MemoryScopeUnavailable: a ceiling was asked for.
        """
        if ceiling.byte_count is None:
            return
        raise MemoryScopeUnavailable(
            "this system offers no way to hold a process to a memory ceiling; run with a ceiling of none"
        )

    def is_running(self, name: str) -> bool:
        return False

    def terminate(self, name: str) -> None:
        """Leave a process this system never held under a name of its own."""

    def peak_bytes(self) -> int | None:
        return None

    def reached_the_ceiling(self) -> bool:
        return False
