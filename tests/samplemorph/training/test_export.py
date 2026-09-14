from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
import torch

from samplecore.tracking.silent import SilentRun
from samplemorph.training.export import BEST_LOSS_STATE, BestEpochExport, ExportRecord

MONITORED = "validation/loss"


@dataclass
class RecordingWriter:
    records: list[ExportRecord] = field(default_factory=list)

    def __call__(self, record: ExportRecord) -> None:
        self.records.append(record)


@dataclass
class ValidatedTrainer:
    """The two things an export reads from a trainer at the end of a validation pass."""

    callback_metrics: dict[str, torch.Tensor]
    current_epoch: int
    sanity_checking: bool = False


def _validated(export: BestEpochExport, loss: float, *, epoch: int) -> None:
    trainer = ValidatedTrainer(callback_metrics={MONITORED: torch.tensor(loss)}, current_epoch=epoch)
    export.on_validation_end(trainer, None)  # type: ignore[arg-type]


def _export(writer: RecordingWriter) -> BestEpochExport:
    return BestEpochExport(path=Path("model.pt"), monitored=MONITORED, tracker=SilentRun(), writer=writer)


def test_the_best_score_travels_through_the_export_state() -> None:
    before = _export(RecordingWriter())
    _validated(before, 0.5, epoch=0)
    after = _export(RecordingWriter())

    after.load_state_dict(before.state_dict())

    assert after.state_dict() == {BEST_LOSS_STATE: 0.5}
    assert after.state_key == before.state_key


def test_a_restored_export_writes_only_an_epoch_that_beats_the_score_before_the_interruption() -> None:
    writer = RecordingWriter()
    export = _export(writer)
    export.load_state_dict({BEST_LOSS_STATE: 0.5})

    _validated(export, 0.7, epoch=4)
    _validated(export, 0.4, epoch=5)

    assert [record.epochs for record in writer.records] == [6]
    assert export.best_loss == pytest.approx(0.4)
