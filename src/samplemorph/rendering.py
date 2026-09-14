from __future__ import annotations

import io
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

import numpy as np
import soundfile
from numpy.typing import NDArray

RENDERED_SUBTYPE: Final[str] = "PCM_16"
RENDERED_FORMAT: Final[str] = "WAV"
SILENT_LEVEL: Final[float] = 1e-10
HEADROOM: Final[float] = 0.98
FULL_SCALE_CEILING: Final[float] = 0.98
# Raised whenever the same model files would sound different, so every cache keyed on a render's
# fingerprint lets go of what the previous code rendered.
RENDER_REVISION: Final[int] = 2


@unique
class RenderKind(StrEnum):
    """What a rendered file is, so a listening set can be read without consulting its filenames."""

    ORIGINAL = "original"
    RECONSTRUCTION = "reconstruction"
    MORPH = "morph"


@dataclass(frozen=True)
class RenderedFile:
    """One file in a listening set: where it goes, what it is, and the rate it is heard at.

    The same description names a file before it is written and records it afterwards, so a summary
    of a listening set says exactly what was asked for.
    """

    path: Path
    kind: RenderKind
    rate_hz: float
    weight: float | None


def write_rendering(file: RenderedFile, waveform: NDArray[np.float64]) -> RenderedFile:
    """Write one waveform at the rate it is heard at, and report what was written.

    The stored library writes every object under one nominal rate, which is a container convention
    rather than a measurement: a sample whose occurrences read it at 8,363 Hz plays five times too
    fast and two octaves too high if it is handed to a player as 44,100 Hz. A listening test is
    only worth running when each file states the rate it is meant to sound at, so that is what goes
    into the header here. The level is kept as rendered, lowered only when a peak would clip.
    """
    file.path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(file.path, limit_to_full_scale(waveform), int(round(file.rate_hz)), subtype=RENDERED_SUBTYPE)
    return file


def wav_bytes(waveform: NDArray[np.float64], *, rate_hz: float) -> bytes:
    """One waveform as a WAV file in memory, at the stated rate and at the level a written file keeps.

    A process that answers a request with audio hands these bytes over as they are, so the file a
    listener receives is the one `write_rendering` would have put on disk.
    """
    buffer = io.BytesIO()
    soundfile.write(
        buffer, limit_to_full_scale(waveform), int(round(rate_hz)), subtype=RENDERED_SUBTYPE, format=RENDERED_FORMAT
    )
    return buffer.getvalue()


def limit_to_full_scale(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """The waveform at its own level, scaled down only as far as keeps its peak below full scale.

    A quiet sound stays quiet, so a morph between a soft pad and a loud hit sounds the way the two
    compare; one static gain on a waveform that would clip adds no distortion of its own.
    """
    peak = float(np.abs(waveform).max()) if waveform.size else 0.0
    return waveform * (FULL_SCALE_CEILING / peak) if peak > FULL_SCALE_CEILING else waveform
