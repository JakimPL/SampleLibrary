from __future__ import annotations

import logging
import time
from typing import Final

from lightning.pytorch import Callback, LightningModule, Trainer
from lightning.pytorch.utilities.types import STEP_OUTPUT

PROGRESS_INTERVAL_SECONDS: Final[float] = 30.0
VALIDATION_PREFIX: Final[str] = "validation/"

_logger = logging.getLogger(__name__)


class ProgressLines(Callback):
    """Reports a run's progress as log lines, so a run read through a pipe or a log file shows how far it is.

    A progress bar draws itself on a terminal alone. This callback writes one line every
    `interval_seconds` of training with the epoch, the batch reached, the rate and the readings
    the module puts on the bar, and one line at the end of each validation with every validation
    reading, in the same log every command writes to.
    """

    def __init__(self, *, interval_seconds: float = PROGRESS_INTERVAL_SECONDS) -> None:
        super().__init__()
        self._interval_seconds = interval_seconds
        self._last_time = 0.0
        self._last_batch = 0

    def on_train_epoch_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        self._last_time = time.monotonic()
        self._last_batch = 0

    def on_train_batch_end(
        self, trainer: Trainer, pl_module: LightningModule, outputs: STEP_OUTPUT, batch: object, batch_idx: int
    ) -> None:
        now = time.monotonic()
        if now - self._last_time < self._interval_seconds:
            return
        batches = batch_idx + 1
        rate = (batches - self._last_batch) / max(now - self._last_time, 1e-9)
        readings = ", ".join(f"{key} {float(value):.5g}" for key, value in trainer.progress_bar_metrics.items())
        _logger.info(
            "Epoch %d of %s: batch %d of %d at %.1f per second; %s",
            trainer.current_epoch + 1,
            trainer.max_epochs,
            batches,
            int(trainer.num_training_batches),
            rate,
            readings,
        )
        self._last_time = now
        self._last_batch = batches

    def on_validation_epoch_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        if trainer.sanity_checking:
            return
        readings = ", ".join(
            f"{key} {float(value):.5g}"
            for key, value in trainer.callback_metrics.items()
            if key.startswith(VALIDATION_PREFIX)
        )
        _logger.info("Epoch %d of %s validated: %s", trainer.current_epoch + 1, trainer.max_epochs, readings)
