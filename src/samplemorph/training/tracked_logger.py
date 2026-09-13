from __future__ import annotations

from typing import Any, Final

from lightning.pytorch.loggers import Logger

from samplecore.tracking import TrackedRun

LOGGER_NAME: Final[str] = "tracked-run"
EPOCH_METRIC: Final[str] = "epoch"


class TrackedRunLogger(Logger):
    """Routes what the trainer measures into the run the command opened.

    The trainer reports metrics to whichever loggers it holds, and this one forwards them to a
    `TrackedRun`. Going through the run rather than through a tracker of the trainer's own is what
    keeps a pass to a single record: the parameters the command wrote and the metrics the epochs
    produced land under one identity, and a pass nobody is recording costs the same calls and keeps
    nothing.

    This is also what holds the tracking library out of the training code. What the trainer sees is
    a logger; which store it reaches is the run's business.
    """

    def __init__(self, run: TrackedRun) -> None:
        super().__init__()
        self._run = run

    @property
    def name(self) -> str:
        return LOGGER_NAME

    @property
    def version(self) -> str:
        return self._run.run_id

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        self._run.log_metrics({name: float(value) for name, value in metrics.items()}, step=step or 0)

    def log_hyperparams(self, params: dict[str, Any] | Any, *args: Any, **kwargs: Any) -> None:
        """Accept what the trainer knows about the model, which the command already recorded.

        A run's parameters are written once by the command that opened it, from the settings a
        person passed rather than from what the trainer inferred, so the two never disagree.
        """
