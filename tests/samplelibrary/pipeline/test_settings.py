from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

from samplecloud.evaluation.cli import parse_arguments as parse_evaluation_arguments
from samplecloud.suggestions.cli import parse_arguments as parse_suggestion_arguments
from samplecore.config import ConfigurationError
from samplelibrary.pipeline.settings import OPERATIONAL_STEP_SETTINGS, StepSettings, read_pipeline_settings
from samplelibrary.pipeline.steps.descriptor import DESCRIPTOR, EVALUATION, GRID_CACHE, MODULE_EVALUATION
from samplelibrary.pipeline.steps.library import settings_model
from samplelibrary.pipeline.steps.listening import SUGGESTIONS
from samplelibrary.pipeline.steps.morph import MORPH_CODEC, RESTORER
from samplemorph.cli import parse_arguments as parse_morph_arguments

LIBRARY_TABLE = """
[library]
module_source_directory = "{root}"
library_root = "{root}"
database_url = "postgresql+psycopg://user:pass@localhost:5432/library"
"""
PROGRAM: Final[str] = "samplelibrary"
UNASKED_COMMANDS: Final[dict[str, Callable[[], argparse.Namespace]]] = {
    SUGGESTIONS: lambda: parse_suggestion_arguments(["--experiment-id", "1"], prog=PROGRAM),
    GRID_CACHE: lambda: parse_morph_arguments(["cache-grids"], prog=PROGRAM),
    DESCRIPTOR: lambda: parse_morph_arguments(["train-descriptor", "--teacher-experiment", "1"], prog=PROGRAM),
    EVALUATION: lambda: parse_evaluation_arguments(["--experiment-id", "1"], prog=PROGRAM),
    MODULE_EVALUATION: lambda: parse_evaluation_arguments(["--experiment-id", "1"], prog=PROGRAM),
    MORPH_CODEC: lambda: parse_morph_arguments(["fit"], prog=PROGRAM),
    RESTORER: lambda: parse_morph_arguments(["train-restorer"], prog=PROGRAM),
}


def _config(tmp_path: Path, pipeline_table: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(LIBRARY_TABLE.format(root=tmp_path.as_posix()) + pipeline_table, encoding="utf-8")
    return path


def test_a_configuration_naming_no_pipeline_reads_as_the_defaults(tmp_path: Path) -> None:
    settings = read_pipeline_settings(_config(tmp_path, ""))

    assert settings.workers is None
    assert settings.labels is None
    assert not settings.ceiling.enforced


def test_the_pipeline_table_reads_its_limits_and_a_table_per_step(tmp_path: Path) -> None:
    settings = read_pipeline_settings(
        _config(
            tmp_path,
            '[pipeline]\nmemory_cap = "16G"\ndevice = "cpu"\nworkers = 4\nlabels = "labels.jsonl"\n'
            '[pipeline.descriptor]\nepochs = 2\nmemory_cap = "24G"\n',
        )
    )

    assert (settings.device, settings.workers) == ("cpu", 4)
    assert settings.labels == Path("labels.jsonl")
    assert str(settings.ceiling) == "16G"
    assert str(settings.ceiling_for("descriptor")) == "24G"
    assert str(settings.ceiling_for("modules")) == "16G"
    assert settings.table_for("descriptor") == {"epochs": 2, "memory_cap": "24G"}


@pytest.mark.parametrize(
    ("table", "reason"),
    [
        ('[pipeline]\nmemory_ceiling = "16G"\n', "memory_ceiling"),
        ('[pipeline]\nmemory_cap = "16 gigabytes"\n', "memory ceiling reads"),
        ("[pipeline]\nworkers = 0\n", "workers"),
        ('[pipeline.descriptor]\nmemory_cap = "plenty"\n', "memory ceiling reads"),
    ],
    ids=("an unknown setting", "a ceiling written another way", "a count below one", "a step's own ceiling"),
)
def test_a_pipeline_table_this_project_does_not_read_is_refused(tmp_path: Path, table: str, reason: str) -> None:
    with pytest.raises(ConfigurationError, match=reason):
        read_pipeline_settings(_config(tmp_path, table))


class TrainingSettings(StepSettings):
    """A step's settings the way a training step declares them, for reading tables against."""

    epochs: int = 40
    learning_rate: float = 0.001
    weights: dict[str, float] = {"labels": 1.0, "retuning": 0.5}


def _parameters(tmp_path: Path, table: str) -> str:
    settings = read_pipeline_settings(_config(tmp_path, f"[pipeline.descriptor]\n{table}"))
    return settings.settings_for("descriptor", TrainingSettings).parameters_digest


@pytest.mark.parametrize(
    "table",
    [
        "epochs = 40\n",
        "learning_rate = 1e-3\n",
        "weights = { retuning = 0.5, labels = 1 }\n",
        'memory_cap = "24G"\n',
    ],
    ids=("a default written out", "a value written another way", "keys in another order", "a ceiling"),
)
def test_parameters_read_the_same_however_the_table_writes_them(tmp_path: Path, table: str) -> None:
    assert _parameters(tmp_path, table) == _parameters(tmp_path, "")


def test_a_parameter_that_differs_names_other_outputs(tmp_path: Path) -> None:
    assert _parameters(tmp_path, "epochs = 41\n") != _parameters(tmp_path, "")


def test_a_step_table_holding_a_setting_its_step_does_not_read_is_refused(tmp_path: Path) -> None:
    settings = read_pipeline_settings(_config(tmp_path, "[pipeline.descriptor]\nepoch = 40\n"))

    with pytest.raises(ConfigurationError, match="epoch"):
        settings.settings_for("descriptor", TrainingSettings)


@pytest.mark.parametrize("step", UNASKED_COMMANDS)
def test_a_step_left_at_its_defaults_asks_what_its_command_does_unasked(step: str) -> None:
    defaults = settings_model(step)().model_dump(exclude=set(OPERATIONAL_STEP_SETTINGS))
    unasked = vars(UNASKED_COMMANDS[step]())

    assert {name: unasked[name] for name in defaults} == defaults
