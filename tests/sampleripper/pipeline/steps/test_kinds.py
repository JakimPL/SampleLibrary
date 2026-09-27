from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from sampleripper.pipeline.context import PipelineContext
from sampleripper.pipeline.layout import PipelineLayout
from sampleripper.pipeline.results import StepAction
from sampleripper.pipeline.settings import PipelineSettings
from sampleripper.pipeline.steps.kinds import SAMPLES_TO_DESCRIBE, DerivedExperimentStep, MissingOutput

KEY = "derived-test"


@pytest.fixture
def context(tmp_path: Path, connection: Connection) -> PipelineContext:
    library_root = tmp_path / "library"
    return PipelineContext(
        config=LibraryConfig(library_root=library_root),
        settings=PipelineSettings(),
        connection=connection,
        layout=PipelineLayout(library_root=library_root),
    )


@dataclass
class Filling:
    """Whether the experiment a derived step files holds everything its inputs name."""

    complete: bool

    def __call__(self, context: PipelineContext, experiment_id: int) -> bool:
        return self.complete


def _step(filling: Filling) -> DerivedExperimentStep:
    return DerivedExperimentStep(
        name="derived",
        requires=(),
        inputs=lambda context: {},
        key=lambda context, digest: KEY,
        command=lambda context, key: ("fill", key),
        complete=filling,
    )


def _filed(connection: Connection) -> None:
    with start_batch(connection):
        PostgresExperimentRepository(connection).insert_new(backend_name="learned", label=None, params={}, key=KEY)


def test_an_experiment_a_stopped_run_left_part_filled_runs_again_and_is_refused_sealing(
    context: PipelineContext, connection: Connection
) -> None:
    _filed(connection)
    step = _step(Filling(complete=False))

    plan = step.evaluate(context)

    assert plan.action is StepAction.RUN
    assert plan.reasons == frozenset({SAMPLES_TO_DESCRIBE})
    with pytest.raises(MissingOutput, match="part-filled"):
        step.seal(context, plan)


def test_a_filled_experiment_stands(context: PipelineContext, connection: Connection) -> None:
    _filed(connection)

    assert _step(Filling(complete=True)).evaluate(context).action is StepAction.SKIP
