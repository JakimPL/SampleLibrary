from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.partials.correspondence.pairing import pair_channels
from samplemorph.partials.model import SinusoidalModel
from samplemorph.partials.paths import PitchPath, fade_progress, pitch_between
from samplemorph.partials.profile import MorphProfile
from samplemorph.partials.synthesis import oscillate
from samplemorph.partials.tracks import CENTS_PER_OCTAVE, PartialTracks
from samplemorph.transport.frame_reading import read_frames
from samplemorph.transport.morph import (
    FIRST_END_WEIGHT,
    SECOND_END_WEIGHT,
    TransportedSpectrogram,
    heard_as_analyzed,
    transport_along,
)
from samplemorph.transport.settings import TransportSettings
from samplemorph.transport.time_map import TimeMap, build_time_map
from samplemorph.vocoders.pghi import integrate_and_synthesize


@dataclass(frozen=True)
class PartialMorph:
    """How two sounds meet: the middle a profile draws, read on one geometry with the transport's own settings."""

    profile: MorphProfile
    geometry: LogFrequencyGeometry
    settings: TransportSettings

    def between(self, first: SinusoidalModel, second: SinusoidalModel, *, weight: float) -> NDArray[np.float64]:
        """The sound `weight` of the way from one to another, its partials sounded and the rest of it carried along.

        Both sounds are aligned in time by their whole analyses. The profile says which partial meets
        which, once for the pair, and each pair of partials then glides between its two pitches while
        its level follows the path between their two, a partial meeting nothing fading as it stands.
        What neither sound holds as a partial travels as a transport carries it, and the two are
        sounded together. A pair of sounds with no partial between them is exactly that transport.

        Raises:
            ValueError: the weight lies outside ``[0, 1]``, or the two sounds are heard at different rates.
        """
        if not FIRST_END_WEIGHT <= weight <= SECOND_END_WEIGHT:
            raise ValueError(f"a partials morph runs between weights 0 and 1, got {weight}")
        if first.rate_hz != second.rate_hz:
            raise ValueError(
                f"two sounds meet in one frame, and these are heard at {first.rate_hz} and {second.rate_hz} Hz"
            )
        if weight == FIRST_END_WEIGHT:
            return self._sounded(first.channels.tracks, residual=heard_as_analyzed(first.residual))
        if weight == SECOND_END_WEIGHT:
            return self._sounded(second.channels.tracks, residual=heard_as_analyzed(second.residual))

        curves = self.profile.curves
        time_map = build_time_map(
            first.whole,
            second.whole,
            weight=curves.time.at(weight),
            hop_length=self.geometry.hop_length,
            settings=self.settings,
        )
        return self._sounded(
            self._partials_between(first, second, time_map=time_map, weight=weight),
            residual=transport_along(
                first.residual,
                second.residual,
                time_map=time_map,
                weight=curves.residual.at(weight),
                settings=self.settings,
            ),
        )

    def _sounded(self, partials: PartialTracks, *, residual: TransportedSpectrogram) -> NDArray[np.float64]:
        """The residual made audible by phase gradient heap integration, with every partial sounded over it."""
        waveform = integrate_and_synthesize(
            residual.magnitude, geometry=self.geometry, frame_count=residual.sample_count
        )
        if partials.track_count == 0:
            return waveform
        return waveform + oscillate(partials, sample_count=residual.sample_count)

    def _partials_between(
        self, first: SinusoidalModel, second: SinusoidalModel, *, time_map: TimeMap, weight: float
    ) -> PartialTracks:
        """Every partial of the point between two sounds: the matched pairs on their way, and the rest on their own.

        A pair of partials carries the level path between the two it meets, and one meeting nothing
        fades by its energy while travelling with the object it belongs to, so the partials of a
        frame sum to what the level path asks of it and a note arrives whole even where a harmonic of
        it found no partner.
        """
        pairing = pair_channels(first.channels, second.channels, correspondence=self.profile.correspondence)
        read_first = _read_along(
            first.channels.tracks,
            positions=time_map.first_positions,
            rates=time_map.first_rates,
            settings=self.settings,
        )
        read_second = _read_along(
            second.channels.tracks,
            positions=time_map.second_positions,
            rates=time_map.second_rates,
            settings=self.settings,
        )
        exponent = self.settings.level_exponent
        curves = self.profile.curves
        pitch = curves.pitch.at(weight)
        timbre = curves.timbre.at(weight)
        level = curves.level.at(weight)
        faded = fade_progress(weight=level, law=self.profile.fade)
        cents = np.concatenate(
            (
                pitch_between(
                    read_first.cents[pairing.matched[:, 0]],
                    read_second.cents[pairing.matched[:, 1]],
                    weight=pitch,
                    path=self.profile.pitch,
                ),
                _travelled(
                    read_first.cents[pairing.first_alone],
                    moves=pairing.first_moves[pairing.first_alone],
                    weight=pitch,
                    path=self.profile.pitch,
                    arriving=False,
                ),
                _travelled(
                    read_second.cents[pairing.second_alone],
                    moves=pairing.second_moves[pairing.second_alone],
                    weight=pitch,
                    path=self.profile.pitch,
                    arriving=True,
                ),
            )
        )
        energy = np.concatenate(
            (
                _level_path(
                    read_first.energy[pairing.matched[:, 0]],
                    read_second.energy[pairing.matched[:, 1]],
                    weight=timbre,
                    exponent=exponent,
                ),
                (1.0 - faded) * read_first.energy[pairing.first_alone],
                faded * read_second.energy[pairing.second_alone],
            )
        )
        heard = _level_path(read_first.frame_energy, read_second.frame_energy, weight=level, exponent=exponent)
        total = energy.sum(axis=0)
        return PartialTracks(
            frequency_hz=(2.0 ** (cents / CENTS_PER_OCTAVE)).astype(np.float32),
            amplitude=np.sqrt(energy * np.where(total > 0.0, heard / np.where(total > 0.0, total, 1.0), 0.0)).astype(
                np.float32
            ),
            hop_length=first.channels.tracks.hop_length,
            rate_hz=first.rate_hz,
        )


def _travelled(
    cents: NDArray[np.float64], *, moves: NDArray[np.float64], weight: float, path: PitchPath, arriving: bool
) -> NDArray[np.float64]:
    """Where a partial meeting nothing stands on its way, carried by the move the object it belongs to makes.

    A partial whose object travels goes with it and fades as it goes, so a note arrives whole even
    where no partner was found for every harmonic of it, and one belonging to nothing holds the pitch
    it stands at. Shapes: `cents` is ``(partials, frames)`` and `moves` is ``(partials,)``.
    """
    carried = np.nan_to_num(moves)[:, None]
    return pitch_between(
        cents + carried if arriving else cents, cents if arriving else cents - carried, weight=weight, path=path
    )


@dataclass(frozen=True)
class _ReadPartials:
    """Partials read along a time map: the pitch each stands at in cents, and the energy it carries there.

    Shapes: both arrays are ``(partials, output frames)``.
    """

    cents: NDArray[np.float64]
    energy: NDArray[np.float64]

    @property
    def frame_energy(self) -> NDArray[np.float64]:
        total: NDArray[np.float64] = self.energy.sum(axis=0)
        return total


def _read_along(
    tracks: PartialTracks,
    *,
    positions: NDArray[np.float64],
    rates: NDArray[np.float64],
    settings: TransportSettings,
) -> _ReadPartials:
    """Every partial read where a time map points, its pitch held where the reading reaches past the sound's own frames."""
    half_width = settings.maximum_reading_half_width
    if tracks.track_count == 0:
        return _ReadPartials(cents=np.zeros((0, positions.shape[0])), energy=np.zeros((0, positions.shape[0])))

    def read(frames: NDArray[np.float32]) -> NDArray[np.float64]:
        return read_frames(frames, positions=positions, rates=rates, maximum_half_width=half_width).astype(np.float64)

    reached = read(np.ones((1, tracks.frame_count), dtype=np.float32))
    heard = read((CENTS_PER_OCTAVE * np.log2(tracks.frequency_hz)).astype(np.float32))
    return _ReadPartials(
        cents=heard / np.maximum(reached, float(np.finfo(np.float32).tiny)), energy=read(tracks.amplitude**2)
    )


def _level_path(
    first: NDArray[np.float64] | float, second: NDArray[np.float64] | float, *, weight: float, exponent: float
) -> NDArray[np.float64]:
    """The energy a point between two energies carries, the power mean of them at `exponent`, element by element."""
    mean = (1.0 - weight) * np.asarray(first) ** exponent + weight * np.asarray(second) ** exponent
    path: NDArray[np.float64] = mean ** (1.0 / exponent)
    return path
