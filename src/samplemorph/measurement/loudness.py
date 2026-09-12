from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.rendering import HEADROOM, SILENT_LEVEL

GATING_BLOCK_SECONDS: Final[float] = 0.4
MISSING_EXTRA_MESSAGE: Final[str] = (
    "pyloudnorm is not installed. Install the 'morph' extra (uv sync --extra morph) to measure loudness."
)


class _Meter(Protocol):
    # pyloudnorm.Meter.integrated_loudness reads a waveform shaped (samples,) or (samples, channels)
    # and returns integrated loudness in LUFS; pyloudnorm ships no type stubs, so the shape is the
    # contract stated here.
    def integrated_loudness(self, data: NDArray[np.float64]) -> float: ...


@cache
def _meter(sample_rate_hz: int) -> _Meter:
    """Build the BS.1770 meter for one sample rate once per process."""
    try:
        # pylint: disable=import-outside-toplevel
        import pyloudnorm
    except ImportError as error:
        raise ImportError(MISSING_EXTRA_MESSAGE) from error

    meter: _Meter = pyloudnorm.Meter(sample_rate_hz)
    return meter


@dataclass(frozen=True)
class LoudnessDelta:
    """Integrated loudness of a reconstruction and of its reference, and how the two were read.

    `delta_lu` is the signed gain the reconstruction carries over the reference, and zero is the
    target: a reconstruction that returns quieter reads negative, which is the effect every
    shape-based reading normalizes away. Both waveforms share one length and one path, so the delta
    compares like with like; `block_count` is how many whole gating blocks that length spans, and
    `gated` says whether the path was the standard's gated reading over those blocks or a
    whole-clip reading of a sample shorter than one.
    """

    reference_lufs: float
    reconstruction_lufs: float
    block_count: int

    @property
    def delta_lu(self) -> float:
        return self.reconstruction_lufs - self.reference_lufs

    @property
    def gated(self) -> bool:
        return self.block_count > 0


def loudness_delta(
    reconstruction: NDArray[np.float64],
    reference: NDArray[np.float64],
    *,
    source_rate_hz: int = NOMINAL_WAV_RATE,
) -> LoudnessDelta:
    """Read how loud a reconstruction is against its reference, as ITU-R BS.1770 integrated loudness.

    The K-weighting inside the standard is a high-pass near 38 Hz and a presence shelf applied
    before the energy is summed, so the reading follows what a listener hears rather than what the
    lowest frequencies contribute. Both waveforms are read at `source_rate_hz`, the rate the samples
    are heard at, over the shorter of their lengths.

    A clip shorter than one gating block is tiled to fill one, which preserves its mean square, so
    the K-weighted reading is the clip's own; both waveforms are tiled alike, so the seams cancel in
    the delta. Such a pair reports no gating blocks.

    Raises:
        ValueError: either waveform is empty, leaving nothing to read.
    """
    length = min(reconstruction.shape[0], reference.shape[0])
    if length == 0:
        raise ValueError("an empty waveform carries no loudness to read")

    return LoudnessDelta(
        reference_lufs=integrated_loudness(reference[:length], source_rate_hz=source_rate_hz),
        reconstruction_lufs=integrated_loudness(reconstruction[:length], source_rate_hz=source_rate_hz),
        block_count=length // _block_length(source_rate_hz),
    )


def integrated_loudness(waveform: NDArray[np.float64], *, source_rate_hz: int = NOMINAL_WAV_RATE) -> float:
    """One waveform's ITU-R BS.1770 integrated loudness in LUFS, read at the rate it is heard at.

    A clip shorter than one gating block is tiled to fill one, which preserves its mean square, so
    the reading is the clip's own. Silence reads as negative infinity, the standard's own answer.

    Raises:
        ValueError: the waveform is empty, leaving nothing to read.
    """
    length = waveform.shape[0]
    if length == 0:
        raise ValueError("an empty waveform carries no loudness to read")

    block_length = _block_length(source_rate_hz)
    repeats = 1 if length >= block_length else -(-block_length // length)
    return _meter(source_rate_hz).integrated_loudness(np.tile(waveform, repeats))


def match_loudness(
    waveforms: Sequence[NDArray[np.float64]],
    *,
    reference: NDArray[np.float64],
    source_rate_hz: int = NOMINAL_WAV_RATE,
) -> tuple[NDArray[np.float64], ...]:
    """Scale every waveform to the reference's loudness, then all of them together under one headroom.

    Matching the K-weighted loudness first puts a reconstruction beside its original at the level a
    listener would set for it, so what is heard between the two is fine structure and crest rather
    than gain; one shared gain afterwards keeps the loudest peak of the set at the rendering
    headroom while the matched relation stands. The reference belongs in `waveforms` when it is to
    be written beside the rest. A silent waveform keeps its level, having no loudness to match.
    """
    target = integrated_loudness(reference, source_rate_hz=source_rate_hz)
    matched = []
    for waveform in waveforms:
        loudness = integrated_loudness(waveform, source_rate_hz=source_rate_hz)
        gain = 10.0 ** ((target - loudness) / 20.0) if np.isfinite(loudness) and np.isfinite(target) else 1.0
        matched.append(waveform * gain)
    peak = max(float(np.abs(waveform).max()) for waveform in matched)
    shared_gain = HEADROOM / peak if peak > SILENT_LEVEL else 1.0
    return tuple(waveform * shared_gain for waveform in matched)


def _block_length(source_rate_hz: int) -> int:
    return int(GATING_BLOCK_SECONDS * source_rate_hz)
