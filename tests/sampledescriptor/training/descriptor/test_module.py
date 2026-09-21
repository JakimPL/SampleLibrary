from __future__ import annotations

from pathlib import Path

import torch
from lightning.pytorch import Trainer

from sampledescriptor.descriptors.learned import load_descriptor
from sampledescriptor.training.descriptor.data import DescriptorCorpus, DescriptorDataModule
from sampledescriptor.training.descriptor.export import DescriptorWriter
from sampledescriptor.training.descriptor.module import DescriptorTrainingModule
from sampledescriptor.training.descriptor.settings import DescriptorTrainingSettings
from sampledescriptor.training.export import BestEpochExport
from sampledescriptor.training.metrics import (
    DESCRIPTOR_MONITORED_METRIC,
    DESCRIPTOR_TRAINING_LABELS,
    DESCRIPTOR_TRAINING_LOSS,
    DESCRIPTOR_VALIDATION_NDCG,
    DESCRIPTOR_VALIDATION_RETUNE_RANK_ONE,
)
from sampledescriptor.training.run.settings import RunSettings
from tests.sampledescriptor.training.test_tracked_logger import RecordingRun


def _data(corpus: DescriptorCorpus) -> DescriptorDataModule:
    settings = DescriptorTrainingSettings(
        run=RunSettings(batch_size=8, worker_count=0, random_seed=0), labeled_per_batch=2, validation_gallery=4
    )
    return DescriptorDataModule(corpus, settings=settings)


def test_the_metric_the_checkpoint_watches_is_one_the_module_logs(
    descriptor_module: DescriptorTrainingModule, descriptor_corpus: DescriptorCorpus
) -> None:
    run = RecordingRun()
    trainer = Trainer(
        max_epochs=1,
        limit_train_batches=1,
        accelerator="cpu",
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
    )

    trainer.fit(descriptor_module, datamodule=_data(descriptor_corpus))

    logged = set(trainer.logged_metrics)
    assert DESCRIPTOR_MONITORED_METRIC in logged
    assert {DESCRIPTOR_TRAINING_LABELS, DESCRIPTOR_VALIDATION_RETUNE_RANK_ONE, DESCRIPTOR_VALIDATION_NDCG} <= logged
    assert any(name.startswith(DESCRIPTOR_TRAINING_LOSS) for name in logged)
    assert not run.metrics


def test_a_teacher_that_separates_the_sounds_is_learned_within_a_few_epochs(
    descriptor_module: DescriptorTrainingModule, descriptor_corpus: DescriptorCorpus
) -> None:
    """The synthetic cache is six sounds with a teacher already telling them apart, so a short run must find it."""
    trainer = Trainer(
        max_epochs=12, accelerator="cpu", logger=False, enable_checkpointing=False, enable_progress_bar=False
    )

    trainer.fit(descriptor_module, datamodule=_data(descriptor_corpus))

    assert float(trainer.logged_metrics[DESCRIPTOR_VALIDATION_RETUNE_RANK_ONE]) > 0.5
    assert float(trainer.logged_metrics[DESCRIPTOR_VALIDATION_NDCG]) > 0.5


def test_the_export_writes_a_descriptor_that_loads_and_reaches_the_run(
    descriptor_module: DescriptorTrainingModule, descriptor_corpus: DescriptorCorpus, tmp_path: Path
) -> None:
    run = RecordingRun()
    path = tmp_path / "models" / "descriptors" / "tiny.pt"
    export = BestEpochExport(
        path=path,
        monitored=DESCRIPTOR_MONITORED_METRIC,
        tracker=run,
        writer=DescriptorWriter(descriptor_module, path, descriptor_corpus, 20),
    )
    trainer = Trainer(
        max_epochs=1,
        limit_train_batches=1,
        accelerator="cpu",
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        callbacks=[export],
    )

    trainer.fit(descriptor_module, datamodule=_data(descriptor_corpus))

    assert path.is_file()
    assert run.artifacts == [path]
    assert export.best_loss < float("inf")
    loaded = load_descriptor(path, device=torch.device("cpu"))
    assert loaded.description.teacher_experiment_id == descriptor_corpus.teacher_experiment_id
    assert loaded.description.trained_sample_count == 20
