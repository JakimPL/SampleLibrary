from __future__ import annotations

from typing import Final

# A pipeline hands each step it starts a lock name through the environment, which the step's
# process holds for as long as it lives.
STEP_LOCK_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_STEP_LOCK"
