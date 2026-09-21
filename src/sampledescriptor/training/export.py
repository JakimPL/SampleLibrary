from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from lightning.pytorch import Callback, LightningModule, Trainer

from samplecore.tracking import TrackedRun

BEST_LOSS_STATE: Final[str] = "best_validation_loss"


@dataclass(frozen=True)
class ExportRecord:
    """How far a run had come when its weights were written, and how well they did."""

    epochs: int
    best_validation_loss: float


class ModelWriter(Protocol):
    """Writes the weights a run has reached, described by the record of how it got there."""

    def __call__(self, record: ExportRecord) -> None: ...


class BestEpochExport(Callback):
    """Writes a run's deliverable each time an epoch beats every epoch before it.

    This is the file a model is read from rather than the run's resume point: the trainer's own
    checkpoint carries what resuming needs, and the writer carries the network and the description
    that rebuilds it. Each write also reaches the run's record, so the weights an epoch's numbers
    describe are stored beside them. The best score so far travels in the resume point, so a
    continued run exports only an epoch that beats every epoch before the interruption as well.
    """

    def __init__(self, *, path: Path, monitored: str, tracker: TrackedRun, writer: ModelWriter) -> None:
        super().__init__()
        self._path = path
        self._monitored = monitored
        self._tracker = tracker
        self._writer = writer
        self._best_loss = float("inf")

    @property
    def monitored(self) -> str:
        return self._monitored

    @property
    def best_loss(self) -> float:
        return self._best_loss

    @property
    def path(self) -> Path:
        return self._path

    @property
    def state_key(self) -> str:
        return self._generate_state_key(monitored=self._monitored)

    def state_dict(self) -> dict[str, Any]:
        return {BEST_LOSS_STATE: self._best_loss}

    def load_state_dict(self, state_dict: dict[str, Any]) -> None:
        self._best_loss = float(state_dict[BEST_LOSS_STATE])

    def on_validation_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        if trainer.sanity_checking:
            return

        reached = trainer.callback_metrics.get(self._monitored)
        if reached is None or float(reached) >= self._best_loss:
            return

        self._best_loss = float(reached)
        self._writer(ExportRecord(epochs=trainer.current_epoch + 1, best_validation_loss=self._best_loss))
        self._tracker.log_artifact(self._path)
