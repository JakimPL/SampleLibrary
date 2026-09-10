from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import librosa
import numpy as np
from numpy.typing import NDArray

PHASE_FFT_LENGTH: Final[int] = 1024
PHASE_HOP_LENGTH: Final[int] = 256
LOG_FLOOR: Final[float] = 1e-5


@dataclass(frozen=True)
class PhaseQuality:
    """Two readings of how a reconstruction differs from the one listening accepts.

    The reference is the same magnitude carried by the source's own phase, the reconstruction
    listening already keeps, so each reading charges the phase estimate alone rather than what the
    representation lost. `magnitude_distance` is the plain log-magnitude difference our evaluation
    already reports, kept here to show what it sees of a phase artifact. `modulation_excess` is how
    much frame-to-frame magnitude flutter the reconstruction carries over the reference, and its
    sign names the fault: a positive value is a comb a phase estimate sweeps through a held note
    that the steady reference has none of, the Griffin-Lim gargle; a negative value is a
    reconstruction smoother than the true phase, heard as a loss of clarity. A reconstruction that
    moves as the reference does reads near zero, so zero is the target rather than the floor.
    """

    magnitude_distance: float
    modulation_excess: float


def _log_magnitude(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    spectrum = np.abs(librosa.stft(waveform, n_fft=PHASE_FFT_LENGTH, hop_length=PHASE_HOP_LENGTH))
    return np.log(np.maximum(spectrum, LOG_FLOOR))


def _loudness_weight(reference_log_magnitude: NDArray[np.float64]) -> NDArray[np.float64]:
    """A per-bin weight that counts a bin by how loud the reference is there, summing to one."""
    above_floor = np.maximum(reference_log_magnitude - np.log(LOG_FLOOR), 0.0)
    total = float(above_floor.sum())
    return above_floor / total if total > 0.0 else np.full_like(above_floor, 1.0 / above_floor.size)


def _frame_flutter(log_magnitude: NDArray[np.float64]) -> NDArray[np.float64]:
    """How much each bin's magnitude moves from one frame to the next, as a per-bin mean.

    A steady partial barely moves; a bin a sweeping comb passes through rises and falls frame to
    frame. Reading the movement of the magnitude rather than of the phase is what lets this hear
    the comb a listener hears rather than the local phase advance that listening does not track.
    """
    if log_magnitude.shape[1] < 2:
        return np.zeros(log_magnitude.shape[0])
    return np.abs(np.diff(log_magnitude, axis=1)).mean(axis=1)


def phase_quality(
    reconstruction: NDArray[np.float64],
    reference: NDArray[np.float64],
) -> PhaseQuality:
    """Measure a reconstruction against the source's own-phase reconstruction on the three readings.

    Both waveforms come from one magnitude on one set of frames, so they are already aligned and a
    bin of one meets the same moment in the other.
    """
    width = min(reconstruction.shape[0], reference.shape[0])
    reconstruction_log = _log_magnitude(reconstruction[:width])
    reference_log = _log_magnitude(reference[:width])
    frames = min(reconstruction_log.shape[1], reference_log.shape[1])
    reconstruction_log = reconstruction_log[:, :frames]
    reference_log = reference_log[:, :frames]
    weight = _loudness_weight(reference_log)

    bin_weight = weight.mean(axis=1)
    magnitude_distance = float(np.sqrt((weight * (reconstruction_log - reference_log) ** 2).sum()))
    flutter_excess = _frame_flutter(reconstruction_log) - _frame_flutter(reference_log)
    modulation_excess = float((bin_weight * flutter_excess).sum() / bin_weight.sum())
    return PhaseQuality(magnitude_distance=magnitude_distance, modulation_excess=modulation_excess)
