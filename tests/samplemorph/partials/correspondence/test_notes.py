from __future__ import annotations

from typing import Final

import numpy as np

from samplemorph.partials.channels import Channels, channelize
from samplemorph.partials.correspondence.assignment import assign_with_fades
from samplemorph.partials.correspondence.notes import note_pairs
from samplemorph.partials.correspondence.pairing import pair_channels
from samplemorph.partials.profile import NotesCorrespondence
from samplemorph.partials.settings import NoteSettings
from tests.samplemorph.partials.conftest import harmonics, tracks_of

SETTINGS: Final[NoteSettings] = NoteSettings()
HARMONIC_COUNT: Final[int] = 8
CAP_SEMITONES: Final[float] = 12.0
EXPONENT: Final[float] = 2.0
C4, E4, G4, F4, A4, C6 = 261.63, 329.63, 392.0, 349.23, 440.0, 1046.5


def _chord(notes: tuple[float, ...]) -> np.ndarray:
    total = sum(harmonics(note, harmonic_count=HARMONIC_COUNT) for note in notes)
    return np.asarray(total) / len(notes)


def _channels(notes: tuple[float, ...]) -> Channels:
    return channelize(tracks_of(_chord(notes)), settings=SETTINGS)


def _pitches(channels: Channels, pairs: np.ndarray, column: int) -> list[float]:
    return [float(np.median(channels.notes[int(pair[column])].frequency_hz)) for pair in pairs]


def test_every_voice_of_a_chord_meets_the_voice_nearest_its_own_place() -> None:
    first, second = _channels((C4, E4, G4)), _channels((C4, F4, A4))

    pairs = note_pairs(first, second, cap_semitones=CAP_SEMITONES, exponent=EXPONENT)

    met = sorted(zip(_pitches(first, pairs, 0), _pitches(second, pairs, 1)))
    assert len(met) == 3
    for (here, there), (played, arriving) in zip(met, ((C4, C4), (E4, F4), (G4, A4)), strict=True):
        assert abs(here - played) < 5.0
        assert abs(there - arriving) < 5.0


def test_a_note_standing_further_off_than_the_cap_fades_instead_of_meeting() -> None:
    first, second = _channels((C4,)), _channels((C6,))

    pairs = note_pairs(first, second, cap_semitones=CAP_SEMITONES, exponent=EXPONENT)

    assert pairs.shape == (0, 2)


def test_the_harmonics_of_two_notes_that_meet_travel_harmonic_to_harmonic() -> None:
    first, second = _channels((C4, E4, G4)), _channels((C4, F4, A4))

    pairing = pair_channels(first, second, correspondence=NotesCorrespondence())

    for here, there in pairing.matched:
        if first.note[here] >= 0 and second.note[there] >= 0:
            assert first.harmonic[here] == second.harmonic[there]


def test_two_sets_meet_where_meeting_costs_less_than_fading() -> None:
    cost = np.array([[1.0, 8.0], [9.0, 2.0]])

    pairs = assign_with_fades(cost, first_fades=np.array([5.0, 5.0]), second_fades=np.array([5.0, 5.0]))

    assert sorted(map(tuple, pairs)) == [(0, 0), (1, 1)]


def test_an_item_whose_every_pairing_costs_more_than_fading_fades() -> None:
    cost = np.array([[1.0, 40.0], [40.0, 40.0]])

    pairs = assign_with_fades(cost, first_fades=np.array([5.0, 5.0]), second_fades=np.array([5.0, 5.0]))

    assert sorted(map(tuple, pairs)) == [(0, 0)]
