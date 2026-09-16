from __future__ import annotations

import time
from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.measurement.comparison import held_out_spectrum
from samplemorph.measurement.morph_path.readings import HeardPath, PathPoint, read_path
from samplemorph.measurement.morph_path.spectra import ACTIVE_DEPTH_DB
from samplemorph.partials.model import SinusoidalModel
from samplemorph.partials.morph import PartialMorph
from samplemorph.partials.presets import PROFILE_PRESETS
from samplemorph.partials.profile import MorphProfile
from samplemorph.partials.tracks import CENTS_PER_OCTAVE
from samplemorph.transport.morph import transport
from samplemorph.transport.settings import TransportSettings
from samplemorph.vocoders.pghi import integrate_and_synthesize
from tests.samplemorph.partials.conftest import GEOMETRY, RATE_HZ, harmonics, model_of, noise_hit, times

MIDPOINT: Final[float] = 0.5
LOW_TONE_HZ: Final[float] = 220.0
HIGH_TONE_HZ: Final[float] = 330.0
HARMONIC_COUNT: Final[int] = 8
SERIES_REACH_HZ: Final[float] = 6.0
SERIES_SHARE_FLOOR: Final[float] = 0.95
END_HEADROOM_DB: Final[float] = 1.0
LEVEL_TOLERANCE_DB: Final[float] = 0.5
PEAK_REACH_HZ: Final[float] = 20.0
CONTINUITY_WEIGHT: Final[float] = 1e-3
CONTINUITY_CEILING_DB: Final[float] = 2.0
SYMMETRY_CEILING_DB: Final[float] = 0.5
IDENTITY_CEILING_DB: Final[float] = 1.0
WOBBLE_CEILING_CENTS: Final[float] = 3.0
ROUGHNESS_EXCESS_CEILING: Final[float] = 0.02
HARMONICITY_FLOOR: Final[float] = 0.9
CENTS_TOLERANCE: Final[float] = 5.0
LONG_SECONDS: Final[float] = 3.0
LONGEST_RENDER_SECONDS: Final[float] = 4.0
SLIDE: Final[MorphProfile] = PROFILE_PRESETS["slide"]
GLIDE: Final[MorphProfile] = PROFILE_PRESETS["glide"]
C4, E4, G4, F4, A4 = 261.63, 329.63, 392.0, 349.23, 440.0


def _morph(
    first: SinusoidalModel, second: SinusoidalModel, weight: float, *, profile: MorphProfile = SLIDE
) -> NDArray[np.float64]:
    return PartialMorph(profile=profile, geometry=GEOMETRY, settings=TransportSettings()).between(
        first, second, weight=weight
    )


def _transported(first: SinusoidalModel, second: SinusoidalModel, weight: float) -> NDArray[np.float64]:
    spectrogram = transport(first.whole, second.whole, weight=weight, geometry=GEOMETRY, settings=TransportSettings())
    return integrate_and_synthesize(spectrogram.magnitude, geometry=GEOMETRY, frame_count=spectrogram.sample_count)


def _chord(notes: tuple[float, ...], *, seconds: float = 1.5) -> NDArray[np.float64]:
    seconds_axis = times(seconds)
    total = np.sum(
        [
            np.sin(2.0 * np.pi * harmonic * note * seconds_axis) / harmonic
            for note in notes
            for harmonic in range(1, 11)
        ],
        axis=0,
    )
    chord: NDArray[np.float64] = 0.5 * total / np.abs(total).max()
    return chord


def _audible_distance_db(rendered: NDArray[np.float64], reference: NDArray[np.float64]) -> float:
    """How far a render stands from a sound over the cells the sound is heard in, in decibels.

    A synthetic tone has no noise floor of its own, so the cells far under its partials hold
    whatever each route leaves there; reading the cells within `ACTIVE_DEPTH_DB` of the sound's
    loudest is reading what a listener hears of it.
    """
    read, against = held_out_spectrum(rendered), held_out_spectrum(reference)
    width = min(read.shape[1], against.shape[1])
    read, against = read[:, :width], against[:, :width]
    active = against >= against.max() - ACTIVE_DEPTH_DB
    return float(np.sqrt(np.mean((read[active] - against[active]) ** 2)))


def _harmonic_levels_db(waveform: NDArray[np.float64], fundamental_hz: float) -> NDArray[np.float64]:
    """Each harmonic's amplitude in decibels, read over the render's middle half.

    The energy of the whole lobe stands for the amplitude, so a partial sitting between two bins
    reads as loud as one sitting on a bin.
    """
    middle = waveform[waveform.shape[0] // 4 : 3 * waveform.shape[0] // 4]
    taper = np.hanning(middle.shape[0])
    energy = np.abs(np.fft.rfft(middle * taper)) ** 2
    frequencies = np.fft.rfftfreq(middle.shape[0], 1.0 / RATE_HZ)
    scale = middle.shape[0] * float((taper**2).sum())
    levels: NDArray[np.float64] = 20.0 * np.log10(
        [
            2.0 * np.sqrt(energy[np.abs(frequencies - harmonic * fundamental_hz) <= PEAK_REACH_HZ].sum() / scale)
            for harmonic in range(1, HARMONIC_COUNT + 1)
        ]
    )
    return levels


def _series_share(waveform: NDArray[np.float64], fundamental_hz: float) -> float:
    """The share of a render's energy standing on the harmonics of `fundamental_hz`, read over its middle half."""
    middle = waveform[waveform.shape[0] // 4 : 3 * waveform.shape[0] // 4]
    spectrum = np.abs(np.fft.rfft(middle * np.hanning(middle.shape[0]))) ** 2
    frequencies = np.fft.rfftfreq(middle.shape[0], 1.0 / RATE_HZ)
    near = np.zeros(spectrum.shape[0], dtype=bool)
    for harmonic in range(1, HARMONIC_COUNT + 1):
        near |= np.abs(frequencies - harmonic * fundamental_hz) <= SERIES_REACH_HZ
    return float(spectrum[near].sum() / spectrum.sum())


@pytest.fixture(scope="module")
def tones() -> tuple[SinusoidalModel, SinusoidalModel]:
    return (
        model_of(harmonics(LOW_TONE_HZ, harmonic_count=HARMONIC_COUNT, brightness=0.9)),
        model_of(harmonics(HIGH_TONE_HZ, harmonic_count=HARMONIC_COUNT, brightness=0.55)),
    )


@pytest.fixture(scope="module")
def chords() -> tuple[SinusoidalModel, SinusoidalModel]:
    return model_of(_chord((C4, E4, G4))), model_of(_chord((C4, F4, A4)))


def test_a_pair_of_sounds_holding_no_partial_travels_exactly_as_a_transport_carries_it() -> None:
    """Percussion keeps the route the ear already accepted: with nothing to sound, the morph is the transport itself."""
    first, second = model_of(noise_hit(seed=21)), model_of(noise_hit(seed=22, decay_per_second=4.0))

    for weight in (0.0, MIDPOINT, 1.0):
        assert np.array_equal(_morph(first, second, weight), _transported(first, second, weight))


def test_each_end_stands_where_the_transport_route_leaves_it(tones: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    """Sounding a sound's own partials over its own residual costs no more than carrying the whole of it does."""
    first, second = tones
    originals = (
        harmonics(LOW_TONE_HZ, harmonic_count=HARMONIC_COUNT, brightness=0.9),
        harmonics(HIGH_TONE_HZ, harmonic_count=HARMONIC_COUNT, brightness=0.55),
    )

    for weight, original in zip((0.0, 1.0), originals, strict=True):
        sounded = _audible_distance_db(_morph(first, second, weight), original)
        carried = _audible_distance_db(_transported(first, second, weight), original)
        assert sounded <= carried + END_HEADROOM_DB


def test_each_end_sounds_its_own_partials_at_the_levels_they_stood_at(
    tones: tuple[SinusoidalModel, SinusoidalModel],
) -> None:
    first, second = tones
    original = harmonics(HIGH_TONE_HZ, harmonic_count=HARMONIC_COUNT, brightness=0.55)

    rendered = _morph(first, second, 1.0)

    apart = _harmonic_levels_db(rendered, HIGH_TONE_HZ) - _harmonic_levels_db(original, HIGH_TONE_HZ)
    assert np.abs(apart).max() <= LEVEL_TOLERANCE_DB


def test_two_tones_meet_as_one_tone_at_the_pitch_between_them(tones: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    first, second = tones
    between_hz = float(np.sqrt(LOW_TONE_HZ * HIGH_TONE_HZ))

    assert _series_share(_morph(first, second, MIDPOINT), between_hz) >= SERIES_SHARE_FLOOR


def test_a_crossfade_holds_both_tones_where_they_stand(tones: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    first, second = tones
    crossfaded = _morph(first, second, MIDPOINT, profile=PROFILE_PRESETS["crossfade"])

    assert _series_share(crossfaded, LOW_TONE_HZ) + _series_share(crossfaded, HIGH_TONE_HZ) >= SERIES_SHARE_FLOOR
    assert _series_share(crossfaded, float(np.sqrt(LOW_TONE_HZ * HIGH_TONE_HZ))) < 1.0 - SERIES_SHARE_FLOOR


def test_the_midpoint_of_two_chords_holds_as_steady_as_the_chords_themselves(
    chords: tuple[SinusoidalModel, SinusoidalModel],
) -> None:
    """The pairing is read once for the pair, so a partial glides along one path from end to end."""
    first, second = chords
    points = tuple(
        PathPoint(weight=weight, waveform=_morph(first, second, weight, profile=GLIDE))
        for weight in (0.0, MIDPOINT, 1.0)
    )

    readings = read_path(
        HeardPath(points=points, first=_chord((C4, E4, G4)), second=_chord((C4, F4, A4)), rate_hz=RATE_HZ)
    )

    middle = readings.points[1].screen
    assert middle.wobble_cents <= WOBBLE_CEILING_CENTS
    assert middle.roughness_excess <= ROUGHNESS_EXCESS_CEILING
    assert middle.harmonicity >= HARMONICITY_FLOOR


def test_the_notes_of_two_chords_meet_note_to_note_and_glide_between_them(
    chords: tuple[SinusoidalModel, SinusoidalModel],
) -> None:
    """C to C, E to F and G to A: every point is the chord standing that far along each voice's own path."""
    first, second = chords

    for weight in (0.25, MIDPOINT, 0.75):
        notes = model_of(_morph(first, second, weight, profile=GLIDE)).channels.notes
        read = sorted(float(np.median(note.frequency_hz)) for note in notes)
        between = sorted(here ** (1.0 - weight) * there**weight for here, there in ((C4, C4), (E4, F4), (G4, A4)))
        assert len(read) == len(between)
        for found, expected in zip(read, between, strict=True):
            assert abs(CENTS_PER_OCTAVE * np.log2(found / expected)) <= CENTS_TOLERANCE


def test_a_path_read_backward_is_the_same_path(tones: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    first, second = tones

    forward = _morph(first, second, 0.25)
    backward = _morph(second, first, 0.75)

    assert _audible_distance_db(forward, backward) <= SYMMETRY_CEILING_DB


def test_a_sound_morphed_with_itself_stays_itself(tones: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    first, _ = tones

    assert _audible_distance_db(_morph(first, first, MIDPOINT), _morph(first, first, 0.0)) <= IDENTITY_CEILING_DB


def test_a_point_just_past_an_end_sounds_like_that_end(tones: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    first, second = tones

    near = _morph(first, second, CONTINUITY_WEIGHT)

    assert _audible_distance_db(near, _morph(first, second, 0.0)) <= CONTINUITY_CEILING_DB


@pytest.mark.parametrize("weight", (-0.1, 1.1))
def test_a_weight_outside_the_path_is_refused(weight: float, tones: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    with pytest.raises(ValueError, match="between weights 0 and 1"):
        _morph(tones[0], tones[1], weight)


def test_two_sounds_heard_at_different_rates_are_refused(tones: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    first, second = tones
    elsewhere = SinusoidalModel(
        channels=second.channels, whole=second.whole, residual=second.residual, rate_hz=2.0 * RATE_HZ
    )

    with pytest.raises(ValueError, match="one frame"):
        _morph(first, elsewhere, MIDPOINT)


def test_a_long_midpoint_renders_in_less_time_than_it_lasts() -> None:
    first = model_of(harmonics(LOW_TONE_HZ, harmonic_count=HARMONIC_COUNT, seconds=LONG_SECONDS))
    second = model_of(harmonics(HIGH_TONE_HZ, harmonic_count=HARMONIC_COUNT, seconds=LONG_SECONDS))
    _morph(first, second, MIDPOINT)

    started = time.perf_counter()
    _morph(first, second, MIDPOINT)

    assert time.perf_counter() - started <= LONGEST_RENDER_SECONDS
