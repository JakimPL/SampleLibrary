from __future__ import annotations

import json
from typing import Any, Protocol

from sqlalchemy import Connection, Row, select

from samplecore.models.experiment import Experiment
from samplecore.storage.database import experiment, experiment_id_sequence


class ExperimentRepository(Protocol):
    """Persistence for the Experiment catalog: one row per embedding run's identity."""

    def next_id(self) -> int: ...

    def insert(self, experiment_: Experiment) -> None: ...

    def get(self, experiment_id: int) -> Experiment | None: ...


class PostgresExperimentRepository:
    """An ExperimentRepository backed by the catalog's ``experiment`` table.

    An experiment's ``id`` is assigned before construction, via ``next_id``, mirroring
    ``PostgresModuleRepository``'s own reasoning: the domain model requires an id up front, so the
    caller must already hold one by the time it builds a complete ``Experiment`` to insert.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def next_id(self) -> int:
        return self._connection.execute(select(experiment_id_sequence.next_value())).scalar_one()

    def insert(self, experiment_: Experiment) -> None:
        self._connection.execute(
            experiment.insert().values(
                id=experiment_.id,
                backend_name=experiment_.backend_name,
                params=json.dumps(experiment_.params),
                created_at=experiment_.created_at,
                label=experiment_.label,
            )
        )

    def get(self, experiment_id: int) -> Experiment | None:
        row = self._connection.execute(select(experiment).where(experiment.c.id == experiment_id)).fetchone()
        return _row_to_experiment(row) if row is not None else None


def _row_to_experiment(row: Row[Any]) -> Experiment:
    """Reconstruct an Experiment from a Core row, addressed by its own column names."""
    return Experiment(
        id=row.id,
        backend_name=row.backend_name,
        params=json.loads(row.params),
        created_at=row.created_at,
        label=row.label,
    )
