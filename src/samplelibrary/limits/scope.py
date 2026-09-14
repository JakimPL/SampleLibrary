from __future__ import annotations

from typing import Protocol

from samplelibrary.limits.ceiling import MemoryCeiling


class MemoryScopeUnavailable(ValueError):
    """Raised when a memory ceiling is asked for on a system with no way to hold a process to one."""


class MemoryScope(Protocol):
    """Holds this process, and everything it starts, to a memory ceiling under a name others can find it by.

    ``enter`` is called before a command loads anything of its own, so every allocation that matters
    falls inside the ceiling. On a system that reaches the ceiling by starting the process again
    under something that enforces it, ``enter`` never returns.
    """

    def enter(self, name: str, ceiling: MemoryCeiling, argv: list[str]) -> None:
        """Put this process under ``ceiling``, or start it again as a process that is.

        Raises:
            MemoryScopeUnavailable: the ceiling cannot be enforced here.
        """

    def is_running(self, name: str) -> bool:
        """Whether a process of this name is still held under a ceiling, its own having started it."""

    def peak_bytes(self) -> int | None:
        """The most memory this process and its children held at once, where the system reports it."""

    def reached_the_ceiling(self) -> bool:
        """Whether anything under the ceiling was stopped for outgrowing it."""

    def terminate(self, name: str) -> None:
        """Stop every process held under this name, for a caller cleaning up after an orphan."""
