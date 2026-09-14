from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from lightning.pytorch import Trainer

from samplecore.hashing import file_sha256
from samplemorph.codecs.conditioned import load_conditioned_codec
from samplemorph.codecs.conditioned_model import ConditionedCodecShape, ResidualLayout
from samplemorph.descriptors.grid_descriptor import DescriptorShape, GridDescriptor
from samplemorph.descriptors.learned import DescriptorDescription, LearnedDescriptor, descriptor_path, save_descriptor
from samplemorph.geometry import log_frequency_geometry
from samplemorph.registries import canonicalizer_for_geometry
from samplemorph.training.codec_data import CodecCorpus, CodecDataModule
from samplemorph.training.codec_export import CodecWriter
from samplemorph.training.codec_losses import (
    CodecLossWeights,
    CodecPrediction,
    codec_loss,
    prior_divergence,
    reconstruction_error,
)
from samplemorph.training.codec_module import DESCRIPTOR_DIGEST_KEY, CodecTrainingModule, ConditioningDescriptor
from samplemorph.training.codec_settings import CodecTrainingSettings
from samplemorph.training.descriptor_cache import (
    DESCRIPTION_FILE_NAME,
    DURATIONS_FILE_NAME,
    GRIDS_FILE_NAME,
    HASHES_FILE_NAME,
    GridCache,
    GridCacheDescription,
    open_grid_cache,
)
from samplemorph.training.export import BestEpochExport
from samplemorph.training.metrics import CODEC_MONITORED_METRIC, CODEC_VALIDATION_RECONSTRUCTION
from samplemorph.training.refusals import ResumeRefused, TrainingDataShortfall, TrainingRefused
from samplemorph.training.run_settings import RunSettings
from tests.samplemorph.training.test_tracked_logger import RecordingRun

DESCRIPTOR_SIZE = 12
DESCRIPTOR_NAME = "tiny"
SAMPLE_COUNT = 16
# A grid small enough to train on the processor in a test, on the same kind of axis as the real one.
GEOMETRY = log_frequency_geometry().model_copy(
    update={"bins_per_octave": 12, "band_count": 24, "maximum_shift_semitones": 4.0, "time_columns": 8}
)
ROWS, COLUMNS = GEOMETRY.grid_shape


def _cache(directory: Path) -> GridCache:
    generator = np.random.default_rng(0)
    grids = np.zeros((SAMPLE_COUNT, 1, ROWS, COLUMNS), dtype=np.float16)
    for position in range(SAMPLE_COUNT):
        grids[position, 0, 4 + position % 6 * 4 : 8 + position % 6 * 4] = 1.0
        grids[position, 0] = np.clip(grids[position, 0] + generator.normal(0.0, 0.05, (ROWS, COLUMNS)), 0.0, 1.0)
    directory.mkdir(parents=True, exist_ok=True)
    np.save(directory / GRIDS_FILE_NAME, grids)
    durations = np.zeros((SAMPLE_COUNT, 1), dtype=np.float32)
    np.save(directory / DURATIONS_FILE_NAME, durations)
    hashes = [format(position + 1, "064x") for position in range(SAMPLE_COUNT)]
    (directory / HASHES_FILE_NAME).write_text("\n".join(hashes), encoding="utf-8")
    description = GridCacheDescription(
        canonicalizer="log_frequency",
        geometry=GEOMETRY,
        bands_per_semitone=12,
        band_count=ROWS,
        time_columns=COLUMNS,
        sample_count=SAMPLE_COUNT,
        view_count=0,
        view_range_semitones=0.0,
        random_seed=0,
    )
    (directory / DESCRIPTION_FILE_NAME).write_text(description.model_dump_json(), encoding="utf-8")
    return open_grid_cache(directory)


def _descriptor(library_root: Path) -> LearnedDescriptor:
    torch.manual_seed(0)
    shape = DescriptorShape(
        band_count=ROWS, time_columns=COLUMNS, width=4, stage_count=2, embedding_size=DESCRIPTOR_SIZE
    )
    description = DescriptorDescription(
        canonicalizer="log_frequency",
        geometry=GEOMETRY,
        bands_per_semitone=1,
        shape=shape,
        teacher_experiment_id=4,
        epochs=1,
        trained_sample_count=8,
        best_validation_loss=0.5,
    )
    model = GridDescriptor(shape).eval()
    save_descriptor(descriptor_path(library_root, name=DESCRIPTOR_NAME), model, description)
    return LearnedDescriptor(
        model=model,
        description=description,
        canonicalizer=canonicalizer_for_geometry(GEOMETRY),
        device=torch.device("cpu"),
    )


def _corpus(tmp_path: Path) -> CodecCorpus:
    return CodecCorpus(
        cache=_cache(tmp_path / "cache" / "grids" / "tiny"),
        library_root=tmp_path,
        descriptor=_descriptor(tmp_path),
        descriptor_name=DESCRIPTOR_NAME,
        descriptor_sha256=file_sha256(descriptor_path(tmp_path, name=DESCRIPTOR_NAME)),
    )


def _settings(layout: ResidualLayout = ResidualLayout.VECTOR) -> CodecTrainingSettings:
    return CodecTrainingSettings(
        run=RunSettings(epochs=2, batch_size=4, learning_rate=1e-3, worker_count=0, random_seed=0),
        residual_size=4,
        layout=layout,
        width=4,
        prior_warmup_steps=2,
        validation_share=0.25,
    )


def _module(corpus: CodecCorpus, settings: CodecTrainingSettings) -> CodecTrainingModule:
    torch.manual_seed(0)
    return CodecTrainingModule(
        ConditionedCodecShape(
            band_count=ROWS,
            time_columns=COLUMNS,
            descriptor_size=DESCRIPTOR_SIZE,
            residual_size=settings.residual_size,
            width=settings.width,
            layout=settings.layout,
        ),
        descriptor=ConditioningDescriptor(network=corpus.descriptor.model, sha256=corpus.descriptor_sha256),
        learning_rate=settings.run.learning_rate,
        weights=settings.weights,
        prior_warmup_steps=settings.prior_warmup_steps,
    )


def test_reconstruction_reads_the_grid_at_three_resolutions_and_a_matching_grid_costs_nothing() -> None:
    grid = torch.rand(2, 64, 16)

    assert reconstruction_error(grid, grid).item() == pytest.approx(0.0)
    assert reconstruction_error(grid, torch.zeros_like(grid)) > 0.0


def test_the_prior_is_met_by_a_unit_gaussian_and_missed_by_a_shifted_one() -> None:
    zeros = torch.zeros(3, 4)

    assert prior_divergence(zeros, zeros).item() == pytest.approx(0.0)
    assert prior_divergence(torch.ones(3, 4), zeros) > 0.0


def test_the_prior_counts_for_as_much_of_its_weight_as_the_warm_up_has_reached() -> None:
    grid = torch.rand(2, 64, 16)
    described = torch.nn.functional.normalize(torch.randn(2, DESCRIPTOR_SIZE), dim=-1)
    prediction = CodecPrediction(grid=grid, mean=torch.ones(2, 4), log_variance=torch.zeros(2, 4), described=described)
    weights = CodecLossWeights(reconstruction=1.0, prior=1.0, cycle=0.0)

    cold = codec_loss(prediction, target=grid, descriptor=described, weights=weights, prior_share=0.0)
    warm = codec_loss(prediction, target=grid, descriptor=described, weights=weights, prior_share=1.0)

    assert cold.total.item() == pytest.approx(0.0, abs=1e-6)
    assert warm.total.item() == pytest.approx(warm.prior.item())


def test_a_pooled_cache_is_refused_as_a_codec_corpus(tmp_path: Path) -> None:
    from tests.samplemorph.training.conftest import write_grid_cache

    with pytest.raises(TrainingRefused, match="was pooled; build it with --bands-per-semitone"):
        CodecCorpus(
            cache=write_grid_cache(tmp_path / "cache" / "grids" / "pooled", sample_count=4),
            library_root=tmp_path,
            descriptor=_descriptor(tmp_path),
            descriptor_name=DESCRIPTOR_NAME,
            descriptor_sha256="0" * 64,
        )


@pytest.mark.parametrize("layout", tuple(ResidualLayout))
def test_a_short_run_logs_the_watched_metric_and_writes_a_codec_that_loads(
    tmp_path: Path, layout: ResidualLayout
) -> None:
    corpus = _corpus(tmp_path)
    settings = _settings(layout)
    module = _module(corpus, settings)
    data = CodecDataModule(corpus, settings=settings)
    run = RecordingRun()
    path = tmp_path / "models" / "codecs" / "tiny.pt"
    export = BestEpochExport(
        path=path,
        monitored=CODEC_MONITORED_METRIC,
        tracker=run,
        writer=CodecWriter(module, path, corpus, data.training_sample_count, 0),
    )
    trainer = Trainer(
        max_epochs=settings.run.epochs,
        accelerator="cpu",
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        callbacks=[export],
    )

    trainer.fit(module, datamodule=data)

    assert CODEC_MONITORED_METRIC in trainer.logged_metrics
    assert CODEC_VALIDATION_RECONSTRUCTION in trainer.logged_metrics
    assert data.training_sample_count + data.validation_sample_count == SAMPLE_COUNT
    assert run.artifacts and set(run.artifacts) == {path}
    codec = load_conditioned_codec(path, library_root=tmp_path, device=torch.device("cpu"))
    assert codec.description.descriptor == DESCRIPTOR_NAME
    assert codec.model.shape.layout is layout
    assert codec.latent_size == DESCRIPTOR_SIZE + codec.model.shape.residual_length
    assert settings.as_parameters()["layout"] == layout.value


def test_the_descriptor_rides_along_frozen(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    module = _module(corpus, _settings())

    assert all(not parameter.requires_grad for parameter in module.descriptor.parameters())
    assert all(parameter.requires_grad for parameter in module.model.parameters())


def test_a_codec_run_resumed_beside_another_descriptor_is_refused(tmp_path: Path) -> None:
    """The frozen descriptor's weights ride in the checkpoint, so resuming beside another file would mix the two."""
    module = _module(_corpus(tmp_path), _settings())
    checkpoint: dict[str, object] = {}
    module.on_save_checkpoint(checkpoint)
    module.on_load_checkpoint(checkpoint)

    with pytest.raises(ResumeRefused, match="another descriptor file"):
        module.on_load_checkpoint({DESCRIPTOR_DIGEST_KEY: "0" * 64})


def test_a_cache_too_small_for_one_batch_names_the_flag_that_shrinks_it(tmp_path: Path) -> None:
    settings = CodecTrainingSettings(
        run=RunSettings(epochs=1, batch_size=64, learning_rate=1e-3, worker_count=0, random_seed=0),
        residual_size=4,
        layout=ResidualLayout.VECTOR,
        width=4,
        prior_warmup_steps=2,
        validation_share=0.25,
    )

    with pytest.raises(TrainingDataShortfall, match="fill no batch of 64; set --batch"):
        CodecDataModule(_corpus(tmp_path), settings=settings)
