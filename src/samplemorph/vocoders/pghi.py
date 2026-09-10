from __future__ import annotations

from functools import cache
from typing import Final, Protocol

import librosa
import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.linear_axis import onto_linear_axis
from samplemorph.geometry import AnalysisWindow, LogFrequencyGeometry, analysis_taper
from samplemorph.images import AnalysisSpectrogram

PGHI_TOLERANCE: Final[float] = 1e-6
MISSING_EXTRA_MESSAGE: Final[str] = (
    "pghipy is not installed. Install the 'pghi' extra (uv sync --extra pghi) to estimate phase by "
    "gradient heap integration."
)


class _PhaseIntegrator(Protocol):
    # pghipy.pghi reads a magnitude shaped (frames, bins) with the analysis length, its hop, the
    # Gaussian's gamma and the relative level below which a bin is left out, and returns a phase of
    # the same shape; pghipy ships no type stubs, so the contract is stated here.
    def __call__(
        self, magnitude: NDArray[np.float64], *, win_length: int, hop_length: int, gamma: float, tol: float
    ) -> NDArray[np.float64]: ...


@cache
def _integrator() -> _PhaseIntegrator:
    try:
        # pylint: disable=import-outside-toplevel
        from pghipy import pghi
    except ImportError as error:
        raise ImportError(MISSING_EXTRA_MESSAGE) from error

    integrator: _PhaseIntegrator = pghi
    return integrator


class PghiVocoder:
    """Estimates the phase a magnitude carries from that magnitude's own gradients.

    Under a Gaussian analysis the phase gradient of a signal is a closed form of its magnitude
    gradient, so phase gradient heap integration (Prusa, Balazs and Sondergaard, 2017) integrates
    the phase outward from the loudest bins in one pass, with nothing iterated and nothing learned.
    Measured on the representation ladder it reads within the flutter of the true phase on a clean
    Gaussian analysis, which is what retires a learned phase model for reconstruction. The geometry
    names the analysis, so the vocoder reads the Gaussian's spread from it; the integration wants a
    transform at least sixteen times its hop to read the gradients cleanly.
    """

    def synthesize(self, spectrogram: AnalysisSpectrogram) -> NDArray[np.float64]:
        """Integrate a phase for the magnitude and return the frames it makes audible.

        Raises:
            ValueError: the spectrogram's geometry is not a log-frequency analysis under a Gaussian taper.
        """
        geometry = spectrogram.geometry
        match geometry:
            case LogFrequencyGeometry(analysis_window=AnalysisWindow.GAUSSIAN):
                pass
            case LogFrequencyGeometry():
                raise ValueError(
                    "phase gradient heap integration reads a Gaussian analysis, and this spectrogram was "
                    f"analyzed under a {geometry.analysis_window.value} taper"
                )
            case _:
                raise ValueError(
                    "phase gradient heap integration reads a log-frequency analysis, and this spectrogram "
                    f"is a {geometry.kind} one"
                )

        frames_first = np.ascontiguousarray(onto_linear_axis(spectrogram.magnitude, geometry=geometry).T)
        phase = _integrator()(
            frames_first,
            win_length=geometry.fft_length,
            hop_length=geometry.hop_length,
            gamma=geometry.phase_gradient_spread,
            tol=PGHI_TOLERANCE,
        )
        waveform: NDArray[np.float64] = librosa.istft(
            (frames_first * np.exp(1j * phase)).T,
            hop_length=geometry.hop_length,
            n_fft=geometry.fft_length,
            window=analysis_taper(geometry),
            length=spectrogram.frame_count,
        )
        return waveform
