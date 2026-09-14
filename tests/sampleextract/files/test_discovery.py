from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from sampleextract.files.discovery import discover_sample_files, is_excluded
from tests.sampleextract.files.conftest import SamplePack


def _relative_paths(directory: Path, exclusions: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        location.relative_path for location in discover_sample_files((directory,), exclusions=exclusions).locations
    )


def test_every_visible_file_in_a_decoded_format_is_listed_in_location_order(sample_pack: SamplePack) -> None:
    assert _relative_paths(sample_pack.directory, ()) == (
        "Kicks/Click.wav",
        "Kicks/Kick 01.wav",
        "Kicks/Kick 02.flac",
        "LOOPS/Loop 01.wav",
    )


def test_an_excluded_folder_is_left_out_whatever_case_it_is_spelled_in(sample_pack: SamplePack) -> None:
    assert _relative_paths(sample_pack.directory, ("*loops*", "*.flac")) == ("Kicks/Click.wav", "Kicks/Kick 01.wav")


def test_a_missing_directory_is_named_and_the_others_are_still_listed(sample_pack: SamplePack, tmp_path: Path) -> None:
    unplugged = tmp_path / "unplugged"

    discovery = discover_sample_files((unplugged, sample_pack.directory), exclusions=())

    assert discovery.missing_directories == (unplugged,)
    assert len(discovery.locations) == 4


def test_a_folder_linked_back_up_the_tree_is_walked_once(sample_pack: SamplePack) -> None:
    (sample_pack.directory / "Kicks" / "back up").symlink_to(sample_pack.directory, target_is_directory=True)

    assert len(_relative_paths(sample_pack.directory, ())) == 4


@dataclass(frozen=True)
class ExclusionCase:
    relative_path: str
    pattern: str
    excluded: bool


@pytest.mark.parametrize(
    "case",
    [
        ExclusionCase(relative_path="VEH1 Loops/Loop 01.wav", pattern="*loop*", excluded=True),
        ExclusionCase(relative_path="VEH1 Loops", pattern="*loop*", excluded=True),
        ExclusionCase(relative_path="Kicks/Kick 01.wav", pattern="*loop*", excluded=False),
        ExclusionCase(relative_path="Kicks/Kick 01.AIF", pattern="*.aif", excluded=True),
        ExclusionCase(relative_path="Kicks/Kick 01.wav", pattern="loops/*", excluded=False),
    ],
    ids=("a file inside a named folder", "the folder itself", "a file elsewhere", "a suffix", "an anchored folder"),
)
def test_an_exclusion_matches_a_relative_path_as_a_shell_pattern_regardless_of_case(case: ExclusionCase) -> None:
    assert is_excluded(case.relative_path, exclusions=(case.pattern,)) is case.excluded
