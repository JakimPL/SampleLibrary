from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from mlflow.entities import RunStatus
from mlflow.tracking import MlflowClient

from samplecore.tracking.store import artifact_root, tracking_uri


@dataclass(frozen=True)
class MlflowRun:
    """A TrackedRun keeping what it is told in an MLflow store.

    Its client is held rather than reached for globally, so the run a call records against is the
    one this object names. That is what lets a training loop's own logger write to the same run as
    the command that opened it, and what keeps two runs in one process from colliding.
    """

    client: MlflowClient
    run_id: str

    def log_parameters(self, parameters: dict[str, str]) -> None:
        for name, value in parameters.items():
            self.client.log_param(self.run_id, name, value)

    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        for name, value in metrics.items():
            self.client.log_metric(self.run_id, name, value, step=step)

    def log_artifact(self, path: Path) -> None:
        self.client.log_artifact(self.run_id, str(path))


@contextmanager
def tracked_run(library_root: Path, *, experiment_name: str, run_name: str) -> Iterator[MlflowRun]:
    """Open a recorded run under `experiment_name`, closing it with the outcome it reached.

    A run that raises is marked as failed rather than left open, so a store read later separates the
    passes that finished from the ones a crash or an interrupt ended -- which on this machine is a
    distinction worth keeping.
    """
    client = MlflowClient(tracking_uri=tracking_uri(library_root))
    run = client.create_run(_experiment_id(client, name=experiment_name, library_root=library_root), run_name=run_name)
    opened = MlflowRun(client=client, run_id=run.info.run_id)
    status = RunStatus.to_string(RunStatus.FAILED)
    try:
        yield opened
        status = RunStatus.to_string(RunStatus.FINISHED)
    finally:
        client.set_terminated(opened.run_id, status=status)


def _experiment_id(client: MlflowClient, *, name: str, library_root: Path) -> str:
    """The identity runs of this name are grouped under, created the first time one is asked for.

    Where its files go is stated at creation, since a client left to decide writes them beneath the
    working directory.
    """
    existing = client.get_experiment_by_name(name)
    if existing is not None:
        return existing.experiment_id

    return client.create_experiment(name, artifact_location=artifact_root(library_root).as_uri())
