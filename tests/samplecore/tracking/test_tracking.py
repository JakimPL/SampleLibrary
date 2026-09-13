from __future__ import annotations

from pathlib import Path

import pytest
from mlflow.entities import RunStatus
from mlflow.tracking import MlflowClient

from samplecore.tracking import TrackedRun
from samplecore.tracking.mlflow_run import tracked_run
from samplecore.tracking.silent import SilentRun
from samplecore.tracking.store import artifact_root, tracking_uri

EXPERIMENT_NAME = "tests"
RUN_NAME = "one pass"


def _client(library_root: Path) -> MlflowClient:
    return MlflowClient(tracking_uri=tracking_uri(library_root))


def test_a_silent_run_is_a_tracked_run() -> None:
    run: TrackedRun = SilentRun()

    run.log_parameters({"epochs": "2"})
    run.log_metrics({"loss": 1.0}, step=0)

    assert run.run_id


def test_an_mlflow_run_is_a_tracked_run(tmp_path: Path) -> None:
    with tracked_run(tmp_path, experiment_name=EXPERIMENT_NAME, run_name=RUN_NAME) as run:
        opened: TrackedRun = run

        assert opened.run_id


def test_a_run_keeps_the_parameters_and_metrics_it_was_given(tmp_path: Path) -> None:
    with tracked_run(tmp_path, experiment_name=EXPERIMENT_NAME, run_name=RUN_NAME) as run:
        run.log_parameters({"epochs": "2", "canonicalizer": "log_frequency"})
        run.log_metrics({"validation/loss": 1.25}, step=0)
        run.log_metrics({"validation/loss": 1.10}, step=1)
        run_id = run.run_id

    recorded = _client(tmp_path).get_run(run_id)

    assert recorded.data.params == {"epochs": "2", "canonicalizer": "log_frequency"}
    assert recorded.data.metrics["validation/loss"] == pytest.approx(1.10)


def test_a_run_that_finishes_is_recorded_apart_from_one_that_raises(tmp_path: Path) -> None:
    with tracked_run(tmp_path, experiment_name=EXPERIMENT_NAME, run_name=RUN_NAME) as finished:
        finished_id = finished.run_id

    with pytest.raises(ValueError):
        with tracked_run(tmp_path, experiment_name=EXPERIMENT_NAME, run_name=RUN_NAME) as failed:
            failed_id = failed.run_id
            raise ValueError("the pass gave up")

    client = _client(tmp_path)

    assert client.get_run(finished_id).info.status == RunStatus.to_string(RunStatus.FINISHED)
    assert client.get_run(failed_id).info.status == RunStatus.to_string(RunStatus.FAILED)


def test_runs_of_one_name_are_grouped_under_a_single_experiment(tmp_path: Path) -> None:
    with tracked_run(tmp_path, experiment_name=EXPERIMENT_NAME, run_name=RUN_NAME) as first:
        first_id = first.run_id
    with tracked_run(tmp_path, experiment_name=EXPERIMENT_NAME, run_name=RUN_NAME) as second:
        second_id = second.run_id

    client = _client(tmp_path)

    assert client.get_run(first_id).info.experiment_id == client.get_run(second_id).info.experiment_id


def test_a_run_stores_the_files_it_produced_under_the_library_root(tmp_path: Path) -> None:
    """A run's files belong beside the library, since the working directory is the repository."""
    produced = tmp_path / "weights.pt"
    produced.write_bytes(b"weights")

    with tracked_run(tmp_path, experiment_name=EXPERIMENT_NAME, run_name=RUN_NAME) as run:
        run.log_artifact(produced)
        run_id = run.run_id

    stored = [artifact.path for artifact in _client(tmp_path).list_artifacts(run_id)]

    assert stored == ["weights.pt"]
    assert [path.name for path in artifact_root(tmp_path).rglob("weights.pt")] == ["weights.pt"]
