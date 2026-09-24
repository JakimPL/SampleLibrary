from __future__ import annotations

from pathlib import Path

import pytest

from samplecore.progress import PROGRESS_FILE_ENVIRONMENT_VARIABLE, ProgressBar, read_progress, tracked


def test_a_tracked_pass_yields_every_item_and_reports_it_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "step.progress.json"
    monkeypatch.setenv(PROGRESS_FILE_ENVIRONMENT_VARIABLE, str(report_path))

    items = list(tracked(range(5), total=5, label="Counting"))

    report = read_progress(report_path)
    assert items == [0, 1, 2, 3, 4]
    assert report is not None
    assert (report.label, report.done, report.total) == ("Counting", 5, 5)


def test_a_bar_reports_its_start_before_any_item_finishes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_path = tmp_path / "step.progress.json"
    monkeypatch.setenv(PROGRESS_FILE_ENVIRONMENT_VARIABLE, str(report_path))

    with ProgressBar(total=3, label="Reading"):
        report = read_progress(report_path)

    assert report is not None
    assert (report.done, report.total) == (0, 3)


def test_a_pass_run_by_hand_writes_no_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PROGRESS_FILE_ENVIRONMENT_VARIABLE, raising=False)

    assert list(tracked(["a"], total=1, label="Alone")) == ["a"]
    assert read_progress(tmp_path / "absent.json") is None
