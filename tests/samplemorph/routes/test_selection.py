from __future__ import annotations

from pathlib import Path

import pytest

from samplemorph.envelope.settings import EnvelopeSettings, Excitation
from samplemorph.routes.selection import DEFAULT_SELECTION_PATH, Glide, read_route_selection

FULL_SELECTION = """
envelope:
  excitation: both
  coefficient_count: 12
glide: subharmonic
"""


def _written(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "morph.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_file_names_the_envelope_settings_and_the_glide(tmp_path: Path) -> None:
    selection = read_route_selection(_written(tmp_path, FULL_SELECTION))

    assert selection.envelope == EnvelopeSettings(excitation=Excitation.BOTH, coefficient_count=12)
    assert selection.glide is Glide.SUBHARMONIC


def test_a_file_naming_no_glide_holds_the_excitation_at_its_own_pitch(tmp_path: Path) -> None:
    selection = read_route_selection(_written(tmp_path, "envelope:\n  excitation: first\n"))

    assert selection.envelope == EnvelopeSettings(excitation=Excitation.FIRST)
    assert selection.glide is None


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "dictionary"),
        ("envelope:\n  excitaton: both\n", "excitaton"),
        ("envelope:\n  excitation: neither\n", "neither"),
        ("envelope:\n  timeline: nowhere\n", "nowhere"),
        ("glide: nobody\n", "nobody"),
        ("route: envelope\n", "route"),
        ("envelope: [\n", "holds no route selection"),
    ],
    ids=(
        "an empty file",
        "a setting misspelled",
        "an excitation this route lacks",
        "a course this route lacks",
        "a pitch reader this route lacks",
        "a route key this pipeline no longer reads",
        "text that is no YAML",
    ),
)
def test_a_file_this_process_cannot_serve_is_refused_naming_the_reason(tmp_path: Path, text: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        read_route_selection(_written(tmp_path, text))


def test_an_absent_file_is_refused_by_its_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absent.yaml"):
        read_route_selection(tmp_path / "absent.yaml")


def test_the_committed_filter_selection_is_one_a_response_can_answer() -> None:
    """The file exists so a VST's filter has a selection to be read under while the renderer glides.

    A response is the envelope route's filter, and it holds for a path whose harmonics stand where
    they stood, so this property is what the file is for rather than a default it happens to carry.
    """
    selection = read_route_selection(DEFAULT_SELECTION_PATH.with_name("morph-filter.yaml"))

    assert selection.glide is None
