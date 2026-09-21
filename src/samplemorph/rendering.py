from __future__ import annotations

import io
from typing import Final

import numpy as np
import soundfile
from numpy.typing import NDArray

RENDERED_SUBTYPE: Final[str] = "PCM_16"
RENDERED_FORMAT: Final[str] = "WAV"
FULL_SCALE_CEILING: Final[float] = 0.98
# Raised whenever the same settings would sound different, so every cache keyed on a render's
# fingerprint lets go of what the previous code rendered.
RENDER_REVISION: Final[int] = 2


def wav_bytes(waveform: NDArray[np.float64], *, rate_hz: float) -> bytes:
    """One waveform as a WAV file in memory, at the stated rate and at the level the route rendered it, lowered only when a peak would clip.

    A process that answers a request with audio hands these bytes over as they are, so the file a
    listener receives is a 16-bit WAV at the stated rate.
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
