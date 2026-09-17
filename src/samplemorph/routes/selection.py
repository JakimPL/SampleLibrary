from __future__ import annotations

from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ValidationError, field_validator

from samplecore.models.base import FROZEN
from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.model_paths import DEFAULT_RESTORER_NAME
from samplemorph.model_store import DEFAULT_MODEL_NAME
from samplemorph.partials.presets import DEFAULT_PROFILE_NAME, PROFILE_PRESETS
from samplemorph.pipeline import RouteChoice
from samplemorph.registries import DEFAULT_MORPHER_NAME, DEFAULT_VOCODER_NAME
from samplemorph.routes.kinds import RouteKind

DEFAULT_SELECTION_PATH: Final[Path] = Path(__file__).resolve().parents[3] / "morph.yaml"
PROCESSOR: Final[str] = "cpu"
DEFAULT_LATENT_CHOICE: Final[RouteChoice] = RouteChoice(
    model_name=DEFAULT_MODEL_NAME,
    vocoder_name=DEFAULT_VOCODER_NAME,
    restorer_name=DEFAULT_RESTORER_NAME,
    morpher_name=DEFAULT_MORPHER_NAME,
    device=PROCESSOR,
)


class PartialsSelection(BaseModel):
    """Which middle the partials route takes, by the name of one of its profile presets."""

    model_config = FROZEN

    profile: str = DEFAULT_PROFILE_NAME

    @field_validator("profile")
    @classmethod
    def _names_a_preset(cls, profile: str) -> str:
        if profile not in PROFILE_PRESETS:
            raise ValueError(f"must be one of {', '.join(PROFILE_PRESETS)}")
        return profile


class RouteSelection(BaseModel):
    """Which route one process renders through, with the settings each kind reads.

    The envelope route reads `envelope`, the partials route the profile `partials` names, and the
    latent route the stored model, vocoder, restorer, morpher and device `latent` names; the
    transport and the blend read their default settings alone. A YAML file holds one selection, so
    what the application serves is stated in one place and changed there.
    """

    model_config = FROZEN

    route: RouteKind
    envelope: EnvelopeSettings = EnvelopeSettings()
    partials: PartialsSelection = PartialsSelection()
    latent: RouteChoice = DEFAULT_LATENT_CHOICE


def read_route_selection(path: Path) -> RouteSelection:
    """The selection a YAML file holds.

    Raises:
        ValueError: the file cannot be read, holds no YAML, or names a route, a preset or a setting
            this pipeline has none of.
    """
    try:
        return RouteSelection.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"{path} holds no route selection to serve ({error})") from error
