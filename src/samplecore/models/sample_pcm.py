from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplecore.models.sample import Sample


@dataclass(frozen=True)
class SamplePCM:
    """A Sample's identity paired with its decoded waveform, for code that needs the audio itself.

    Shape is always ``(frames, channels)``, float64 in ``[-1, 1]``, so a C-contiguous array's
    ``.tobytes()`` is already frame-major interleaved -- the byte order both a WAV data chunk and
    the sample hash function expect.
    """

    sample: Sample
    pcm: NDArray[np.float64]

    def __post_init__(self) -> None:
        if self.pcm.ndim != 2:
            raise ValueError(
                f"sample {self.sample.hash} pcm must be 2-D (frames, channels), got shape {self.pcm.shape}"
            )

        expected_shape = (self.sample.frames, self.sample.channels.value)
        if self.pcm.shape != expected_shape:
            raise ValueError(
                f"sample {self.sample.hash} pcm shape {self.pcm.shape} does not match declared {expected_shape}"
            )
