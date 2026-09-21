from __future__ import annotations

from typing import Final

# A pipeline hands each step it starts a lock name through the environment, which the step's
# process holds for as long as it lives.
STEP_LOCK_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_STEP_LOCK"

# The name of this package as a shell and a re-execution name it: `python -m samplelibrary`.
PACKAGE_NAME: Final[str] = "samplelibrary"

# A process started again under a memory ceiling carries the name of the scope holding it, so the
# process that comes back knows it is already inside one.
MEMORY_SCOPE_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_MEMORY_SCOPE"

# The options this command line reads before a command's name, which a pipeline passes to every step.
CONFIG_OPTION: Final[str] = "--config"
MEMORY_CAP_OPTION: Final[str] = "--memory-cap"
MEMORY_SCOPE_OPTION: Final[str] = "--memory-scope"
