from __future__ import annotations

from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.partials.correspondence.pairing import pair_partials
from samplemorph.partials.correspondence.partials import ordered_pairs, partial_voices
from samplemorph.partials.profile import NoCorrespondence, OrderedPartials
from samplemorph.partials.tracks import PartialTracks
from tests.samplemorph.partials.conftest import HOP_LENGTH, RATE_HZ

FRAME_COUNT: Final[int] = 32
AMPLITUDE: Final[float] = 0.5
CENTS_TOLERANCE: Final[float] = 1.0


def _tracks(frequencies_hz: tuple[float, ...], *, amplitudes: tuple[float, ...] | None = None) -> PartialTracks:
    held = np.repeat(np.array(frequencies_hz, dtype=np.float32)[:, None], FRAME_COUNT, axis=1)
    levels = np.array(amplitudes if amplitudes is not None else (AMPLITUDE,) * len(frequencies_hz), dtype=np.float32)
    return PartialTracks(
        frequency_hz=held,
        amplitude=np.repeat(levels[:, None], FRAME_COUNT, axis=1),
        hop_length=HOP_LENGTH,
        rate_hz=RATE_HZ,
    )


def _pairs(first: tuple[float, ...], second: tuple[float, ...]) -> NDArray[np.intp]:
    return ordered_pairs(partial_voices(_tracks(first)), partial_voices(_tracks(second)))


def test_a_partial_stands_at_the_pitch_it_holds_and_the_share_it_carries() -> None:
    voices = partial_voices(_tracks((220.0, 440.0), amplitudes=(1.0, 0.5)))

    assert voices.cents[1] - voices.cents[0] == pytest.approx(1200.0, abs=CENTS_TOLERANCE)
    assert voices.share.sum() == pytest.approx(1.0)
    assert voices.share[0] == pytest.approx(0.8)


def test_partials_of_two_sounds_meet_in_frequency_order() -> None:
    pairs = _pairs((300.0, 500.0, 900.0), (400.0, 800.0, 1200.0))

    assert np.array_equal(pairs, np.array([[0, 0], [1, 1], [2, 2]]))


def test_the_partials_left_over_are_those_furthest_from_any_partner() -> None:
    """Every partial of the smaller set travels, and the pairing keeps their order in frequency."""
    pairs = _pairs((300.0, 900.0), (310.0, 620.0, 880.0, 1760.0))

    assert np.array_equal(pairs, np.array([[0, 0], [1, 2]]))


def test_a_pairing_read_backward_pairs_the_same_partials() -> None:
    forward = _pairs((300.0, 900.0), (310.0, 620.0, 880.0, 1760.0))
    backward = _pairs((310.0, 620.0, 880.0, 1760.0), (300.0, 900.0))

    assert np.array_equal(forward, backward[:, ::-1])


def test_a_sound_with_no_partial_pairs_with_nothing() -> None:
    assert _pairs((), (400.0, 800.0)).shape == (0, 2)


def test_an_ordered_correspondence_leaves_the_unmatched_partials_on_their_own() -> None:
    first = _tracks((300.0, 900.0))
    second = _tracks((310.0, 620.0, 880.0, 1760.0))

    pairing = pair_partials(first, second, correspondence=OrderedPartials())

    assert pairing.pair_count == 2
    assert np.array_equal(pairing.first_alone, np.array([]))
    assert np.array_equal(pairing.second_alone, np.array([1, 3]))


def test_no_correspondence_leaves_every_partial_on_its_own() -> None:
    first = _tracks((300.0, 900.0))
    second = _tracks((400.0, 800.0, 1600.0))

    pairing = pair_partials(first, second, correspondence=NoCorrespondence())

    assert pairing.pair_count == 0
    assert np.array_equal(pairing.first_alone, np.array([0, 1]))
    assert np.array_equal(pairing.second_alone, np.array([0, 1, 2]))
