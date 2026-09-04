from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from samplecore.models.module import Module
from samplecore.models.tracker import TrackerFormat


def _module(module_hash: str, filename: str) -> Module:
    return Module(
        hash=module_hash,
        id=0,
        filename=filename,
        tracker=TrackerFormat.IT,
        title="untitled",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )


def test_a_plain_filename_is_accepted(module_hash_a: str) -> None:
    module = _module(module_hash_a, "song.it")

    assert module.filename == "song.it"


@pytest.mark.parametrize("filename", ["dir/song.it", "dir\\song.it", "/song.it"])
def test_a_filename_with_a_path_separator_is_rejected(module_hash_a: str, filename: str) -> None:
    with pytest.raises(ValidationError):
        _module(module_hash_a, filename)
