from __future__ import annotations

from enum import StrEnum, unique
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ValidationError

from samplecore.models.base import FROZEN
from samplemorph.envelope.settings import EnvelopeSettings

DEFAULT_SELECTION_PATH: Final[Path] = Path(__file__).resolve().parent / "selections" / "morph.yaml"
DEFAULT_FILTER_SELECTION_PATH: Final[Path] = DEFAULT_SELECTION_PATH.with_name("morph-filter.yaml")


@unique
class Glide(StrEnum):
    """The pitch reader an envelope route carries its excitation between the two sounds' pitches by."""

    SUBHARMONIC = "subharmonic"


class RouteSelection(BaseModel):
    """How one process renders a morph: the settings of the envelope route, and the glide it carries its excitation by.

    `envelope` says how the envelope is drawn, whose excitation sounds under it and whose course
    through time the path is heard on. `glide` names the pitch reader the excitation moves between
    the two sounds' pitches by; left out, the excitation holds its own pitch. A YAML file holds one
    selection, so what a process reads is stated in one place and changed there: `morph.yaml` names
    the morph the renderer plays, and `morph-filter.yaml` beside it the one a filter is read under.
    """

    model_config = FROZEN

    envelope: EnvelopeSettings = EnvelopeSettings()
    glide: Glide | None = None


def read_route_selection(path: Path) -> RouteSelection:
    """The selection a YAML file holds.

    Raises:
        ValueError: the file cannot be read, holds no YAML, or names a setting this pipeline has none of.
    """
    try:
        return RouteSelection.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"{path} holds no route selection to serve ({error})") from error


def read_filter_selection(path: Path) -> RouteSelection:
    """The selection a YAML file holds, read as the one a morph filter is built under.

    A filter is the envelope route held to one sound, whose harmonics stand where they stood along
    the whole path, so the file it is read under holds every pitch.

    Raises:
        ValueError: the file cannot be read, holds no YAML, names a setting this pipeline has none of,
            or names a glide.
    """
    selection = read_route_selection(path)
    if selection.glide is not None:
        raise ValueError(f"{path} glides by {selection.glide}, and a filter holds only where the harmonics stay put")
    return selection
