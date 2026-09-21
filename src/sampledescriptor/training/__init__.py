from __future__ import annotations

from typing import Final

# Every worker process a trainer or a cache builder starts is a fresh interpreter, which is what
# keeps a worker's memory its own rather than a copy of a process holding the GPU.
WORKER_START_METHOD: Final[str] = "spawn"
