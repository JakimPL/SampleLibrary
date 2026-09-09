from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import DataLoader

from samplecore.models.sample import Sample
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.geometry import fourier_bin_count
from samplemorph.training.phase_dataset import (
    DEFAULT_CROP_FRAMES,
    PhaseBatchItem,
    PhaseTrainingSet,
    limit_worker_threads,
)
from samplemorph.training.phase_losses import AnalysisWindow, LossWeights, phase_loss
from samplemorph.vocoders.phase_model import (
    DEFAULT_CHANNELS,
    PhaseModel,
    PhaseModelShape,
)

DEFAULT_BATCH_SIZE: Final[int] = 32
DEFAULT_EPOCHS: Final[int] = 20
DEFAULT_LEARNING_RATE: Final[float] = 2e-4
DEFAULT_WORKER_COUNT: Final[int] = 8
DEFAULT_VALIDATION_SHARE: Final[float] = 0.05
PROGRESS_INTERVAL: Final[int] = 100
GRADIENT_CLIP: Final[float] = 1.0
PREFETCH_BATCHES: Final[int] = 2
WORKER_START_METHOD: Final[str] = "spawn"

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingSettings:
    """How one training run is shaped, recorded beside the weights it produces."""

    epochs: int = DEFAULT_EPOCHS
    batch_size: int = DEFAULT_BATCH_SIZE
    learning_rate: float = DEFAULT_LEARNING_RATE
    crop_frames: int = DEFAULT_CROP_FRAMES
    channels: int = DEFAULT_CHANNELS
    worker_count: int = DEFAULT_WORKER_COUNT
    random_seed: int = 0
    weights: LossWeights = field(default_factory=LossWeights)


@dataclass(frozen=True)
class PhaseCorpus:
    """The material a phase model is taught from: which samples, read from where, on which axis.

    The axis travels with the samples because the magnitudes a model learns from are produced by it,
    so a model is only ever valid for the canonicalizer it was taught on.
    """

    samples: tuple[Sample, ...]
    library_root: Path
    canonicalizer: Canonicalizer
    canonicalizer_name: str


@dataclass(frozen=True)
class EpochReport:
    """What one epoch did, on the part it trained on and the part it was held against."""

    epoch: int
    training_loss: float
    validation_loss: float
    validation_gradient: float
    validation_spectral: float
    seconds: float


@dataclass(frozen=True)
class TrainedPhaseModel:
    """A fitted phase model together with the run that produced it."""

    model: PhaseModel
    shape: PhaseModelShape
    canonicalizer_name: str
    settings: TrainingSettings
    history: tuple[EpochReport, ...]

    @property
    def best_validation_loss(self) -> float:
        return min(report.validation_loss for report in self.history) if self.history else float("inf")


@dataclass(frozen=True)
class TrainingRun:
    """Everything one epoch of training reaches for, gathered so a step reads as one thing."""

    model: PhaseModel
    optimizer: torch.optim.Optimizer
    schedule: torch.optim.lr_scheduler.LRScheduler
    window: AnalysisWindow
    device: torch.device
    settings: TrainingSettings


def train_phase_model(
    corpus: PhaseCorpus,
    *,
    settings: TrainingSettings,
    device: torch.device,
    on_improvement: Callable[[PhaseModel, EpochReport], None] | None = None,
) -> TrainedPhaseModel:
    """Teach a model the phase that belongs with the magnitudes this pipeline produces.

    The samples are split once into a part trained on and a part held back, so an epoch's validation
    figure describes material the weights never saw.

    `on_improvement` is called after any epoch that beats every epoch before it. A run over the whole
    catalog takes hours, so the best weights so far reach disk as they are found rather than only at
    the end -- which survives an interruption and lets a run be listened to while it is still going.

    Raises:
        ValueError: too few samples to hold any back for validation.
    """
    torch.manual_seed(settings.random_seed)
    geometry = corpus.canonicalizer.geometry
    training_samples, validation_samples = _split(corpus.samples, random_seed=settings.random_seed)
    _logger.info(
        "Training on %d samples, holding %d back, at %d frames a crop.",
        len(training_samples),
        len(validation_samples),
        settings.crop_frames,
    )
    shape = PhaseModelShape(bin_count=fourier_bin_count(fft_length=geometry.fft_length), channels=settings.channels)
    model = PhaseModel(shape).to(device)
    training_loader = _loader(training_samples, corpus=corpus, settings=settings, shuffle=True)
    validation_loader = _loader(validation_samples, corpus=corpus, settings=settings, shuffle=False)
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings.learning_rate)
    run = TrainingRun(
        model=model,
        optimizer=optimizer,
        schedule=torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=max(settings.epochs * len(training_loader), 1)
        ),
        window=AnalysisWindow(
            fft_length=geometry.fft_length,
            hop_length=geometry.hop_length,
            taper=torch.hann_window(geometry.fft_length, device=device),
        ),
        device=device,
        settings=settings,
    )

    history: list[EpochReport] = []
    best_loss = float("inf")
    for epoch in range(1, settings.epochs + 1):
        started = time.monotonic()
        training_loss = _train_one_epoch(training_loader, run=run, epoch=epoch)
        validation_loss, gradient, spectral = _validate(validation_loader, run=run)
        history.append(
            EpochReport(
                epoch=epoch,
                training_loss=training_loss,
                validation_loss=validation_loss,
                validation_gradient=gradient,
                validation_spectral=spectral,
                seconds=time.monotonic() - started,
            )
        )
        _logger.info(
            "Epoch %d/%d: training %.4f, validation %.4f (gradient %.4f, spectral %.4f), %.0fs.",
            epoch,
            settings.epochs,
            training_loss,
            validation_loss,
            gradient,
            spectral,
            history[-1].seconds,
        )
        if validation_loss < best_loss:
            best_loss = validation_loss
            if on_improvement is not None:
                on_improvement(model, history[-1])

    return TrainedPhaseModel(
        model=model,
        shape=shape,
        canonicalizer_name=corpus.canonicalizer_name,
        settings=settings,
        history=tuple(history),
    )


def _split(samples: tuple[Sample, ...], *, random_seed: int) -> tuple[tuple[Sample, ...], tuple[Sample, ...]]:
    """Draw a held-back part once, so every epoch is judged on the same unseen material.

    Raises:
        ValueError: the body is too small to hold any of it back.
    """
    holdout = max(round(len(samples) * DEFAULT_VALIDATION_SHARE), 1)
    if len(samples) <= holdout:
        raise ValueError(f"{len(samples)} samples leave nothing to train on once {holdout} are held back")

    order = np.random.default_rng(random_seed).permutation(len(samples))
    return (
        tuple(samples[position] for position in order[holdout:]),
        tuple(samples[position] for position in order[:holdout]),
    )


def _loader(
    samples: tuple[Sample, ...], *, corpus: PhaseCorpus, settings: TrainingSettings, shuffle: bool
) -> DataLoader[PhaseBatchItem]:
    """Build the loader that feeds one part of the corpus, on a transport a long run survives.

    Each worker starts as a fresh interpreter, so it holds the roughly 730 MB its own imports and
    working arrays need and nothing else. That keeps a worker's memory its own, and it keeps the
    weights on the GPU out of the picture entirely: the model reaches the device before the first
    batch is asked for, and a worker started fresh begins after that with an address space of its
    own rather than a copy of the trainer's.

    Batches travel as ordinary pageable memory, and each worker holds `PREFETCH_BATCHES` of them
    ready. Together those bound what a run has in flight at any moment, which is what lets a whole
    catalog pass leave the rest of the machine the memory it is using.
    """
    dataset = PhaseTrainingSet(
        samples,
        library_root=corpus.library_root,
        canonicalizer=corpus.canonicalizer,
        crop_frames=settings.crop_frames,
        random_seed=settings.random_seed,
    )
    parallel = settings.worker_count > 0
    return DataLoader(
        dataset,
        batch_size=settings.batch_size,
        shuffle=shuffle,
        num_workers=settings.worker_count,
        drop_last=shuffle,
        persistent_workers=parallel,
        worker_init_fn=limit_worker_threads if parallel else None,
        prefetch_factor=PREFETCH_BATCHES if parallel else None,
        multiprocessing_context=WORKER_START_METHOD if parallel else None,
    )


def _batch_loss(batch: tuple[Tensor, Tensor, Tensor, Tensor], *, run: TrainingRun) -> tuple[Tensor, Tensor, Tensor]:
    magnitude, cosine, sine, frame_offset = (part.to(run.device, non_blocking=True) for part in batch)
    parts = phase_loss(
        run.model(magnitude, frame_offset=frame_offset),
        torch.stack((cosine, sine), dim=1),
        magnitude,
        window=run.window,
        weights=run.settings.weights,
    )
    return parts.total, parts.gradient, parts.spectral


def _train_one_epoch(loader: DataLoader[PhaseBatchItem], *, run: TrainingRun, epoch: int) -> float:
    run.model.train()
    total, batches = 0.0, 0
    for index, batch in enumerate(loader, start=1):
        loss, _, _ = _batch_loss(batch, run=run)
        # torch's stubs leave Tensor.backward untyped, so mypy reads the call as untyped.
        loss.backward()  # type: ignore[no-untyped-call]
        torch.nn.utils.clip_grad_norm_(run.model.parameters(), max_norm=GRADIENT_CLIP)
        run.optimizer.step()
        run.optimizer.zero_grad(set_to_none=True)
        run.schedule.step()
        total += float(loss.detach())
        batches += 1
        if index % PROGRESS_INTERVAL == 0:
            _logger.info("  epoch %d, batch %d: running loss %.4f", epoch, index, total / batches)
    return total / max(batches, 1)


@torch.no_grad()
def _validate(loader: DataLoader[PhaseBatchItem], *, run: TrainingRun) -> tuple[float, float, float]:
    run.model.eval()
    totals = np.zeros(3)
    batches = 0
    for batch in loader:
        loss, gradient, spectral = _batch_loss(batch, run=run)
        totals += np.array([float(loss), float(gradient), float(spectral)])
        batches += 1
    divided = totals / max(batches, 1)
    return float(divided[0]), float(divided[1]), float(divided[2])
