from __future__ import annotations

from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.partials.channels import FREE_PARTIAL, Channels
from samplemorph.partials.correspondence.pairing import pair_channels
from samplemorph.partials.notes import Note
from samplemorph.partials.presets import TRAVELS_AS_OBJECTS
from samplemorph.partials.tracks import PartialTracks
from tests.samplemorph.partials.conftest import HOP_LENGTH, RATE_HZ

FRAME_COUNT: Final[int] = 32
CENTS_TOLERANCE: Final[float] = 5.0
OCTAVE_CENTS: Final[float] = 1200.0
FIFTH_CENTS: Final[float] = 701.955


def _note(fundamental_hz: float, *, harmonics: int) -> Note:
    reach = np.arange(1, harmonics + 1, dtype=np.intp)
    return Note(
        frequency_hz=np.full(FRAME_COUNT, fundamental_hz),
        inharmonicity=0.0,
        harmonics=reach,
        partials=reach - 1,
        share=1.0,
    )


def _sound(series: tuple[tuple[float, int], ...]) -> Channels:
    """A sound holding one note per series, each sounding its harmonics at `1 / k` of the first."""
    frequencies: list[float] = []
    amplitudes: list[float] = []
    note: list[int] = []
    harmonic: list[int] = []
    for index, (fundamental_hz, harmonics) in enumerate(series):
        for order in range(1, harmonics + 1):
            frequencies.append(fundamental_hz * order)
            amplitudes.append(1.0 / order)
            note.append(index)
            harmonic.append(order)
    return Channels(
        tracks=PartialTracks(
            frequency_hz=np.repeat(np.array(frequencies, dtype=np.float32)[:, None], FRAME_COUNT, axis=1),
            amplitude=np.repeat(np.array(amplitudes, dtype=np.float32)[:, None], FRAME_COUNT, axis=1),
            hop_length=HOP_LENGTH,
            rate_hz=RATE_HZ,
        ),
        note=np.array(note, dtype=np.intp),
        harmonic=np.array(harmonic, dtype=np.intp),
        fate=np.zeros(len(frequencies), dtype=np.intp),
        notes=tuple(_note(fundamental_hz, harmonics=harmonics) for fundamental_hz, harmonics in series),
    )


def _moves(first: Channels, second: Channels) -> NDArray[np.float64]:
    return pair_channels(first, second, correspondence=TRAVELS_AS_OBJECTS).first_moves


def test_a_whole_series_travels_by_one_move() -> None:
    """A sound and its own octave meet harmonic by harmonic, and every channel carries the same interval."""
    pairing = pair_channels(_sound(((100.0, 8),)), _sound(((200.0, 8),)), correspondence=TRAVELS_AS_OBJECTS)

    assert pairing.pair_count == 8
    assert np.allclose(pairing.first_moves, -OCTAVE_CENTS, atol=CENTS_TOLERANCE)


def test_every_channel_of_an_object_travels_whether_or_not_it_meets_one() -> None:
    """The harmonics the other sound stops short of go with their note, so it arrives as one note."""
    moves = _moves(_sound(((100.0, 12),)), _sound(((150.0, 5),)))

    assert not np.any(np.isnan(moves))
    assert np.allclose(moves, -FIFTH_CENTS, atol=CENTS_TOLERANCE)


def test_two_objects_take_a_move_each() -> None:
    first = _sound(((200.0, 6), (300.0, 6)))
    second = _sound(((200.0, 6), (450.0, 6)))

    moves = _moves(first, second)

    assert np.allclose(moves[:6], 0.0, atol=CENTS_TOLERANCE)
    assert np.allclose(moves[6:], -FIFTH_CENTS, atol=CENTS_TOLERANCE)


def test_an_object_meeting_nothing_holds_the_pitch_it_stands_at() -> None:
    moves = _moves(_sound(((100.0, 6),)), _sound(((3733.0, 6),)))

    assert np.all(np.isnan(moves))


def test_a_sound_with_no_channel_pairs_with_nothing() -> None:
    pairing = pair_channels(_sound(()), _sound(((200.0, 4),)), correspondence=TRAVELS_AS_OBJECTS)

    assert pairing.pair_count == 0
    assert np.array_equal(pairing.second_alone, np.arange(4))
