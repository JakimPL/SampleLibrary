from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from samplemorph.pipeline import RouteChoice

DEFAULT_INFERENCE_DEVICE: Final[str] = "cpu"
PROCESSOR_DEVICE: Final[str] = "cpu"
MEBIBYTE: Final[int] = 2**20
RENDER_CACHE_BYTES: Final[int] = 128 * MEBIBYTE
LATENT_CACHE_BYTES: Final[int] = 32 * MEBIBYTE
MAXIMUM_RATE_RATIO: Final[float] = 16.0
MAXIMUM_RENDER_FRAMES: Final[int] = 2**20
CACHE_CONTROL: Final[str] = "private, no-cache"
WAV_MEDIA_TYPE: Final[str] = "audio/wav"


@dataclass(frozen=True)
class RenderLimits:
    """How far one process goes for a request, and how much it keeps of what it rendered.

    A pair is heard at the higher of its two rates, so a slow sample paired with a fast one grows
    by the ratio between them; four octaves of it are served, beyond that the request is refused.
    The frame bound holds one render's memory to what a listener's click should cost: at the bound,
    about 24 seconds at 44.1 kHz, a render through the restored route peaks near 9 GB on the
    processor, and a longer one grows in proportion.
    """

    maximum_rate_ratio: float = MAXIMUM_RATE_RATIO
    maximum_frames: int = MAXIMUM_RENDER_FRAMES
    render_cache_bytes: int = RENDER_CACHE_BYTES
    latent_cache_bytes: int = LATENT_CACHE_BYTES


@dataclass(frozen=True)
class ServiceSettings:
    """What one inference process serves: the library it reads objects from, the sample directories it
    reads files from, the route it renders through, and its limits.

    A request names the file a sample found in a sample directory is read from, and the process reads
    only files inside the directories named here, which are the ones its configuration lists.
    """

    library_root: Path
    sample_directories: tuple[Path, ...]
    choice: RouteChoice
    limits: RenderLimits = field(default_factory=RenderLimits)
