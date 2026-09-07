from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from typing import Final

from samplecloud.backends import FeatureExtractor
from samplecloud.backends.invariant_backend import InvariantFeatureExtractor
from samplecloud.backends.librosa_backend import LibrosaFeatureExtractor
from samplecloud.run import resolve_experiment, run_embedding
from samplecore.cli_support import bootstrap_cli, open_catalog_connection

DEFAULT_BACKEND_NAME: Final[str] = "librosa"
BACKEND_REGISTRY: Final[dict[str, Callable[[], FeatureExtractor]]] = {
    DEFAULT_BACKEND_NAME: LibrosaFeatureExtractor,
    "invariant": InvariantFeatureExtractor,
}

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one embedding pass over the catalog and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    feature_extractor = BACKEND_REGISTRY[arguments.backend]()
    with open_catalog_connection(config.database_url) as connection:
        experiment_id = resolve_experiment(
            connection, backend_name=arguments.backend, label=arguments.label, experiment_id=arguments.experiment_id
        )
        summary = run_embedding(config, connection, feature_extractor, experiment_id, sample_limit=arguments.limit)

    _logger.info(
        "Experiment %d: extracted features for %d new samples (%d already known, %d catalogued). "
        "Reduced %d samples to 2D coordinates.",
        summary.experiment_id,
        summary.extraction.newly_extracted,
        summary.extraction.already_extracted,
        summary.extraction.catalogued,
        summary.reduction.samples_reduced,
    )


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract sample features and reduce them to 2D cloud coordinates.")
    parser.add_argument(
        "--backend",
        choices=sorted(BACKEND_REGISTRY),
        default=DEFAULT_BACKEND_NAME,
        help="Which FeatureExtractor backend to run, as its own independent experiment.",
    )
    parser.add_argument(
        "--label", type=str, default=None, help="A human-readable note for the resulting experiment, if any."
    )
    parser.add_argument(
        "--experiment-id",
        type=int,
        default=None,
        help="Resume an existing experiment's extraction instead of starting a new one.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Extract features for only the first N unfeatured samples, for a quick run over a small slice.",
    )
    return parser.parse_args(argv)
