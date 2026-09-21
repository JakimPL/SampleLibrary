from __future__ import annotations

import shutil
import sys

from samplelibrary.limits.bare import BareScope
from samplelibrary.limits.scope import MemoryScope
from samplelibrary.limits.systemd import SYSTEMD_RUN, SystemdScope


def memory_scope() -> MemoryScope:
    """What this system holds a process to a memory ceiling with, read as the process runs.

    Linux holds a process in a systemd scope of the user's own session, Windows in a job object, and
    a system offering neither runs uncapped and refuses a ceiling that was asked for.
    """
    if sys.platform == "win32":
        # pylint: disable-next=import-outside-toplevel
        from samplelibrary.limits.job_object import JobObjectScope

        return JobObjectScope()
    if sys.platform.startswith("linux") and shutil.which(SYSTEMD_RUN) is not None:
        return SystemdScope()
    return BareScope()
