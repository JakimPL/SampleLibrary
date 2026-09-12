from __future__ import annotations

import argparse
import logging

from samplecloud.backends import FeatureExtractor
from samplecloud.backends.learned_backend import DEFAULT_LEARNED_DEVICE, build_learned_extractor, learned_parameters
from samplecloud.hearing import Reading
from samplecloud.registries import BACKEND_REGISTRY, DEFAULT_BACKEND_NAME
from samplecloud.run import EmbeddingOptions, reading_parameters, resolve_experiment, run_embedding
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.models.experiment import LEARNED_BACKEND_NAME

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one embedding pass over the catalog and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    feature_extractor = _extractor_for(config, arguments)
    reading = Reading.HEARD_RATE if arguments.heard_rate else Reading.NOMINAL
    with open_catalog_connection(config.database_url) as connection:
        experiment_id = resolve_experiment(
            connection,
            backend_name=arguments.backend,
            label=arguments.label,
            params=reading_parameters(reading)
            | (learned_parameters(arguments.model) if arguments.backend == LEARNED_BACKEND_NAME else {}),
            experiment_id=arguments.experiment_id,
        )
        summary = run_embedding(
            config,
            connection,
            feature_extractor,
            experiment_id,
            options=EmbeddingOptions(reading=reading, sample_limit=arguments.limit, promote=not arguments.extract_only),
        )

    _logger.info(
        "Experiment %d: extracted features for %d new samples (%d already known, %d cataloged).",
        summary.experiment_id,
        summary.extraction.newly_extracted,
        summary.extraction.already_extracted,
        summary.extraction.cataloged,
    )
    if summary.reduction is not None:
        _logger.info("Reduced %d samples to 2D coordinates.", summary.reduction.samples_reduced)


def _extractor_for(config: LibraryConfig, arguments: argparse.Namespace) -> FeatureExtractor:
    """The extractor the run was asked for: a registered backend, or a stored descriptor by name.

    Raises:
        ValueError: the learned backend was chosen with no model named.
    """
    if arguments.backend != LEARNED_BACKEND_NAME:
        return BACKEND_REGISTRY[arguments.backend]()
    if arguments.model is None:
        raise ValueError(f"the {LEARNED_BACKEND_NAME} backend needs --model to name the stored descriptor")

    return build_learned_extractor(config.library_root, model_name=arguments.model, device=arguments.device)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract sample features and reduce them to 2D cloud coordinates.")
    parser.add_argument(
        "--backend",
        choices=sorted({*BACKEND_REGISTRY, LEARNED_BACKEND_NAME}),
        default=DEFAULT_BACKEND_NAME,
        help="Which FeatureExtractor backend to run, as its own independent experiment.",
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Which stored descriptor the learned backend reads, by name."
    )
    parser.add_argument(
        "--device", type=str, default=DEFAULT_LEARNED_DEVICE, help="Which device a learned descriptor runs on."
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
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Keep the experiment's vectors and leave the cloud as it is, for an experiment made to be measured.",
    )
    parser.add_argument(
        "--heard-rate",
        action="store_true",
        help="Read every sample at the rate the library plays it at, the way a listener hears it.",
    )
    return parser.parse_args(argv)
