from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection

from samplecloud.modules.distance import chamfer_distances, nearest_distances_to_modules
from samplecloud.modules.layout import LayoutPreservation, fit_module_plane, preservation
from samplecloud.modules.membership import load_module_sample_sets
from samplecloud.reduce import MINIMUM_SAMPLES_FOR_REDUCTION, neighbor_count
from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.models.cloud import ModuleCloudCoordinate
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.cloud import (
    ModuleCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleCloudSummary:
    """What one module layout run did: how many modules it placed and how faithfully.

    ``preservation`` is ``None`` when too few modules carry embedded samples for a layout.
    """

    modules_placed: int
    preservation: LayoutPreservation | None


def lay_out_and_persist_modules(connection: Connection) -> ModuleCloudSummary:
    """Place every module with embedded samples on the plane by the distance between their sample sets.

    Reads the promoted spectral vectors, so the modules follow whichever experiment the sample cloud
    shows. The layout is recomputed in full every run and replaces every stored module coordinate in
    one transaction, so a run lands completely or leaves the previous layout in place.
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

    _logger.info("Measuring %d modules over %d distinct samples...", module_count, len(sets.vectors))
    distances = chamfer_distances(sets, nearest_distances_to_modules(sets))
    _logger.info("Fitting UMAP over %d module distances...", module_count)
    coordinates = fit_module_plane(distances, n_neighbors=neighbor_count(module_count))

    computed_at = datetime.now(UTC)
    new_coordinates = [
        ModuleCloudCoordinate(module_hash=module_hash, x=float(x), y=float(y), computed_at=computed_at)
        for module_hash, (x, y) in zip(sets.module_hashes, coordinates, strict=True)
    ]
    coordinate_repository: ModuleCloudCoordinateRepository = PostgresModuleCloudCoordinateRepository(connection)
    with start_batch(connection):
        coordinate_repository.replace_all(new_coordinates)

    return ModuleCloudSummary(modules_placed=module_count, preservation=preservation(distances, coordinates))


def main(argv: list[str], *, prog: str) -> None:
    """Lay the cataloged modules out on the cloud and report how faithfully the plane keeps their distances."""
    _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        summary = lay_out_and_persist_modules(connection)

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
