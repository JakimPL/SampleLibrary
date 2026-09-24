from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass

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
from samplecore.cli_parsing import command_parser
from samplecore.cli_support import (
    bootstrap_cli,
    ending_in_one_line,
    experiment_key,
    open_catalog_connection,
    positive_integer,
)
from samplecore.config import LibraryConfig
from samplecore.models.experiment import LEARNED_BACKEND_NAME, Reading
from samplecore.storage.repositories.experiment import PostgresExperimentRepository

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run one embedding pass over the catalog and report the result."""
    arguments = parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with (
        open_catalog_connection(config.catalog_url()) as connection,
        ending_in_one_line("Embedded nothing", (ExperimentRefused,)),
    ):
        summary = _embed(config, connection, arguments)

    _report(summary)


@dataclass(frozen=True)
class ChosenExperiment:
    """The experiment a run fills, the recipe it follows, whether the cloud shows it after, and what builds its extractor."""

    experiment_id: int
    recipe: EmbeddingRecipe
    promote: bool
    extractor: Callable[[], FeatureExtractor]


def _embed(config: LibraryConfig, connection: Connection, arguments: argparse.Namespace) -> EmbeddingSummary:
    """Pick the experiment the arguments name, then extract and lay out what it still lacks.

    Raises:
        ExperimentRefused: the arguments name an experiment that cannot be resumed as asked.
    """
    chosen = _chosen_experiment(config, connection, arguments)
    return run_embedding(
        config,
        connection,
        chosen.experiment_id,
        extractor=chosen.extractor,
        options=EmbeddingOptions(reading=chosen.recipe.reading, sample_limit=arguments.limit, promote=chosen.promote),
    )


def _chosen_experiment(
    config: LibraryConfig, connection: Connection, arguments: argparse.Namespace
) -> ChosenExperiment:
    """The experiment the arguments name: the one the cloud shows, one resumed by its id or key, or a new one.

    A resumed experiment builds its extractor only when a sample is missing from it. A new
    experiment's extractor is built before its row is written, so a descriptor that fails to load
    leaves the catalog as it was. A key names the experiment a first run files under it and every
    later run resumes, following the recipe that first run recorded.

    Raises:
        ExperimentRefused: the arguments name an experiment that cannot be resumed as asked.
    """

    def resumed(experiment_id: int, recipe: EmbeddingRecipe, *, promote: bool) -> ChosenExperiment:
        def build_extractor() -> FeatureExtractor:
            return extractor_for(recipe, library_root=config.library_root, device=arguments.device)

        return ChosenExperiment(experiment_id=experiment_id, recipe=recipe, promote=promote, extractor=build_extractor)

    if arguments.resume_promoted:
        _refuse_beside_resume_promoted(arguments)
        experiment_id = experiment_to_rebuild(connection)
        return resumed(experiment_id, recipe_of(experiment_named(connection, experiment_id)), promote=True)
    if arguments.experiment_id is not None:
        recipe = recipe_of(experiment_named(connection, arguments.experiment_id))
        _refuse_conflicts(arguments, recipe, experiment_id=arguments.experiment_id)
        return resumed(arguments.experiment_id, recipe, promote=not arguments.extract_only)
    if arguments.key is not None:
        filed = PostgresExperimentRepository(connection).get_by_key(arguments.key)
        if filed is not None:
            recipe = recipe_of(filed)
            _refuse_conflicts(arguments, recipe, experiment_id=filed.id)
            return resumed(filed.id, recipe, promote=not arguments.extract_only)

    recipe = _requested_recipe(arguments)
    feature_extractor = extractor_for(recipe, library_root=config.library_root, device=arguments.device)
    return ChosenExperiment(
        experiment_id=create_experiment(connection, recipe, label=arguments.label, key=arguments.key),
        recipe=recipe,
        promote=not arguments.extract_only,
        extractor=lambda: feature_extractor,
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


def _refuse_conflicts(arguments: argparse.Namespace, recipe: EmbeddingRecipe, *, experiment_id: int) -> None:
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
            f"experiment {experiment_id} keeps its own recipe, which conflicts with {'; '.join(conflicts)}"
        )


def _report(summary: EmbeddingSummary) -> None:
    _logger.info(
        "Experiment %d: extracted features for %d new samples (%d already known, %d with no file to read now, "
        "%d cataloged).",
        summary.experiment_id,
        summary.extraction.newly_extracted,
        summary.extraction.already_extracted,
        summary.extraction.unavailable,
        summary.extraction.cataloged,
    )
    if summary.reduction is not None:
        _logger.info("Reduced %d samples to 2D coordinates.", summary.reduction.samples_reduced)


def parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description="Extract sample features and reduce them to cloud coordinates.")
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
        "--key",
        type=experiment_key,
        default=None,
        help="Resume the experiment filed under this key, or start one under it following the recipe flags.",
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
