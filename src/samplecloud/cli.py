from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import Connection

from samplecloud.backends import FeatureExtractor
from samplecloud.backends.learned_backend import DEFAULT_LEARNED_DEVICE
from samplecloud.experiments import (
    EmbeddingRecipe,
    ExperimentRefused,
    experiment_named,
    extractor_for,
    recipe_of,
)
from samplecloud.registries import BACKEND_REGISTRY, DEFAULT_BACKEND_NAME
from samplecloud.run import EmbeddingOptions, EmbeddingSummary, create_experiment, experiment_to_rebuild, run_embedding
from samplecore.cli_support import bootstrap_cli, open_catalog_connection, positive_integer
from samplecore.config import LibraryConfig
from samplecore.models.experiment import LEARNED_BACKEND_NAME, Reading

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run one embedding pass over the catalog and report the result."""
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        try:
            summary = _embed(config, connection, arguments)
        except ExperimentRefused as error:
            _logger.error("Embedded nothing: %s.", error)
            sys.exit(1)

    _report(summary)


def _embed(config: LibraryConfig, connection: Connection, arguments: argparse.Namespace) -> EmbeddingSummary:
    """Pick the experiment the arguments name, then extract and lay out what it still lacks.

    A new experiment's extractor is built before its row is written, so a descriptor that fails to
    load leaves the catalog as it was.

    Raises:
        ExperimentRefused: the arguments name an experiment that cannot be resumed as asked.
    """
    promote = not arguments.extract_only
    if arguments.resume_promoted:
        _refuse_beside_resume_promoted(arguments)
        experiment_id = experiment_to_rebuild(connection)
        recipe = recipe_of(experiment_named(connection, experiment_id))
        return _run(config, connection, arguments, experiment_id=experiment_id, recipe=recipe, promote=True)
    if arguments.experiment_id is not None:
        recipe = recipe_of(experiment_named(connection, arguments.experiment_id))
        _refuse_conflicts(arguments, recipe)
        return _run(
            config, connection, arguments, experiment_id=arguments.experiment_id, recipe=recipe, promote=promote
        )

    recipe = _requested_recipe(arguments)
    feature_extractor = extractor_for(recipe, library_root=config.library_root, device=arguments.device)
    experiment_id = create_experiment(connection, recipe, label=arguments.label)
    return run_embedding(
        config,
        connection,
        experiment_id,
        extractor=lambda: feature_extractor,
        options=EmbeddingOptions(reading=recipe.reading, sample_limit=arguments.limit, promote=promote),
    )


def _run(
    config: LibraryConfig,
    connection: Connection,
    arguments: argparse.Namespace,
    *,
    experiment_id: int,
    recipe: EmbeddingRecipe,
    promote: bool,
) -> EmbeddingSummary:
    def build_extractor() -> FeatureExtractor:
        return extractor_for(recipe, library_root=config.library_root, device=arguments.device)

    return run_embedding(
        config,
        connection,
        experiment_id,
        extractor=build_extractor,
        options=EmbeddingOptions(reading=recipe.reading, sample_limit=arguments.limit, promote=promote),
    )


def _requested_recipe(arguments: argparse.Namespace) -> EmbeddingRecipe:
    """The recipe a new experiment follows, from the backend, model and reading flags.

    Raises:
        ExperimentRefused: a learned backend is chosen with no model, or a model with another backend.
    """
    backend_name = arguments.backend if arguments.backend is not None else DEFAULT_BACKEND_NAME
    if backend_name == LEARNED_BACKEND_NAME and arguments.model is None:
        raise ExperimentRefused(f"the {LEARNED_BACKEND_NAME} backend needs --model to name the stored descriptor")
    if backend_name != LEARNED_BACKEND_NAME and arguments.model is not None:
        raise ExperimentRefused(f"--model names a stored descriptor, which the {LEARNED_BACKEND_NAME} backend reads")

    return EmbeddingRecipe(
        backend_name=backend_name,
        reading=Reading.HEARD_RATE if arguments.heard_rate else Reading.NOMINAL,
        model_name=arguments.model,
    )


def _refuse_beside_resume_promoted(arguments: argparse.Namespace) -> None:
    """Refuse the flags a rebuild settles on its own: the recipe, the label, and whether the cloud changes.

    Raises:
        ExperimentRefused: any of them is given.
    """
    given = [
        flag
        for flag, value in (
            ("--backend", arguments.backend),
            ("--model", arguments.model),
            ("--label", arguments.label),
            ("--heard-rate", arguments.heard_rate or None),
            ("--extract-only", arguments.extract_only or None),
        )
        if value is not None
    ]
    if given:
        raise ExperimentRefused(
            f"--resume-promoted follows the recipe of the experiment the cloud shows and lays it out, "
            f"so it takes none of {', '.join(given)}"
        )


def _refuse_conflicts(arguments: argparse.Namespace, recipe: EmbeddingRecipe) -> None:
    """Refuse flags naming a recipe other than the resumed experiment's own, and a label, which names a new one.

    Raises:
        ExperimentRefused: any such flag is given.
    """
    conflicts: list[str] = []
    if arguments.backend is not None and arguments.backend != recipe.backend_name:
        conflicts.append(f"--backend {arguments.backend} (it was made by {recipe.backend_name})")
    if arguments.model is not None and arguments.model != recipe.model_name:
        conflicts.append(f"--model {arguments.model} (it reads {recipe.model_name or 'no stored descriptor'})")
    if arguments.heard_rate and recipe.reading != Reading.HEARD_RATE:
        conflicts.append(f"--heard-rate (it records the {recipe.reading.value} reading)")
    if arguments.label is not None:
        conflicts.append("--label (a label names a new experiment)")
    if conflicts:
        raise ExperimentRefused(
            f"experiment {arguments.experiment_id} keeps its own recipe, which conflicts with {'; '.join(conflicts)}"
        )


def _report(summary: EmbeddingSummary) -> None:
    _logger.info(
        "Experiment %d: extracted features for %d new samples (%d already known, %d cataloged).",
        summary.experiment_id,
        summary.extraction.newly_extracted,
        summary.extraction.already_extracted,
        summary.extraction.cataloged,
    )
    if summary.reduction is not None:
        _logger.info("Reduced %d samples to 2D coordinates.", summary.reduction.samples_reduced)


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog, description="Extract sample features and reduce them to cloud coordinates."
    )
    parser.add_argument(
        "--backend",
        choices=sorted({*BACKEND_REGISTRY, LEARNED_BACKEND_NAME}),
        default=None,
        help=f"Which FeatureExtractor backend a new experiment runs ({DEFAULT_BACKEND_NAME} when left out).",
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Which stored descriptor the learned backend reads, by name."
    )
    parser.add_argument(
        "--device", type=str, default=DEFAULT_LEARNED_DEVICE, help="Which device a learned descriptor runs on."
    )
    parser.add_argument("--label", type=str, default=None, help="A human-readable note for a new experiment.")
    chosen_experiment = parser.add_mutually_exclusive_group()
    chosen_experiment.add_argument(
        "--experiment-id",
        type=positive_integer,
        default=None,
        help="Resume an existing experiment's extraction, following the recipe it records.",
    )
    chosen_experiment.add_argument(
        "--resume-promoted",
        action="store_true",
        help="Resume the experiment the cloud shows and lay it out again, or start the default one on an empty cloud.",
    )
    parser.add_argument(
        "--limit",
        type=positive_integer,
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
