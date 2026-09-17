from __future__ import annotations

from pathlib import Path

import pytest

from samplemorph.envelope.settings import EnvelopeSettings, Excitation
from samplemorph.pipeline import RouteChoice
from samplemorph.routes.kinds import RouteKind
from samplemorph.routes.selection import read_route_selection

FULL_SELECTION = """
route: envelope
envelope:
  excitation: both
  coefficient_count: 12
partials:
  profile: stepped
latent:
  model_name: pca
  vocoder_name: pghi
  restorer_name: restorer
  morpher_name: linear
  device: cpu
"""


def _written(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "morph.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_file_names_the_route_and_the_settings_each_kind_reads(tmp_path: Path) -> None:
    selection = read_route_selection(_written(tmp_path, FULL_SELECTION))

    assert selection.route is RouteKind.ENVELOPE
    assert selection.envelope == EnvelopeSettings(excitation=Excitation.BOTH, coefficient_count=12)
    assert selection.partials.profile == "stepped"
    assert selection.latent == RouteChoice(
        model_name="pca", vocoder_name="pghi", restorer_name="restorer", morpher_name="linear", device="cpu"
    )


def test_a_file_naming_the_route_alone_leaves_every_kind_its_own_settings(tmp_path: Path) -> None:
    selection = read_route_selection(_written(tmp_path, "route: transport\n"))

    assert selection.route is RouteKind.TRANSPORT
    assert selection.envelope == EnvelopeSettings()


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "dictionary"),
        ("route: elsewhere\n", "elsewhere"),
        ("route: envelope\nenvelope:\n  excitaton: both\n", "excitaton"),
        ("route: envelope\nenvelope:\n  excitation: neither\n", "neither"),
        ("route: envelope\nenvelope:\n  timeline: nowhere\n", "nowhere"),
        ("route: partials\npartials:\n  profile: nowhere\n", "must be one of"),
        ("route: latent\nlatent:\n  model_name: pca\n", "vocoder_name"),
        ("route: [\n", "holds no route selection"),
    ],
    ids=(
        "an empty file",
        "a route this pipeline lacks",
        "a setting misspelled",
        "an excitation this route lacks",
        "a course this route lacks",
        "a profile this route lacks",
        "a latent choice left incomplete",
        "text that is no YAML",
    ),
)
def test_a_file_this_process_cannot_serve_is_refused_naming_the_reason(tmp_path: Path, text: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        read_route_selection(_written(tmp_path, text))


def test_an_absent_file_is_refused_by_its_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absent.yaml"):
        read_route_selection(tmp_path / "absent.yaml")
