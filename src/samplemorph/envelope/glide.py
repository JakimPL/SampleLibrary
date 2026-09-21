from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.geometry import REFERENCE_FREQUENCY_HZ, SEMITONES_PER_OCTAVE, LogFrequencyGeometry
from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.placement import place_groups
from samplemorph.transport.segmentation import LOWEST_MOVED_BIN, segment_spectrum

HELD_RATIO: Final[float] = 1.0
# The envelope keeps ripples at least twice as slow as the widest harmonic spacing of either end,
# which leaves every harmonic comb to the excitation.
COMB_MARGIN: Final[float] = 2.0
WHOLE_SPECTRUM_PROMINENCE_DB: Final[float] = 1.0
SINGLE_GROUP: Final[NDArray[np.intp]] = np.zeros(1, dtype=np.intp)
WHOLE_GAIN: Final[NDArray[np.float64]] = np.ones(1)


@dataclass(frozen=True)
class PitchedAnalysis:
    """A sound's transport analysis beside the pitch it sounds at, or None where no pitch reads reliably.

    `pitch_semitones` counts from the reference frequency in the frame the analysis reads its
    frames at, so two ends heard in one frame differ by the interval a listener hears between them.
    """

    analysis: TransportAnalysis
    pitch_semitones: float | None

    @property
    def nbytes(self) -> int:
        return self.analysis.nbytes


@dataclass(frozen=True)
class PitchGlide:
    """The pitches two ends sound at, which a gliding envelope path carries the kept excitation between.

    At weight `w` the path sounds at the pitch `w` of the way from the first end's to the second's in
    semitones: the first end's excitation moves up by `w` of the interval, and the second end's down
    by the rest of it.
    """

    first_semitones: float
    second_semitones: float

    @property
    def interval_semitones(self) -> float:
        return self.second_semitones - self.first_semitones

    def first_ratio(self, *, weight: float) -> float:
        """The frequency ratio the first end's excitation is carried by at `weight`."""
        return float(2.0 ** (weight * self.interval_semitones / SEMITONES_PER_OCTAVE))

    def second_ratio(self, *, weight: float) -> float:
        """The frequency ratio the second end's excitation is carried by at `weight`."""
        return float(2.0 ** (-(1.0 - weight) * self.interval_semitones / SEMITONES_PER_OCTAVE))

    def envelope_settings(self, settings: EnvelopeSettings, *, geometry: LogFrequencyGeometry) -> EnvelopeSettings:
        """The envelope settings under this glide: as many coefficients as leave either end's harmonic comb out of the envelope.

        The `q`-th coefficient draws a ripple `2 N / q` bins long over `N` bins, and a comb whose
        harmonics stand `p` bins apart is a ripple of that length. Keeping fewer than `N / p`
        coefficients for the higher end, the sparser comb, keeps every ripple the envelope draws at
        least `COMB_MARGIN` times as long as any comb, so the harmonics travel with the excitation
        and the envelope between two notes holds neither note's series.
        """
        highest_hz = REFERENCE_FREQUENCY_HZ * 2.0 ** (
            max(self.first_semitones, self.second_semitones) / SEMITONES_PER_OCTAVE
        )
        bin_count = geometry.fft_length // 2 + 1
        comb_bins = highest_hz * geometry.fft_length / geometry.analysis_rate_hz
        clear = max(int(2.0 * bin_count / (COMB_MARGIN * comb_bins)), 1)
        return settings.model_copy(update={"coefficient_count": min(settings.coefficient_count, clear)})


def glide_between(first: PitchedAnalysis, second: PitchedAnalysis) -> PitchGlide | None:
    """The glide between two ends that both sound at a reliable pitch, and None when either does not."""
    if first.pitch_semitones is None or second.pitch_semitones is None:
        return None
    return PitchGlide(first_semitones=first.pitch_semitones, second_semitones=second.pitch_semitones)


def carried_excitation(excitation: NDArray[np.float32], *, ratio: float) -> NDArray[np.float32]:
    """An excitation with every lobe of every frame carried rigidly to `ratio` times its frequency.

    Each frame is cut into grains at its own valleys and moved as one group by `place_groups`, so a
    harmonic arrives as the lobe it was, with its width and its energy, which is what phase gradient
    integration reads a partial from; whatever is carried past the top of the spectrum leaves it, and
    whatever is carried down leaves the top empty, as a retuning does. A ratio of one returns the
    excitation as it is. Shape: ``(bins, frames)``, in and out.
    """
    if ratio == HELD_RATIO:
        return excitation
    energy = excitation.astype(np.float64) ** 2
    flat_outline = np.ones(energy.shape[0])
    scales = np.array([ratio])
    carried = np.empty_like(excitation)
    for frame in range(energy.shape[1]):
        shape = energy[:, frame]
        placed = place_groups(
            shape,
            segment_spectrum(shape, flat_outline, prominence_db=WHOLE_SPECTRUM_PROMINENCE_DB),
            piece_groups=SINGLE_GROUP,
            piece_gains=WHOLE_GAIN,
            piece_scales=scales,
        )
        placed[:LOWEST_MOVED_BIN] += shape[:LOWEST_MOVED_BIN]
        carried[:, frame] = np.sqrt(placed)
    return carried
