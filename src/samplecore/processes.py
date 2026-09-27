from __future__ import annotations

import subprocess
import sys
from typing import Final

# Windows gives a console program its own console window when the process starting it has none,
# as the packaged application started through pythonw has.
if sys.platform == "win32":
    HIDDEN_CONSOLE_FLAGS: Final[int] = subprocess.CREATE_NO_WINDOW
else:
    HIDDEN_CONSOLE_FLAGS: Final[int] = 0
