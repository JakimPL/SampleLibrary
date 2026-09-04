from __future__ import annotations

import pytest

from samplecore.models.tracker import TrackerFormat
from sampleextract.parsing import parse_module


def test_parse_module_reads_an_xm_file_back_to_its_song(xm_module_bytes: bytes) -> None:
    song = parse_module(xm_module_bytes, tracker=TrackerFormat.XM)

    assert song.name == "probe"
    assert len(song.instruments) == 1
    assert len(song.samples) == 1
    assert song.samples[0].name == "lead"


def test_parse_module_reads_an_it_file_back_to_its_song(it_module_bytes: bytes) -> None:
    song = parse_module(it_module_bytes, tracker=TrackerFormat.IT)

    assert song.name == "probe"
    assert len(song.instruments) == 1
    assert len(song.samples) == 1
    assert song.samples[0].name == "kick"


def test_parse_module_rejects_bytes_without_the_xm_tag() -> None:
    with pytest.raises(ValueError):
        parse_module(b"not a module", tracker=TrackerFormat.XM)


def test_parse_module_rejects_bytes_without_the_it_tag() -> None:
    with pytest.raises(ValueError):
        parse_module(b"not a module", tracker=TrackerFormat.IT)
