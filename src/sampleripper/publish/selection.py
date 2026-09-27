from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import Connection, select

from samplecore.models.experiment import VOCABULARY_PARAMETER
from samplecore.models.sample_file import SampleFile
from samplecore.storage.database import sample_properties
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.sample_category import PostgresSampleCategoryRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository


@dataclass(frozen=True)
class Selection:
    """The samples a publication carries: those a module holds, and the file-only ones of the published directories, with their files."""

    module_samples: frozenset[str]
    file_samples: dict[str, tuple[SampleFile, ...]]


def published_selection(connection: Connection, *, directories: tuple[str, ...]) -> Selection:
    """The samples a publication of ``directories`` carries, as the catalog on ``connection`` holds them."""
    module_samples = frozenset(
        str(sample_hash)
        for sample_hash in connection.execute(select(sample_properties.c.sample_hash).distinct()).scalars()
    )
    file_samples: defaultdict[str, list[SampleFile]] = defaultdict(list)
    for found in PostgresSampleFileRepository(connection).list_all():
        if found.location.directory.as_posix() in directories and found.sample_hash not in module_samples:
            file_samples[found.sample_hash].append(found)
    return Selection(
        module_samples=module_samples,
        file_samples={sample_hash: tuple(found) for sample_hash, found in file_samples.items()},
    )


def shown_vocabulary(connection: Connection) -> tuple[str, ...] | None:
    """The vocabulary the categories on show were scored with; ``None`` where none are on show."""
    experiment_id = PostgresSampleCategoryRepository(connection).shown_experiment_id()
    if experiment_id is None:
        return None
    experiment = PostgresExperimentRepository(connection).get(experiment_id)
    recorded = experiment.params.get(VOCABULARY_PARAMETER, []) if experiment is not None else []
    return tuple(str(label) for label in recorded) if isinstance(recorded, list) else ()
