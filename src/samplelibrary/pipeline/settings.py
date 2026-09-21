from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from samplecore.config import PIPELINE_TABLE, ConfigurationError, resolve_config_path
from samplecore.digests import digest_of_rows
from samplelibrary.limits.ceiling import MalformedCeiling, MemoryCeiling

DEFAULT_MEMORY_CAP: Final[str] = "none"
OPERATIONAL_STEP_SETTINGS: Final[set[str]] = {"memory_cap"}
DEFAULT_DEVICE: Final[str] = "cuda"


class StepSettings(BaseModel):
    """What one step's own table says: the ceiling the step runs under, and the parameters its outputs are named from.

    A step taking parameters reads them through a model of its own built on this one, each field
    defaulting to its command's own default, so a table writing a default out names the same outputs
    as one leaving it out.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_cap: str | None = None

    @property
    def parameters_digest(self) -> str:
        """One digest over the parameters as read, which a step's outputs are named from and the ceiling stays out of."""
        values = self.model_dump(mode="json", exclude=OPERATIONAL_STEP_SETTINGS)
        return digest_of_rows((name, json.dumps(values[name], sort_keys=True)) for name in sorted(values))


class PipelineSettings(BaseModel):
    """What the `[pipeline]` table says: the machine's own limits, and a table per step that takes parameters.

    `memory_cap` and `device` are facts about this machine rather than about the library, so they
    stay out of what a step's outputs are named from. `labels` names the file a fresh catalog reads
    its hand labels from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_cap: str = DEFAULT_MEMORY_CAP
    device: str = DEFAULT_DEVICE
    workers: int | None = Field(default=None, ge=1)
    labels: Path | None = None
    steps: Mapping[str, Mapping[str, Any]] = Field(default_factory=dict)

    @property
    def ceiling(self) -> MemoryCeiling:
        """The ceiling every step runs under unless its own table names another.

        Raises:
            MalformedCeiling: the ceiling is written some other way than this project reads.
        """
        return MemoryCeiling.parse(self.memory_cap)

    def ceiling_for(self, step: str) -> MemoryCeiling:
        """The ceiling one step runs under.

        Raises:
            MalformedCeiling: the ceiling is written some other way than this project reads.
        """
        named = self.steps.get(step, {}).get("memory_cap")
        return MemoryCeiling.parse(named) if isinstance(named, str) else self.ceiling

    def table_for(self, step: str) -> Mapping[str, Any]:
        """What the configuration says about one step, which that step validates as its own settings."""
        return self.steps.get(step, {})

    def settings_for[Settings: StepSettings](self, step: str, model: type[Settings]) -> Settings:
        """One step's table read as the settings that step takes.

        Raises:
            ConfigurationError: the table names a setting the step does not take, or a value written
                some other way than the step reads it.
        """
        try:
            return model.model_validate(self.table_for(step))
        except ValidationError as error:
            first = error.errors()[0]
            location = ".".join(str(part) for part in first["loc"])
            raise ConfigurationError(f"[{PIPELINE_TABLE}.{step}] {location}: {first['msg']}") from error


def read_pipeline_settings(path: Path | None = None) -> PipelineSettings:
    """The `[pipeline]` table of the configuration a command reads, or the defaults where it names none.

    Raises:
        ConfigurationError: the file cannot be read, the table holds a setting this project does not
            read, or a value is written some other way than this project reads it.
    """
    config_path = resolve_config_path(path)
    try:
        with config_path.open("rb") as file:
            document = tomllib.load(file)
    except OSError as error:
        raise ConfigurationError(f"{config_path} cannot be read ({error.strerror})") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"{config_path} is not valid TOML: {error}") from error

    table = document.get(PIPELINE_TABLE, {})
    if not isinstance(table, dict):
        raise ConfigurationError(f"[{PIPELINE_TABLE}] in {config_path} holds a value where a table belongs")
    scalars = {name: value for name, value in table.items() if not isinstance(value, dict)}
    steps = {name: value for name, value in table.items() if isinstance(value, dict)}
    try:
        settings = PipelineSettings(**scalars, steps=steps)
        _require_readable_ceilings(settings, steps)
    except ValidationError as error:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or PIPELINE_TABLE
        raise ConfigurationError(f"[{PIPELINE_TABLE}] in {config_path}: {location}: {first['msg']}") from error
    except MalformedCeiling as error:
        raise ConfigurationError(f"[{PIPELINE_TABLE}] in {config_path}: {error}") from error
    return settings


def _require_readable_ceilings(settings: PipelineSettings, steps: Mapping[str, Mapping[str, Any]]) -> None:
    """Read every ceiling the table names, so one written another way is refused before a run starts.

    Raises:
        MalformedCeiling: a ceiling is written some other way than this project reads.
    """
    for step in ("", *steps):
        settings.ceiling_for(step)
