from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

BUILT_FRONTEND: Final[Path] = Path("frontend") / "dist"
PACKAGED_FRONTEND: Final[str] = "samplelibrary/app/frontend"
STANDARD_WHEEL: Final[str] = "standard"


class FrontendBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    """Puts the built frontend inside every regular wheel, where `samplelibrary app` serves it from.

    A checkout without a build, and an editable install, go without it; the application then serves
    a checkout's own `frontend/dist`.
    """

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        built = Path(self.root) / BUILT_FRONTEND
        if version == STANDARD_WHEEL and (built / "index.html").is_file():
            build_data["force_include"][str(built)] = PACKAGED_FRONTEND
