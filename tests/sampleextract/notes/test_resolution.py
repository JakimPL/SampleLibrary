from __future__ import annotations

from dataclasses import dataclass

import pytest
from trackmod.core.instruments.instrument import Instrument
from trackmod.core.instruments.keymap import KeyAssignment, pitched_keymap, routed_keymap
from trackmod.core.notes.pitch import Note
from trackmod.core.patterns.builder import PatternBuilder
from trackmod.core.patterns.cell import Cell
from trackmod.core.samples.sample import Sample
from trackmod.core.songs.order import OrderList
from trackmod.core.songs.playback import Playback
from trackmod.core.songs.song import Song
from trackmod.core.voices.voices import InstrumentVoices, SampleVoices

from samplecore.models.tracker import TrackerFormat
from sampleextract.notes.resolution import resolve_module_instruments, resolve_note_events
from sampleextract.parsing import parse_module

MODULE_ID = 7
PRESSED_KEY = Note(60)
SILENT_ALTERNATIVE_KEY = Note(48)
# Every slot the small songs below could name, so a test states only what it withholds.
CATALOGUED_SLOTS = frozenset((instrument, slot) for instrument in range(4) for slot in range(4))


@dataclass(frozen=True)
class FormatCase:
    """One tracker format's own module bytes, named by the fixture that builds them."""

    fixture_name: str
    tracker: TrackerFormat


FORMAT_CASES = (
    FormatCase("xm_module_bytes", TrackerFormat.XM),
    FormatCase("it_module_bytes", TrackerFormat.IT),
    FormatCase("mod_module_bytes", TrackerFormat.MOD),
    FormatCase("s3m_module_bytes", TrackerFormat.S3M),
)


def _song(*, samples: tuple[Sample, ...], instruments: tuple[Instrument, ...], pattern: PatternBuilder) -> Song:
    return Song(
        name="probe",
        channels=pattern.channels,
        patterns=(pattern.build(),),
        order=OrderList(entries=(0,)),
        voices=InstrumentVoices(instruments=instruments, samples=samples),
        playback=Playback(speed=6, tempo=125),
    )


def _sample(*, frames: int = 32, name: str = "bell") -> Sample:
    return Sample(name=name, pcm=[0.0] * frames, rate=8363)


@pytest.mark.parametrize("case", FORMAT_CASES, ids=lambda case: case.tracker.value)
def test_every_format_resolves_its_one_note_to_the_first_occurrence(
    case: FormatCase, request: pytest.FixtureRequest, played_note: Note
) -> None:
    song = parse_module(request.getfixturevalue(case.fixture_name), tracker=case.tracker)

    events = resolve_note_events(song, module_id=MODULE_ID, catalogued_slots=CATALOGUED_SLOTS)

    assert len(events) == 1
    assert events[0].note == played_note
    assert events[0].sounded_note == played_note
    assert events[0].instrument_index == 0
    assert events[0].sample_slot == 0


def test_an_impulse_tracker_keymap_resolves_a_key_to_the_note_it_sounds(
    transposing_it_module_bytes: bytes, routed_key: Note, routed_sounded_note: Note
) -> None:
    """The resolved note is what the routing produces, which is a different value from the key pressed."""
    song = parse_module(transposing_it_module_bytes, tracker=TrackerFormat.IT)

    events = resolve_note_events(song, module_id=MODULE_ID, catalogued_slots=CATALOGUED_SLOTS)

    assert len(events) == 1
    assert events[0].note == routed_key
    assert events[0].sounded_note == routed_sounded_note


def test_a_cell_naming_no_instrument_leaves_its_routing_open() -> None:
    pattern = PatternBuilder(rows=1, channels=1)
    pattern.place(0, 0, Cell(note=PRESSED_KEY))
    song = _song(
        samples=(_sample(),), instruments=(Instrument(name="voice", keymap=pitched_keymap(sample=0)),), pattern=pattern
    )

    events = resolve_note_events(song, module_id=MODULE_ID, catalogued_slots=CATALOGUED_SLOTS)

    assert len(events) == 1
    assert events[0].note == PRESSED_KEY
    assert events[0].instrument_index is None
    assert events[0].sounded_note is None
    assert events[0].sample_slot is None


def test_a_key_reaching_an_occurrence_the_catalog_lacks_keeps_its_note_without_a_slot() -> None:
    """The catalog leaves out a slot it holds no occurrence for -- a too-short sample, say -- and a
    key routed onto one still records the note it sounds."""
    pattern = PatternBuilder(rows=1, channels=1)
    pattern.place(0, 0, Cell(note=PRESSED_KEY, instrument=0))
    song = _song(
        samples=(_sample(),),
        instruments=(Instrument(name="voice", keymap=pitched_keymap(sample=0)),),
        pattern=pattern,
    )

    events = resolve_note_events(song, module_id=MODULE_ID, catalogued_slots=frozenset())

    assert events[0].sounded_note == PRESSED_KEY
    assert events[0].sample_slot is None


def test_a_key_the_keymap_leaves_silent_resolves_to_neither_a_note_nor_a_slot() -> None:
    pattern = PatternBuilder(rows=1, channels=1)
    pattern.place(0, 0, Cell(note=PRESSED_KEY, instrument=0))
    keymap = routed_keymap({SILENT_ALTERNATIVE_KEY: KeyAssignment(sample=0, note=SILENT_ALTERNATIVE_KEY)})
    song = _song(samples=(_sample(),), instruments=(Instrument(name="voice", keymap=keymap),), pattern=pattern)

    events = resolve_note_events(song, module_id=MODULE_ID, catalogued_slots=CATALOGUED_SLOTS)

    assert events[0].sounded_note is None
    assert events[0].sample_slot is None


def test_a_slot_is_numbered_within_its_instrument_rather_than_by_the_song_s_sample_table() -> None:
    """A keymap indexes the song's whole sample table; an occurrence is numbered inside its instrument.

    The slots follow the order the keys first reach a sample, walking the keymap from the lowest key
    up, so the key pressed here reaches the song's third sample and the instrument's second slot.
    """
    pattern = PatternBuilder(rows=1, channels=1)
    pattern.place(0, 0, Cell(note=PRESSED_KEY, instrument=0))
    keymap = routed_keymap(
        {
            SILENT_ALTERNATIVE_KEY: KeyAssignment(sample=1, note=SILENT_ALTERNATIVE_KEY),
            PRESSED_KEY: KeyAssignment(sample=2, note=PRESSED_KEY),
        }
    )
    song = _song(
        samples=(_sample(name="unreached"), _sample(name="lower key"), _sample(name="pressed key")),
        instruments=(Instrument(name="voice", keymap=keymap),),
        pattern=pattern,
    )

    events = resolve_note_events(song, module_id=MODULE_ID, catalogued_slots=CATALOGUED_SLOTS)

    assert events[0].sample_slot == 1


def test_every_grid_position_holding_a_key_becomes_its_own_event() -> None:
    pattern = PatternBuilder(rows=4, channels=2)
    pattern.place(0, 0, Cell(note=PRESSED_KEY, instrument=0))
    pattern.place(3, 1, Cell(note=Note(50), instrument=0))
    song = _song(
        samples=(_sample(),), instruments=(Instrument(name="voice", keymap=pitched_keymap(sample=0)),), pattern=pattern
    )

    events = resolve_note_events(song, module_id=MODULE_ID, catalogued_slots=CATALOGUED_SLOTS)

    assert {(event.row_index, event.channel_index) for event in events} == {(0, 0), (3, 1)}


def test_a_pattern_holding_no_keys_yields_no_events() -> None:
    song = _song(
        samples=(_sample(),),
        instruments=(Instrument(name="voice", keymap=pitched_keymap(sample=0)),),
        pattern=PatternBuilder(rows=4, channels=1),
    )

    assert resolve_note_events(song, module_id=MODULE_ID, catalogued_slots=CATALOGUED_SLOTS) == ()


def test_a_sample_addressed_module_still_reports_an_instrument_slot_per_sample(
    mod_module_bytes: bytes,
) -> None:
    """Raising a sample table to instruments is what keeps every format addressed the same way."""
    song = parse_module(mod_module_bytes, tracker=TrackerFormat.MOD)
    assert isinstance(song.voices, SampleVoices)

    instruments = resolve_module_instruments(song, module_id=MODULE_ID)

    assert len(instruments) == len(song.voices.samples)
    assert instruments[0].instrument_index == 0


def test_module_instruments_carry_the_name_the_voice_was_given(xm_module_bytes: bytes) -> None:
    song = parse_module(xm_module_bytes, tracker=TrackerFormat.XM)

    instruments = resolve_module_instruments(song, module_id=MODULE_ID)

    assert [instrument.name for instrument in instruments] == ["voice"]
