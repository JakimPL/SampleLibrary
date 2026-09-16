from __future__ import annotations

from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.partials.channels import FREE_PARTIAL, Channels
from samplemorph.partials.correspondence.pairing import ChannelPairing, pair_channels
from samplemorph.partials.presets import FADES_IN_PLACE, HOLDS_WHAT_IS_SHARED, SLIDES_IN_ORDER, TRAVELS
from samplemorph.partials.profile import Correspondence
from samplemorph.partials.tracks import PartialTracks
from samplemorph.partials.voices import partial_voices
from tests.samplemorph.partials.conftest import HOP_LENGTH, RATE_HZ

FRAME_COUNT: Final[int] = 32
AMPLITUDE: Final[float] = 0.5
CENTS_TOLERANCE: Final[float] = 1.0
WHOLE_LIFE: Final[tuple[float, float]] = (0.0, 1.0)


def _tracks(
    frequencies_hz: tuple[float, ...],
    *,
    amplitudes: tuple[float, ...] | None = None,
    lives: tuple[tuple[float, float], ...] | None = None,
) -> PartialTracks:
    levels = np.array(amplitudes if amplitudes is not None else (AMPLITUDE,) * len(frequencies_hz), dtype=np.float32)
    heard = np.repeat(levels[:, None], FRAME_COUNT, axis=1)
    frames = np.arange(FRAME_COUNT) / max(FRAME_COUNT - 1, 1)
    for track, (starts, ends) in enumerate(lives if lives is not None else (WHOLE_LIFE,) * len(frequencies_hz)):
        heard[track] = np.where((frames >= starts) & (frames <= ends), heard[track], 0.0)
    return PartialTracks(
        frequency_hz=np.repeat(np.array(frequencies_hz, dtype=np.float32)[:, None], FRAME_COUNT, axis=1),
        amplitude=heard,
        hop_length=HOP_LENGTH,
        rate_hz=RATE_HZ,
    )


def _sound(
    frequencies_hz: tuple[float, ...],
    *,
    amplitudes: tuple[float, ...] | None = None,
    lives: tuple[tuple[float, float], ...] | None = None,
) -> Channels:
    """Partials standing free of any note, which is every channel a pairing reads."""
    tracks = _tracks(frequencies_hz, amplitudes=amplitudes, lives=lives)
    return Channels(
        tracks=tracks,
        note=np.full(tracks.track_count, FREE_PARTIAL, dtype=np.intp),
        harmonic=np.zeros(tracks.track_count, dtype=np.intp),
        notes=(),
    )


def _pairing(
    first: tuple[float, ...], second: tuple[float, ...], *, correspondence: Correspondence = TRAVELS
) -> ChannelPairing:
    return pair_channels(_sound(first), _sound(second), correspondence=correspondence)


def _matched(first: tuple[float, ...], second: tuple[float, ...], **named: Correspondence) -> NDArray[np.intp]:
    return _pairing(first, second, **named).matched


def test_a_partial_stands_at_the_pitch_it_holds_and_the_share_it_carries() -> None:
    voices = partial_voices(_tracks((220.0, 440.0), amplitudes=(1.0, 0.5)))

    assert voices.cents[1] - voices.cents[0] == pytest.approx(1200.0, abs=CENTS_TOLERANCE)
    assert voices.share.sum() == pytest.approx(1.0)
    assert voices.share[0] == pytest.approx(0.8)


def test_a_partial_is_placed_on_the_stretch_the_whole_sound_sounds_through() -> None:
    voices = partial_voices(_tracks((220.0, 440.0), lives=((0.0, 1.0), (0.5, 1.0))))

    assert voices.onset[0] == pytest.approx(0.0)
    assert voices.lifetime[0] == pytest.approx(1.0)
    assert voices.onset[1] == pytest.approx(0.5, abs=0.05)


def test_two_harmonic_series_a_fifth_apart_meet_harmonic_by_harmonic() -> None:
    """Every harmonic proposes the same interval, so the series travels as one without a note being sought."""
    matched = _matched((100.0, 200.0, 300.0, 400.0), (150.0, 300.0, 450.0, 600.0))

    assert np.array_equal(matched, np.array([[0, 0], [1, 1], [2, 2], [3, 3]]))


def test_partials_further_apart_than_a_semitone_travel_to_each_other() -> None:
    """Two basses a minor third apart are one sound turning into another, and every partial carries the move."""
    matched = _matched((59.1, 108.8), (49.9, 99.2))

    assert np.array_equal(matched, np.array([[0, 0], [1, 1]]))


def test_a_partial_with_nothing_within_reach_fades_where_it_stands() -> None:
    pairing = _pairing((440.0,), (2489.0,))

    assert pairing.pair_count == 0
    assert np.array_equal(pairing.first_alone, np.array([0]))
    assert np.array_equal(pairing.second_alone, np.array([0]))


def test_a_partial_travels_to_the_partner_it_matches_in_loudness_where_loudness_is_asked_for() -> None:
    """Loudness stands at rest in the presets, since a partial growing louder is what a morph carries."""
    first = _sound((440.0,), amplitudes=(1.0,))
    second = _sound((415.3, 466.2), amplitudes=(0.2, 1.0))

    matched = pair_channels(first, second, correspondence=Correspondence(level_weight=1.0)).matched

    assert np.array_equal(matched, np.array([[0, 1]]))


def test_a_partial_travels_to_the_partner_it_is_heard_beside() -> None:
    """Two partials at one pitch stand apart by when they sound, and a partial meets the one it shares its time with."""
    first = _sound((100.0, 440.0), lives=(WHOLE_LIFE, (0.0, 0.25)))
    second = _sound((100.0, 440.0, 440.0), lives=(WHOLE_LIFE, (0.7, 1.0), (0.0, 0.3)))

    matched = pair_channels(first, second, correspondence=TRAVELS).matched

    assert np.array_equal(matched, np.array([[0, 0], [1, 2]]))


def test_partials_sliding_in_order_keep_their_order_in_frequency() -> None:
    matched = _matched((300.0, 500.0, 900.0), (400.0, 800.0, 1200.0), correspondence=SLIDES_IN_ORDER)

    assert np.array_equal(matched, np.array([[0, 0], [1, 1], [2, 2]]))


def test_the_partials_left_over_are_those_furthest_from_any_partner() -> None:
    pairing = _pairing((300.0, 900.0), (310.0, 620.0, 880.0, 1760.0), correspondence=SLIDES_IN_ORDER)

    assert np.array_equal(pairing.matched, np.array([[0, 0], [1, 2]]))
    assert np.array_equal(pairing.first_alone, np.array([]))
    assert np.array_equal(pairing.second_alone, np.array([1, 3]))


def test_a_pairing_read_backward_pairs_the_same_partials() -> None:
    forward = _matched((300.0, 900.0), (310.0, 620.0, 880.0, 1760.0))
    backward = _matched((310.0, 620.0, 880.0, 1760.0), (300.0, 900.0))

    assert np.array_equal(forward, backward[:, ::-1])


def test_holding_what_is_shared_keeps_the_common_partials_and_fades_the_rest() -> None:
    pairing = _pairing((440.0, 660.0), (441.0, 880.0), correspondence=HOLDS_WHAT_IS_SHARED)

    assert np.array_equal(pairing.matched, np.array([[0, 0]]))
    assert np.array_equal(pairing.first_alone, np.array([1]))
    assert np.array_equal(pairing.second_alone, np.array([1]))


def test_a_free_fade_leaves_every_partial_on_its_own() -> None:
    pairing = _pairing((300.0, 900.0), (400.0, 800.0, 1600.0), correspondence=FADES_IN_PLACE)

    assert pairing.pair_count == 0
    assert np.array_equal(pairing.first_alone, np.array([0, 1]))
    assert np.array_equal(pairing.second_alone, np.array([0, 1, 2]))


def test_a_sound_with_no_partial_pairs_with_nothing() -> None:
    pairing = _pairing((), (400.0, 800.0))

    assert pairing.pair_count == 0
    assert np.array_equal(pairing.second_alone, np.array([0, 1]))
