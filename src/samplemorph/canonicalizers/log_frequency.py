from __future__ import annotations

from functools import cache
from typing import Final

import librosa
import numpy as np
from numpy.typing import NDArray

from samplecore.waveform import triangular_weights
from samplemorph.canonicalizers.common import prepare_mono, restore_spectrogram, to_sound_image
from samplemorph.geometry import DEFAULT_ANCHOR, Anchor, LogFrequencyGeometry, analysis_taper, log_frequency_geometry
from samplemorph.images import AnalysisSpectrogram, SoundImage

# Singular values under this share of the largest are the directions the band averaging resolves
# to nothing; the inverse leaves them at zero, which keeps its entries of the order of the weights.
LEAST_SQUARES_CUTOFF: Final[float] = 1e-6


class LogFrequencyCanonicalizer:
    """Canonicalizes onto an exactly logarithmic reading of the short-time Fourier magnitude.

    Each band averages the linear Fourier bins across its own width, and synthesis reads the bands
    back onto that grid by least squares, so the return path to audio is an ordinary magnitude
    inversion on the grid the analysis started from. That keeps an exact log axis -- where a rate
    change is a whole-band translation -- and a well-behaved inverse at once.
    """

    def __init__(self, geometry: LogFrequencyGeometry) -> None:
        self._geometry = geometry

    @property
    def geometry(self) -> LogFrequencyGeometry:
        return self._geometry

    def canonicalize(self, waveform: NDArray[np.float64]) -> SoundImage:
        mono = prepare_mono(waveform)
        linear = np.abs(
            librosa.stft(
                mono,
                n_fft=self._geometry.fft_length,
                hop_length=self._geometry.hop_length,
                window=analysis_taper(self._geometry),
            )
        )
        return to_sound_image(
            _onto_log_axis(linear, geometry=self._geometry), geometry=self._geometry, frame_count=mono.shape[0]
        )

    def restore(self, image: SoundImage) -> AnalysisSpectrogram:
        return restore_spectrogram(image, geometry=self._geometry)


def _onto_log_axis(linear: NDArray[np.float64], *, geometry: LogFrequencyGeometry) -> NDArray[np.float64]:
    bands: NDArray[np.float64] = band_weights(geometry) @ linear
    return bands


def band_weights(geometry: LogFrequencyGeometry) -> NDArray[np.float64]:
    """Weights averaging the linear Fourier bins each logarithmic band covers.

    A band spans one Fourier bin at around 560 Hz and widens with frequency from there, reaching
    about forty bins at the top of the range. Each band therefore takes a weighted mean over its
    own width, which carries every bin it covers into the picture and holds each frame's content
    where the analysis found it.

    Bands narrower than one bin widen to that much, so every band draws on the grid it is read
    from. Weights fall linearly from each band's center to its edge and sum to one per band.
    """
    band_frequencies = geometry.band_frequencies
    step = 2.0 ** (1.0 / geometry.bins_per_octave)
    bin_spacing = geometry.analysis_rate_hz / geometry.fft_length
    return triangular_weights(
        source_positions=geometry.linear_frequencies,
        target_positions=band_frequencies,
        half_widths=np.maximum(band_frequencies * (step - 1.0 / step) / 2.0, bin_spacing),
    )


@cache
def linear_axis_inverse(geometry: LogFrequencyGeometry) -> NDArray[np.float64]:
    """The least-squares inverse of `band_weights`, computed once per geometry.

    Every band is a weighted mean of the bins it covers, so the bins that best reproduce a set of
    bands are the least-squares solution of that averaging. A magnitude the bands were read from
    comes back exactly wherever the bands resolve it, and where several bins were averaged into
    one band the solution spreads that band evenly over them. Measured across the round trip on
    forty probes, this halves the modulation a phase estimate then adds over the interpolation it
    replaces, on every kind of sound; `18-perceptual-readings.md` holds the table.
    """
    inverse: NDArray[np.float64] = np.linalg.pinv(band_weights(geometry), rcond=LEAST_SQUARES_CUTOFF)
    return inverse


def onto_linear_axis(magnitude: NDArray[np.float64], *, geometry: LogFrequencyGeometry) -> NDArray[np.float64]:
    """Read a band magnitude spectrogram back onto the linear Fourier grid it was averaged from.

    The reading is the least-squares one, held at zero from below since a magnitude is one; a bin
    no band touches reads as silence.
    """
    linear: NDArray[np.float64] = np.maximum(linear_axis_inverse(geometry) @ magnitude, 0.0)
    return linear


def build_log_frequency_canonicalizer(*, anchor: Anchor = DEFAULT_ANCHOR) -> LogFrequencyCanonicalizer:
    return LogFrequencyCanonicalizer(log_frequency_geometry(anchor=anchor))
