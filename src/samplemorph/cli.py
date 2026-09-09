from __future__ import annotations

import argparse
import logging
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

import torch
from sqlalchemy import Connection

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.measurement.corpus import (
    DEFAULT_PROBE_FRAME_CEILING,
    DEFAULT_PROBE_FRAME_FLOOR,
    read_probe_samples,
)
from samplemorph.model_store import (
    PRINCIPAL_COMPONENT_CODEC_NAME,
    MorphModel,
    MorphModelDescription,
    load_model,
    model_path,
    save_model,
)
from samplemorph.pipeline import MorphRoute, encode_sample, listening_set_manifest, render_listening_set
from samplemorph.registries import (
    CANONICALIZER_REGISTRY,
    DEFAULT_CANONICALIZER_NAME,
    DEFAULT_MORPHER_NAME,
    DEFAULT_VOCODER_NAME,
    LEARNED_VOCODER_NAME,
    MORPHER_REGISTRY,
    VOCODER_REGISTRY,
)
from samplemorph.training.phase_dataset import DEFAULT_CROP_FRAMES
from samplemorph.training.phase_trainer import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_EPOCHS,
    DEFAULT_LEARNING_RATE,
    DEFAULT_WORKER_COUNT,
    EpochReport,
    PhaseCorpus,
    TrainingSettings,
    train_phase_model,
)
from samplemorph.training.principal_components import (
    DEFAULT_LATENT_SIZE,
    DEFAULT_RANDOM_SEED,
    PrincipalComponentTrainer,
)
from samplemorph.vocoders import Vocoder
from samplemorph.vocoders.learned import (
    DEFAULT_PHASE_MODEL_NAME,
    PhaseModelDescription,
    load_phase_model,
    phase_model_path,
    save_phase_model,
)
from samplemorph.vocoders.phase_model import DEFAULT_CHANNELS, PhaseModel

DEFAULT_MODEL_NAME: Final[str] = "principal_components"
DEFAULT_FIT_SAMPLE_COUNT: Final[int] = 4_000
DEFAULT_TRAIN_SAMPLE_COUNT: Final[int] = 20_000
DEFAULT_DEVICE: Final[str] = "cuda"
MANIFEST_NAME: Final[str] = "manifest.json"

_logger = logging.getLogger(__name__)


@unique
class MorphCommand(StrEnum):
    """What this pipeline does from a shell: fit a codec, teach a vocoder, and render audio."""

    FIT = "fit"
    TRAIN_PHASE = "train-phase"
    RENDER = "render"


def main(argv: list[str] | None = None) -> None:
    """Fit a codec over the library, or render a listening set through one, and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        match MorphCommand(arguments.command):
            case MorphCommand.FIT:
                _fit(connection, config, arguments)
            case MorphCommand.TRAIN_PHASE:
                _train_phase(connection, config, arguments)
            case MorphCommand.RENDER:
                _render(connection, config, arguments)


def _fit(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    canonicalizer = CANONICALIZER_REGISTRY[arguments.canonicalizer]()
    samples = PostgresSampleRepository(connection).sample_reproducibly(
        count=arguments.samples,
        random_seed=arguments.seed,
        frame_floor=DEFAULT_PROBE_FRAME_FLOOR,
        frame_ceiling=DEFAULT_PROBE_FRAME_CEILING,
    )
    _logger.info("Canonicalizing %d samples on the %s axis...", len(samples), arguments.canonicalizer)
    images = [canonicalizer.canonicalize(probe.mono) for probe in read_probe_samples(config.library_root, samples)]

    trainer = PrincipalComponentTrainer(
        canonicalizer.geometry, latent_size=arguments.latent_size, random_seed=arguments.seed
    )
    codec = trainer.fit(images)
    description = MorphModelDescription(
        codec=PRINCIPAL_COMPONENT_CODEC_NAME,
        canonicalizer=arguments.canonicalizer,
        geometry=canonicalizer.geometry,
        latent_size=codec.latent_size,
        fitted_sample_count=len(images),
        random_seed=arguments.seed,
        explained_variance=codec.explained_variance,
    )
    path = model_path(config.library_root, name=arguments.model)
    save_model(path, MorphModel(description=description, codec=codec))

    _logger.info(
        "Fitted %d components over %d samples, holding %.1f%% of their variance. Wrote %s.",
        codec.latent_size,
        len(images),
        100.0 * codec.explained_variance,
        path,
    )


def _render(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    model = load_model(model_path(config.library_root, name=arguments.model))
    canonicalizer = _canonicalizer_for(model)
    codec = model.codec
    first = encode_sample(
        connection,
        config.library_root,
        _require_sample(connection, arguments.first),
        canonicalizer=canonicalizer,
        codec=codec,
    )
    second = encode_sample(
        connection,
        config.library_root,
        _require_sample(connection, arguments.second),
        canonicalizer=canonicalizer,
        codec=codec,
    )

    output_directory = Path(arguments.output)
    summary = render_listening_set(
        first,
        second,
        route=MorphRoute(
            canonicalizer=canonicalizer,
            codec=codec,
            vocoder=_vocoder_for(config, arguments),
            morpher=MORPHER_REGISTRY[arguments.morpher](),
        ),
        output_directory=output_directory,
    )
    (output_directory / MANIFEST_NAME).write_text(listening_set_manifest(model.description, summary))

    _logger.info(
        "Wrote %d files for %s against %s, %d of them morphs, into %s.",
        len(summary.files),
        summary.first_hash[:12],
        summary.second_hash[:12],
        summary.morph_count,
        output_directory,
    )


def _canonicalizer_for(model: MorphModel) -> Canonicalizer:
    """Rebuild the frequency axis a model was fitted on.

    Raises:
        ValueError: the model names a canonicalizer this build has no entry for.
    """
    if model.description.canonicalizer not in CANONICALIZER_REGISTRY:
        raise ValueError(f"this model was fitted on the unknown {model.description.canonicalizer} axis")

    return CANONICALIZER_REGISTRY[model.description.canonicalizer]()


def _require_sample(connection: Connection, sample_hash: str) -> Sample:
    """Look one sample up by hash.

    Raises:
        ValueError: the catalog holds no sample under that hash.
    """
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise ValueError(f"the catalog holds no sample {sample_hash}")

    return sample


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit a decodable sample codec, and render morphs through it.")
    commands = parser.add_subparsers(dest="command", required=True)

    fit = commands.add_parser(MorphCommand.FIT.value, help="Fit a codec over a draw of the library.")
    fit.add_argument(
        "--canonicalizer",
        choices=sorted(CANONICALIZER_REGISTRY),
        default=DEFAULT_CANONICALIZER_NAME,
        help="Which frequency axis to canonicalize onto.",
    )
    fit.add_argument(
        "--latent-size", type=int, default=DEFAULT_LATENT_SIZE, help="How many components the codec keeps."
    )
    fit.add_argument("--samples", type=int, default=DEFAULT_FIT_SAMPLE_COUNT, help="How many samples to fit over.")
    fit.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed the draw and the fit use.")
    fit.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help="The name to store the model under.")

    train = commands.add_parser(
        MorphCommand.TRAIN_PHASE.value, help="Teach a phase model the phase this pipeline's magnitudes carry."
    )
    train.add_argument(
        "--canonicalizer",
        choices=sorted(CANONICALIZER_REGISTRY),
        default=DEFAULT_CANONICALIZER_NAME,
        help="Which frequency axis the magnitudes are produced on.",
    )
    train.add_argument("--samples", type=int, default=DEFAULT_TRAIN_SAMPLE_COUNT, help="How many samples to train on.")
    train.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS, help="How many passes over the training samples.")
    train.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help="How many crops make up one step.")
    train.add_argument(
        "--channels", type=int, default=DEFAULT_CHANNELS, help="How much capacity the network spends per layer."
    )
    train.add_argument(
        "--crop", type=int, default=DEFAULT_CROP_FRAMES, help="How many analysis frames one training crop spans."
    )
    train.add_argument(
        "--learning-rate", type=float, default=DEFAULT_LEARNING_RATE, help="The rate the optimizer starts at."
    )
    train.add_argument(
        "--workers", type=int, default=DEFAULT_WORKER_COUNT, help="How many processes derive training examples."
    )
    train.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed the draw and the split use.")
    train.add_argument("--device", type=str, default=DEFAULT_DEVICE, help="Which device to train on.")
    train.add_argument(
        "--phase-model", type=str, default=DEFAULT_PHASE_MODEL_NAME, help="The name to store the phase model under."
    )

    render = commands.add_parser(MorphCommand.RENDER.value, help="Render a listening set between two samples.")
    render.add_argument("--first", type=str, required=True, help="The sample hash the morph starts from.")
    render.add_argument("--second", type=str, required=True, help="The sample hash the morph arrives at.")
    render.add_argument("--output", type=str, required=True, help="The directory to write the audio into.")
    render.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help="Which stored model to render through.")
    render.add_argument(
        "--vocoder",
        choices=sorted({*VOCODER_REGISTRY, LEARNED_VOCODER_NAME}),
        default=DEFAULT_VOCODER_NAME,
        help="Which vocoder estimates the phase a magnitude spectrogram lost.",
    )
    render.add_argument(
        "--phase-model",
        type=str,
        default=DEFAULT_PHASE_MODEL_NAME,
        help="Which stored phase model the learned vocoder reads.",
    )
    render.add_argument("--device", type=str, default=DEFAULT_DEVICE, help="Which device the learned vocoder runs on.")
    render.add_argument(
        "--morpher",
        choices=sorted(MORPHER_REGISTRY),
        default=DEFAULT_MORPHER_NAME,
        help="Which route the morph takes between the two latents.",
    )
    return parser.parse_args(argv)


def _train_phase(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Teach a phase model on the magnitudes this pipeline's own canonicalizer produces."""
    canonicalizer = CANONICALIZER_REGISTRY[arguments.canonicalizer]()
    samples = PostgresSampleRepository(connection).sample_reproducibly(
        count=arguments.samples,
        random_seed=arguments.seed,
        frame_floor=DEFAULT_PROBE_FRAME_FLOOR,
        frame_ceiling=DEFAULT_PROBE_FRAME_CEILING,
    )
    device = torch.device(arguments.device)
    path = phase_model_path(config.library_root, name=arguments.phase_model)

    def _keep_best(model: PhaseModel, report: EpochReport) -> None:
        """Write the weights whenever an epoch beats every epoch before it."""
        save_phase_model(
            path,
            model,
            PhaseModelDescription(
                canonicalizer=arguments.canonicalizer,
                bin_count=model.shape.bin_count,
                frames_per_turn=model.shape.frames_per_turn,
                channels=model.shape.channels,
                kernel_size=model.shape.kernel_size,
                dilations=model.shape.dilations,
                fft_length=canonicalizer.geometry.fft_length,
                hop_length=canonicalizer.geometry.hop_length,
                epochs=report.epoch,
                trained_sample_count=len(samples),
                best_validation_loss=report.validation_loss,
            ),
        )
        _logger.info("  epoch %d is the best so far; wrote %s.", report.epoch, path)

    trained = train_phase_model(
        PhaseCorpus(
            samples=samples,
            library_root=config.library_root,
            canonicalizer=canonicalizer,
            canonicalizer_name=arguments.canonicalizer,
        ),
        settings=TrainingSettings(
            epochs=arguments.epochs,
            batch_size=arguments.batch,
            channels=arguments.channels,
            crop_frames=arguments.crop,
            learning_rate=arguments.learning_rate,
            worker_count=arguments.workers,
            random_seed=arguments.seed,
        ),
        device=device,
        on_improvement=_keep_best,
    )
    _logger.info(
        "Trained over %d samples for %d epochs. The best epoch scored %.4f and is what %s holds.",
        len(samples),
        trained.settings.epochs,
        trained.best_validation_loss,
        path,
    )


def _vocoder_for(config: LibraryConfig, arguments: argparse.Namespace) -> Vocoder:
    """Build the vocoder a render was asked for, loading a fitted phase model when one is named.

    Raises:
        FileNotFoundError: the learned vocoder was asked for and no model is stored under that name.
    """
    if arguments.vocoder == LEARNED_VOCODER_NAME:
        return load_phase_model(
            phase_model_path(config.library_root, name=arguments.phase_model), device=torch.device(arguments.device)
        )

    return VOCODER_REGISTRY[arguments.vocoder]()
