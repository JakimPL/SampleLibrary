from __future__ import annotations

import argparse
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ValidationError
from sqlalchemy import Connection

from samplecloud.modules.distance import directed_batches, symmetric_distances
from samplecloud.modules.layout import LayoutPreservation, fit_module_plane, preservation
from samplecloud.modules.membership import ModuleSampleSets, load_module_sample_sets
from samplecloud.paths import LAYOUT_RECORD_FILE_NAME, module_layout_directory
from samplecloud.reduce import MINIMUM_SAMPLES_FOR_REDUCTION, neighbor_count
from samplecloud.stages import LayoutStages
from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.digests import digest_of_rows
from samplecore.models.base import FROZEN
from samplecore.models.cloud import ModuleCloudCoordinate
from samplecore.progress import ProgressBar
from samplecore.storage.atomic import write_bytes_atomically
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.cloud import (
    ModuleCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.staged_rows import RowArray, StagedRows

TOWARD_FILE_NAME: Final[str] = "toward.npy"
MEASURING_LABEL: Final[str] = "Measuring modules"

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleCloudSummary:
    """What one module layout run did: how many modules it placed and how faithfully.

    ``preservation`` is ``None`` when too few modules carry embedded samples for a layout.
    """

    modules_placed: int
    preservation: LayoutPreservation | None


class ModuleLayoutRecord(BaseModel):
    """The layout the module cloud last wrote whole: the digest of the modules and sounds it was fitted from."""

    model_config = FROZEN

    digest: str


def lay_out_and_persist_modules(connection: Connection, *, library_root: Path) -> ModuleCloudSummary | None:
    """Place every module with embedded samples on the plane by the distance between their sample sets.

    Reads the promoted spectral vectors, so the modules follow whichever experiment the sample cloud
    shows. A layout is named by the digest of the modules, their samples and those samples' vectors;
    the one the stored coordinates were fitted from is recorded under `library_root`, so a run
    finding the same layout standing returns ``None`` with nothing to do. Otherwise the layout is
    recomputed and replaces every stored module coordinate in one transaction, so a run lands
    completely or leaves the previous layout in place. Its distances are checkpointed batch by
    batch and its coordinates kept once fitted, so a run stopped partway takes up where it stopped.
    """
    sets = load_module_sample_sets(connection)
    module_count = len(sets.module_hashes)
    if module_count < MINIMUM_SAMPLES_FOR_REDUCTION:
        _logger.info(
            "%d module(s) hold embedded samples; a layout needs %d, so the module cloud stays as it is.",
            module_count,
            MINIMUM_SAMPLES_FOR_REDUCTION,
        )
        return ModuleCloudSummary(modules_placed=0, preservation=None)

    directory = module_layout_directory(library_root)
    digest = _layout_digest(sets)
    if _stands(connection, directory, digest=digest, module_count=module_count):
        return None
    stages = LayoutStages.open(directory, digest=digest)
    distances = _measured(sets, directory=directory, digest=digest)
    coordinates = stages.coordinates()
    if coordinates is None:
        _logger.info("Fitting UMAP over %d module distances...", module_count)
        coordinates = fit_module_plane(distances, n_neighbors=neighbor_count(module_count)).astype(np.float64)
        stages.keep_coordinates(coordinates)

    computed_at = datetime.now(UTC)
    new_coordinates = [
        ModuleCloudCoordinate(module_hash=module_hash, x=float(x), y=float(y), computed_at=computed_at)
        for module_hash, (x, y) in zip(sets.module_hashes, coordinates, strict=True)
    ]
    coordinate_repository: ModuleCloudCoordinateRepository = PostgresModuleCloudCoordinateRepository(connection)
    with start_batch(connection):
        coordinate_repository.replace_all(new_coordinates)
    write_bytes_atomically(
        directory / LAYOUT_RECORD_FILE_NAME, ModuleLayoutRecord(digest=digest).model_dump_json().encode("utf-8")
    )
    stages.discard()

    return ModuleCloudSummary(
        modules_placed=module_count, preservation=preservation(distances, coordinates.astype(np.float32))
    )


def _layout_digest(sets: ModuleSampleSets) -> str:
    """The name of the layout these sets make: every module, the rows of its samples, and the vectors they point to."""
    return digest_of_rows(
        [
            ("vectors", hashlib.sha256(np.ascontiguousarray(sets.vectors).tobytes()).hexdigest()),
            *(
                (module_hash, *rows.tolist())
                for module_hash, rows in zip(sets.module_hashes, sets.member_rows, strict=True)
            ),
        ]
    )


def _stands(connection: Connection, directory: Path, *, digest: str, module_count: int) -> bool:
    """Whether the stored module coordinates are the layout named `digest`, which is then left as it is."""
    record_path = directory / LAYOUT_RECORD_FILE_NAME
    if not record_path.is_file():
        return False
    try:
        record = ModuleLayoutRecord.model_validate_json(record_path.read_text(encoding="utf-8"))
    except ValidationError:
        return False
    placed = len(PostgresModuleCloudCoordinateRepository(connection).list_all())
    return record.digest == digest and placed == module_count


def _measured(sets: ModuleSampleSets, *, directory: Path, digest: str) -> NDArray[np.float32]:
    """The Chamfer distances between the sets, measured into the layout's partial and checkpointed batch by batch."""
    module_count = len(sets.module_hashes)
    rows = StagedRows.open(
        directory / digest,
        identity=digest,
        arrays=(RowArray(TOWARD_FILE_NAME, np.float32, (module_count, module_count)),),
    )
    toward = rows.array(TOWARD_FILE_NAME)
    _logger.info("Measuring %d modules over %d distinct samples...", module_count, len(sets.vectors))
    with ProgressBar(total=module_count, label=MEASURING_LABEL, resumed=rows.resumed_rows) as progress:
        try:
            for batch, distances in directed_batches(sets, first_module=rows.resumed_rows):
                toward[batch.start : batch.stop] = distances
                rows.advance_to(batch.stop)
                progress.update(len(batch))
        finally:
            rows.checkpoint()
    return symmetric_distances(np.asarray(toward))


def main(argv: list[str], *, prog: str) -> None:
    """Lay the cataloged modules out on the cloud and report how faithfully the plane keeps their distances."""
    _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with open_catalog_connection(config.catalog_url()) as connection:
        summary = lay_out_and_persist_modules(connection, library_root=config.library_root)

    if summary is None:
        _logger.info("The module cloud already shows these modules and their sounds, so its layout stays.")
        return
    _logger.info("Placed %d module(s) on the cloud.", summary.modules_placed)
    if summary.preservation is not None:
        _logger.info(
            "Distance rank correlation %.3f, neighborhood trustworthiness %.3f.",
            summary.preservation.distance_correlation,
            summary.preservation.trustworthiness,
        )


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog, description="Lay the cataloged modules out on the cloud by the sounds of their samples."
    )
    return parser.parse_args(argv)
