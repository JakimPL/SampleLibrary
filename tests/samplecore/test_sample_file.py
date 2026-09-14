from __future__ import annotations

from pathlib import Path

import pydantic
import pytest

from samplecore.models.sample_file import SampleFileLocation

DIRECTORY = Path("/samples/packs")


def test_a_location_names_the_file_its_stem_and_its_folders_nearest_first() -> None:
    location = SampleFileLocation(directory=DIRECTORY, relative_path="Club Sounds/Kicks/Kick 01.wav")

    assert location.path == DIRECTORY / "Club Sounds" / "Kicks" / "Kick 01.wav"
    assert location.stem == "Kick 01"
    assert location.folder_names == ("Kicks", "Club Sounds")


@pytest.mark.parametrize(
    "relative_path",
    ["", "/kick.wav", "../kick.wav", "drums/../kick.wav", "drums//kick.wav", "./kick.wav", "drums\\kick.wav"],
    ids=("empty", "absolute", "above the directory", "climbing back", "a doubled slash", "a dot", "a backslash"),
)
def test_a_location_outside_or_loosely_below_its_directory_is_refused(relative_path: str) -> None:
    with pytest.raises(pydantic.ValidationError, match="below its directory"):
        SampleFileLocation(directory=DIRECTORY, relative_path=relative_path)


def test_a_location_needs_an_absolute_directory() -> None:
    with pytest.raises(pydantic.ValidationError, match="absolute"):
        SampleFileLocation(directory=Path("packs"), relative_path="kick.wav")
