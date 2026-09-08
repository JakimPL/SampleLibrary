from __future__ import annotations

import pytest
from trackmod.core.voices.voices import InstrumentVoices, SampleVoices

from samplecore.models.tracker import TrackerFormat
from sampleextract.parsing import parse_module


def test_parse_module_reads_an_xm_file_back_to_its_song(xm_module_bytes: bytes) -> None:
    song = parse_module(xm_module_bytes, tracker=TrackerFormat.XM)

    assert song.name == "probe"
    assert isinstance(song.voices, InstrumentVoices)
    assert len(song.voices.instruments) == 1
    assert len(song.voices.samples) == 1
    assert song.voices.samples[0].name == "lead"


def test_parse_module_reads_an_it_file_back_to_its_song(it_module_bytes: bytes) -> None:
    song = parse_module(it_module_bytes, tracker=TrackerFormat.IT)

    assert song.name == "probe"
    assert isinstance(song.voices, InstrumentVoices)
    assert len(song.voices.instruments) == 1
    assert len(song.voices.samples) == 1
    assert song.voices.samples[0].name == "kick"


def test_parse_module_reads_a_mod_file_back_to_its_song(mod_module_bytes: bytes) -> None:
    song = parse_module(mod_module_bytes, tracker=TrackerFormat.MOD)

    assert song.name == "probe"
    assert isinstance(song.voices, SampleVoices)
    assert len(song.voices.samples) == 1
    assert song.voices.samples[0].name == "chip"


def test_parse_module_reads_an_s3m_file_back_to_its_song(s3m_module_bytes: bytes) -> None:
    song = parse_module(s3m_module_bytes, tracker=TrackerFormat.S3M)

    assert song.name == "probe"
    assert isinstance(song.voices, SampleVoices)
    assert len(song.voices.samples) == 1
    assert song.voices.samples[0].name == "pluck"


def test_parse_module_rejects_bytes_without_the_xm_tag() -> None:
    with pytest.raises(ValueError):
        parse_module(b"not a module", tracker=TrackerFormat.XM)


def test_parse_module_rejects_bytes_without_the_it_tag() -> None:
    with pytest.raises(ValueError):
        parse_module(b"not a module", tracker=TrackerFormat.IT)


def test_parse_module_rejects_bytes_without_the_mod_tag() -> None:
    with pytest.raises(ValueError):
        parse_module(b"not a module", tracker=TrackerFormat.MOD)


def test_parse_module_rejects_bytes_without_the_s3m_tag() -> None:
    with pytest.raises(ValueError):
        parse_module(b"not a module", tracker=TrackerFormat.S3M)
