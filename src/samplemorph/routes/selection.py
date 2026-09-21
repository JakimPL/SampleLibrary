from __future__ import annotations

from enum import StrEnum, unique
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ValidationError

from samplecore.models.base import FROZEN
from samplemorph.envelope.settings import EnvelopeSettings

DEFAULT_SELECTION_PATH: Final[Path] = Path(__file__).resolve().parents[3] / "morph.yaml"


@unique
class Glide(StrEnum):
    """The pitch reader an envelope route carries its excitation between the two sounds' pitches by."""

    SUBHARMONIC = "subharmonic"


class RouteSelection(BaseModel):
    """How one process renders a morph: the settings of the envelope route, and the glide it carries its excitation by.

    `envelope` says how the envelope is drawn, whose excitation sounds under it and whose course
    through time the path is heard on. `glide` names the pitch reader the excitation moves between
    the two sounds' pitches by; left out, the excitation holds its own pitch. A YAML file holds one
    selection, so what the application serves is stated in one place and changed there.
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
