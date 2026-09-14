from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from samplecore.storage.repositories.annotation_import import PostgresAnnotationImportRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.steps.kinds import GuardedPassStep, PassStep, Step

LABELS: Final[str] = "labels"
MODULES: Final[str] = "modules"
SAMPLE_FILES: Final[str] = "sample-files"
NOTES: Final[str] = "notes"
THUMBNAILS: Final[str] = "thumbnails"
EQUIVALENCE: Final[str] = "equivalence"
RELINK: Final[str] = "relink"


def catalog_steps() -> tuple[Step, ...]:
    """The passes that bring the catalog level with the collection, and the labels that travel with it.

    Each of them decides for itself what is left to do -- an unchanged collection, a file whose size
    and write time stand, a module already read -- so the run's part is to take them in order.
    """
    return (
        GuardedPassStep(
            name=LABELS,
            requires=(),
            command=_import_labels,
            satisfied=_labels_are_in,
            refusal=_labels_refusal,
        ),
        PassStep(name=MODULES, requires=(LABELS,), command=_extract_modules),
        PassStep(name=SAMPLE_FILES, requires=(LABELS,), command=_scan_sample_files),
        PassStep(name=NOTES, requires=(MODULES,), command=lambda context: ("notes",)),
        PassStep(name=THUMBNAILS, requires=(MODULES, SAMPLE_FILES), command=lambda context: ("thumbnails",)),
        PassStep(name=EQUIVALENCE, requires=(MODULES, SAMPLE_FILES), command=lambda context: ("equivalence",)),
        PassStep(
            name=RELINK,
            requires=(MODULES, SAMPLE_FILES, LABELS),
            command=lambda context: ("annotations", "relink"),
        ),
    )


def _extract_modules(context: PipelineContext) -> tuple[str, ...]:
    return ("extract", "--prune", *_workers(context))


def _scan_sample_files(context: PipelineContext) -> tuple[str, ...]:
    return ("files", "--prune", *_workers(context))


def _workers(context: PipelineContext) -> tuple[str, ...]:
    workers = context.settings.workers
    return () if workers is None else ("--workers", str(workers))


def _import_labels(context: PipelineContext) -> tuple[str, ...]:
    return ("annotations", "import", "--path", str(_labels_file(context)))


def _labels_are_in(context: PipelineContext) -> bool:
    """Whether this library already holds what the configured labels file says."""
    path = _labels_file(context)
    if path is None:
        return True
    digest = _file_digest(path)
    return digest is not None and PostgresAnnotationImportRepository(context.connection).get(digest) is not None


def _labels_refusal(context: PipelineContext) -> str | None:
    """Why the labels cannot be read in, where they cannot: a file that is not there, or labels already made."""
    path = _labels_file(context)
    if path is None:
        return None
    digest = _file_digest(path)
    if digest is None:
        return f"the labels file {path} is not there"
    imports = PostgresAnnotationImportRepository(context.connection)
    if imports.get(digest) is not None:
        return None
    if PostgresSampleAnnotationRepository(context.connection).count() > 0:
        return (
            f"this library already holds labels of its own, and {path} was never read into it; "
            "leave labels out of the pipeline table, or read the file in by hand first"
        )
    return None


def _labels_file(context: PipelineContext) -> Path | None:
    return context.settings.labels


def _file_digest(path: Path) -> str | None:
    """The digest of a file's bytes, or nothing where the file is not there to read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
