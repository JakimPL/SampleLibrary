from __future__ import annotations

from typing import Final

from pydantic import ConfigDict

FROZEN: Final = ConfigDict(frozen=True, extra="forbid")
