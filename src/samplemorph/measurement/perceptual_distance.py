from __future__ import annotations

from fractions import Fraction
from functools import cache
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly

from samplecore.storage.audio_store import NOMINAL_WAV_RATE

CDPAM_RATE_HZ: Final[int] = 22050
RESAMPLING_DENOMINATOR_LIMIT: Final[int] = 200
INT16_SCALE: Final[float] = 32768.0
CDPAM_DEVICE: Final[str] = "cpu"
MISSING_EXTRA_MESSAGE: Final[str] = (
    "cdpam is not installed. Install the 'perceptual' extra (uv sync --extra perceptual) "
    "to measure the learned perceptual distance."
)


class _PerceptualModel(Protocol):
    # cdpam.CDPAM.forward reads two int16-range waveforms shaped (1, samples) and returns a
    # one-element distance; cdpam ships no type stubs, so the shape is the contract stated here.
    def forward(self, wav_in: NDArray[np.float64], wav_out: NDArray[np.float64]) -> NDArray[np.float64]: ...


@cache
def _model() -> _PerceptualModel:
    """Load CDPAM once per process on the CPU, keeping it off the GPU the vocoders hold."""
    try:
        # pylint: disable=import-outside-toplevel
        import cdpam
    except ImportError as error:
        raise ImportError(MISSING_EXTRA_MESSAGE) from error
    model: _PerceptualModel = cdpam.CDPAM(dev=CDPAM_DEVICE)
    return model


def to_cdpam_block(
    waveform: NDArray[np.float64],
    length: int,
    *,
    source_rate_hz: int,
) -> NDArray[np.float64]:
    """Shape a mono waveform the way CDPAM reads it: 22.05 kHz, int16 range, one row.

    CDPAM analyzes at a fixed 22.05 kHz and normalizes an int16-range signal internally, so the
    first `length` samples are resampled from `source_rate_hz` and scaled out of the unit range
    before the model sees them. Passing the rate the samples are clocked at — the store's nominal
    rate, or a probe's heard rate — is what lets CDPAM judge the sound a listener hears at that
    rate. The single leading axis is the batch of one CDPAM's forward pass expects.
    """
    ratio = Fraction(CDPAM_RATE_HZ, source_rate_hz).limit_denominator(RESAMPLING_DENOMINATOR_LIMIT)
    resampled: NDArray[np.float64] = resample_poly(waveform[:length], ratio.numerator, ratio.denominator)
    scaled: NDArray[np.float64] = resampled * INT16_SCALE
    return scaled.reshape(1, -1)


def perceptual_distance(
    reconstruction: NDArray[np.float64],
    reference: NDArray[np.float64],
    *,
    source_rate_hz: int = NOMINAL_WAV_RATE,
) -> float:
    """How far a reconstruction sits from a reference on CDPAM's learned perceptual scale.

    CDPAM is a full-reference distance trained to track what listeners hear, so it reads the
    flanger a reconstruction carries that magnitude and phase-gradient distances pass over. The
    reference is the ground-truth waveform the reconstruction stands in for, and the shorter length
    is the one compared. Both waveforms are read as `source_rate_hz`: the store's nominal rate by
    default, since that is the rate every stored object and every vocoder output carries; pass a
    probe's heard rate to score the sound as a listener hears that sample.
    """
    model = _model()
    length = min(reconstruction.shape[0], reference.shape[0])
    distance = model.forward(
        to_cdpam_block(reference, length, source_rate_hz=source_rate_hz),
        to_cdpam_block(reconstruction, length, source_rate_hz=source_rate_hz),
    )
    return float(np.asarray(distance).reshape(-1)[0])
