from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.envelope.glide import HELD_RATIO, PitchedAnalysis, PitchGlide, carried_excitation, glide_between
from samplemorph.envelope.settings import EnvelopeSettings, Excitation
from samplemorph.envelope.split import SplitSpectrum, split_spectrum
from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.transport.analysis import TransportAnalysis, read_magnitude
from samplemorph.transport.morph import (
    FIRST_END_WEIGHT,
    SECOND_END_WEIGHT,
    TransportedSpectrogram,
)
from samplemorph.transport.settings import TransportSettings
from samplemorph.transport.time_map import build_time_map


@dataclass(frozen=True)
class EnvelopePath:
    """The spectral path that moves the envelope between two sounds and sounds an excitation under it.

    Both sounds are aligned in time by the transport's own map and read along it, on the course the
    settings' timeline names, and each read frame is split into the smooth envelope it stands in and
    the excitation under it. The path's envelope lies at `weight` between the two in decibels, bin by
    bin, so resonances, brightness and the balance of registers move from one sound's to the other's.
    Under it sounds the excitation the settings name: one sound's whole, so its harmonics travel as
    one series at one pitch and a chord stays the chord it was, or the two crossfaded with the
    weight. The ends render through the same reading as every point between them, so each end is
    where the path arrives: under a kept excitation, that sound's own spectrum at its end of the
    path, and its pitch content under the other sound's envelope at the far end. On a held course
    every point lasts as long as the sound whose course it is, and that sound is read exactly as it
    was analyzed.
    """

    envelope_settings: EnvelopeSettings

    def __call__(
        self,
        first: TransportAnalysis,
        second: TransportAnalysis,
        *,
        weight: float,
        geometry: LogFrequencyGeometry,
        settings: TransportSettings,
    ) -> TransportedSpectrogram:
        """The magnitude `weight` of the way from one sound to another, the chosen excitation under the envelope between them.

        Raises:
            ValueError: the weight lies outside ``[0, 1]``.
        """
        return self.gliding(
            PitchedAnalysis(analysis=first, pitch_semitones=None),
            PitchedAnalysis(analysis=second, pitch_semitones=None),
            weight=weight,
            geometry=geometry,
            settings=settings,
        )

    def gliding(
        self,
        first: PitchedAnalysis,
        second: PitchedAnalysis,
        *,
        weight: float,
        geometry: LogFrequencyGeometry,
        settings: TransportSettings,
    ) -> TransportedSpectrogram:
        """The magnitude `weight` of the way from one sound to another, the kept excitation gliding when both ends sound a pitch.

        When both ends sound a pitch (`glide_between`), the kept excitation is carried to the pitch
        `weight` of the way between them, and both ends are split with the envelope the glide's
        settings allow, so the pitch moves with the excitation while the envelope carries the rest;
        otherwise the excitation sounds at its own pitch.

        Raises:
            ValueError: the weight lies outside ``[0, 1]``.
        """
        if not FIRST_END_WEIGHT <= weight <= SECOND_END_WEIGHT:
            raise ValueError(f"an envelope morph runs between weights 0 and 1, got {weight}")

        glide = glide_between(first, second)
        envelope_settings = (
            self.envelope_settings
            if glide is None
            else glide.envelope_settings(self.envelope_settings, geometry=geometry)
        )
        time_map = build_time_map(
            first.analysis,
            second.analysis,
            weight=self.envelope_settings.timeline.weight_at(weight),
            hop_length=geometry.hop_length,
            settings=settings,
        )
        first_split = _split_along(
            first.analysis,
            positions=time_map.first_positions,
            rates=time_map.first_rates,
            settings=settings,
            envelope_settings=envelope_settings,
        )
        second_split = _split_along(
            second.analysis,
            positions=time_map.second_positions,
            rates=time_map.second_rates,
            settings=settings,
            envelope_settings=envelope_settings,
        )
        excitation = self._excitation_under(first_split, second_split, weight=weight, glide=glide)
        magnitude = _between(first_split.envelope, second_split.envelope, weight=weight) * excitation
        return TransportedSpectrogram(magnitude=magnitude.astype(np.float32), sample_count=time_map.sample_count)

    def _excitation_under(
        self, first: SplitSpectrum, second: SplitSpectrum, *, weight: float, glide: PitchGlide | None
    ) -> NDArray[np.float32]:
        """The excitation the settings name at this weight, carried to the glide's pitch: one sound's whole, or the two crossfaded."""
        first_ratio = HELD_RATIO if glide is None else glide.first_ratio(weight=weight)
        second_ratio = HELD_RATIO if glide is None else glide.second_ratio(weight=weight)
        match self.envelope_settings.excitation:
            case Excitation.FIRST:
                return carried_excitation(first.excitation, ratio=first_ratio)
            case Excitation.SECOND:
                return carried_excitation(second.excitation, ratio=second_ratio)
            case Excitation.BOTH:
                crossfaded: NDArray[np.float32] = (1.0 - weight) * carried_excitation(
                    first.excitation, ratio=first_ratio
                ) + weight * carried_excitation(second.excitation, ratio=second_ratio)
                return crossfaded.astype(np.float32)


def _split_along(
    analysis: TransportAnalysis,
    *,
    positions: NDArray[np.float64],
    rates: NDArray[np.float64],
    settings: TransportSettings,
    envelope_settings: EnvelopeSettings,
) -> SplitSpectrum:
    """A sound read where a time map points, split into its envelope and its excitation."""
    magnitude = read_magnitude(analysis, positions=positions, rates=rates, settings=settings)
    return split_spectrum(magnitude, settings=envelope_settings)


def _between(first: NDArray[np.float32], second: NDArray[np.float32], *, weight: float) -> NDArray[np.float32]:
    """The envelope `weight` of the way from one to another, bin by bin in decibels."""
    between: NDArray[np.float32] = first ** (1.0 - weight) * second**weight
    return between
