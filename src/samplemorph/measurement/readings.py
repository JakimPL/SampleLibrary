from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.measurement.comparison import held_out_distance_db, held_out_spectrum
from samplemorph.measurement.loudness import loudness_delta
from samplemorph.measurement.modulation_spectrum import modulation_spectrum_distance
from samplemorph.measurement.phase_quality import phase_quality
from samplemorph.rendering import SILENT_LEVEL


@dataclass(frozen=True)
class ReconstructionReadings:
    """Every reading the listening studies adopted, taken on one reconstruction against its reference.

    Read the pair as it will be heard, at matched loudness: `peak_dbfs` is then the crest the
    reconstruction carries over its original's, the reading that ordered percussive material the way
    the ear did, and `loudness_delta_lu` reads the residue the matching left. `fluctuation_excess`
    and `roughness_excess` are the signed modulation the reconstruction adds on the two axes a
    phase error is heard on, and their magnitude tracked the ear on percussive and tonal material;
    `modulation_distance` is the unsigned deviation. `modulation_excess` is the older flutter
    screen and `held_out_db` the log-magnitude distance, both kept for continuity with the tables
    in `docs/morphing/18-perceptual-readings.md`.
    """

    held_out_db: float
    loudness_delta_lu: float
    gated: bool
    peak_dbfs: float
    fluctuation_excess: float
    roughness_excess: float
    modulation_distance: float
    modulation_excess: float


def read_reconstruction(
    reconstruction: NDArray[np.float64],
    reference: NDArray[np.float64],
    *,
    source_rate_hz: int = NOMINAL_WAV_RATE,
) -> ReconstructionReadings:
    """Take every reading of `ReconstructionReadings` on one pair, at the rate the pair is heard at."""
    loudness = loudness_delta(reconstruction, reference, source_rate_hz=source_rate_hz)
    modulation = modulation_spectrum_distance(reconstruction, reference, source_rate_hz=source_rate_hz)
    flutter = phase_quality(reconstruction, reference)
    return ReconstructionReadings(
        held_out_db=held_out_distance_db(held_out_spectrum(reference), held_out_spectrum(reconstruction)),
        loudness_delta_lu=loudness.delta_lu,
        gated=loudness.gated,
        peak_dbfs=20.0 * float(np.log10(max(float(np.abs(reconstruction).max()), SILENT_LEVEL))),
        fluctuation_excess=modulation.fluctuation_excess,
        roughness_excess=modulation.roughness_excess,
        modulation_distance=modulation.distance,
        modulation_excess=flutter.modulation_excess,
    )
