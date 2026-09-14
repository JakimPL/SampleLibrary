from __future__ import annotations

from enum import IntEnum, unique


@unique
class ExitStatus(IntEnum):
    """What a command's exit status tells whoever ran it, a pipeline reading it above all.

    A command that committed its work exits `COMPLETED` even when single items failed along the
    way, since those failures describe the collection and are logged as warnings. `REFUSED` is a
    request the command declines as asked -- a missing directory, a refused prune, an experiment it
    cannot resume -- which a person settles before running it again, apart from `FAILED`, where
    something broke while the work ran. `USAGE` is argparse's own status for a malformed command
    line, `MEMORY_CAP_REACHED` is a process that outgrew the memory ceiling it ran under, and
    `INTERRUPTED` is the status a shell gives a process a person stopped with Ctrl+C.
    """

    COMPLETED = 0
    FAILED = 1
    USAGE = 2
    REFUSED = 3
    MEMORY_CAP_REACHED = 4
    INTERRUPTED = 130
