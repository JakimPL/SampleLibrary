from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

import numpy as np
import soundfile
from numpy.typing import NDArray

RENDERED_SUBTYPE: Final[str] = "PCM_16"
SILENT_LEVEL: Final[float] = 1e-10
HEADROOM: Final[float] = 0.98


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
    into the header here.
    """
    file.path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(file.path, _with_headroom(waveform), int(round(file.rate_hz)), subtype=RENDERED_SUBTYPE)
    return file


def _with_headroom(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """Scale a waveform to sit just below full scale, so a written file carries no clipping."""
    peak = float(np.abs(waveform).max())
    return waveform * (HEADROOM / peak) if peak > SILENT_LEVEL else waveform


def rate_between(first_rate_hz: float, second_rate_hz: float, weight: float) -> float:
    """The playback rate a morph between two samples is heard at.

    Rates are read as pitches, so the path between them runs through their logarithms: halfway
    between 8,363 Hz and 16,726 Hz is the octave's midpoint rather than its arithmetic mean. This
    is the frame's own speed, and it multiplies with the pitch the conditioners place the content
    at, so interpolating both in the log domain interpolates what is heard.
    """
    return float(2.0 ** ((1.0 - weight) * np.log2(first_rate_hz) + weight * np.log2(second_rate_hz)))
