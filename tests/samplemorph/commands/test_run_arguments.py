from __future__ import annotations

import logging
import math
from pathlib import Path

import pytest

from samplemorph.commands.run_arguments import report_outcome, train_and_report
from samplemorph.training.refusals import TrainingDataShortfall
from samplemorph.training.runs import TrainingOutcome


def _outcome(tmp_path: Path, *, best_validation_loss: float) -> TrainingOutcome:
    return TrainingOutcome(
        best_validation_loss=best_validation_loss,
        epochs_completed=2,
        model_path=tmp_path / "model.pt",
        resume_path=tmp_path / "resume.ckpt",
    )


def test_a_run_with_no_validated_epoch_ends_as_a_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(SystemExit) as raised, caplog.at_level(logging.INFO):
        report_outcome(_outcome(tmp_path, best_validation_loss=math.inf))

    assert raised.value.code == 1
    assert "nothing was written" in caplog.text


def test_a_run_that_exported_an_epoch_reports_where_it_went(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        report_outcome(_outcome(tmp_path, best_validation_loss=0.25))

    assert "scored 0.2500" in caplog.text


def test_a_run_that_cannot_go_ahead_ends_with_one_message(caplog: pytest.LogCaptureFixture) -> None:
    def refused() -> TrainingOutcome:
        raise TrainingDataShortfall("3 training samples fill no batch of 8")

    with pytest.raises(SystemExit) as raised, caplog.at_level(logging.INFO):
        train_and_report(refused)

    assert raised.value.code == 1
    assert "Trained nothing: 3 training samples fill no batch of 8." in caplog.text
