from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.models.cloud import ModuleCloudCoordinate
from samplecore.models.module import Module
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.cloud import (
    ModuleCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.module import PostgresModuleRepository

PLACEHOLDER_COORDINATE_BOUND: Final[float] = 10.0

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlaceholderEmbeddingSummary:
    """What one placeholder-embedding run did, across every module it considered."""

    modules_placed: int


def generate_placeholder_coordinates(
    modules: tuple[Module, ...], *, computed_at: datetime
) -> tuple[ModuleCloudCoordinate, ...]:
    """Place every given Module at a coordinate seeded from its own hash.

    Stands in for a genuine per-module embedding -- which needs a feature-aggregation step and a
    fresh UMAP fit samplecloud does not yet have -- until a spectral-distance similarity metric
    makes one possible. Seeding each point's own generator from `module.hash`, rather than drawing
    every point from one shared generator, keeps a module's placement stable across repeated runs
    over the same catalog without persisting any model state between them.
    """
    return tuple(_placeholder_coordinate(module, computed_at=computed_at) for module in modules)


def _placeholder_coordinate(module: Module, *, computed_at: datetime) -> ModuleCloudCoordinate:
    generator = random.Random(module.hash)
    x = generator.uniform(-PLACEHOLDER_COORDINATE_BOUND, PLACEHOLDER_COORDINATE_BOUND)
    y = generator.uniform(-PLACEHOLDER_COORDINATE_BOUND, PLACEHOLDER_COORDINATE_BOUND)
    return ModuleCloudCoordinate(module_hash=module.hash, x=x, y=y, computed_at=computed_at)


def place_and_persist_coordinates(connection: Connection) -> PlaceholderEmbeddingSummary:
    """Generate and store one placeholder 2D coordinate for every currently-cataloged Module.

    A full recompute every run, mirroring `reduce_and_persist_coordinates`'s own crash-safety
    pattern -- the whole pass runs as one transaction, landing completely or not at all.
    """
    modules = PostgresModuleRepository(connection).list_all()
    coordinates = generate_placeholder_coordinates(modules, computed_at=datetime.now(UTC))

    coordinate_repository: ModuleCloudCoordinateRepository = PostgresModuleCloudCoordinateRepository(connection)
    with start_batch(connection):
        coordinate_repository.replace_all(coordinates)

    return PlaceholderEmbeddingSummary(modules_placed=len(coordinates))


def main() -> None:
    """Place every cataloged module at a placeholder 2D coordinate and report the result."""
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        summary = place_and_persist_coordinates(connection)

    _logger.info("Placed %d module(s) at placeholder cloud coordinates.", summary.modules_placed)
