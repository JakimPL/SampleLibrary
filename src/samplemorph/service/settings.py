from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from samplemorph.pipeline import RouteChoice

DEFAULT_INFERENCE_DEVICE: Final[str] = "cpu"
RENDER_CACHE_SIZE: Final[int] = 64
LATENT_CACHE_SIZE: Final[int] = 256
CACHE_CONTROL: Final[str] = "private, max-age=3600"
WAV_MEDIA_TYPE: Final[str] = "audio/wav"


@dataclass(frozen=True)
class ServiceSettings:
    """What one inference process serves: the library it reads objects from, and the route it renders through."""

    library_root: Path
    choice: RouteChoice
