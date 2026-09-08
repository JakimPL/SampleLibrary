from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecloud.evaluation.cli import _report, main
from samplecloud.evaluation.harness import evaluate_experiment
from samplecloud.evaluation.report import report_json
from samplecloud.evaluation.settings import EvaluationSettings
from samplecloud.evaluation.transposition import OffsetRetrieval, TranspositionRetrieval
from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from tests.samplecloud.evaluation.conftest import SeededCatalog

SETTINGS = EvaluationSettings(random_seed=0, fold_count=4, neighbor_count=3)


def _write_config(tmp_path: Path, database_url: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[library]\nmodule_source_directory = "{tmp_path.as_posix()}"\n'
        f'library_root = "{tmp_path.as_posix()}"\ndatabase_url = "{database_url}"\n',
        encoding="utf-8",
    )
    return config_path


def test_a_pass_without_an_extractor_scores_the_stored_vectors_alone(
    connection: Connection, tmp_path: Path, separable_catalog: SeededCatalog
) -> None:
    """Two of the three metrics read vectors only, so a pass over them needs no audio at all."""
    report = evaluate_experiment(
        connection,
        experiment_id=separable_catalog.experiment_id,
        library_root=tmp_path,
        feature_extractor=None,
        settings=SETTINGS,
    )

    assert report.transposition is None
    assert report.categories is not None
    assert report.notes is not None
    assert report.sample_count == len(separable_catalog.sample_hashes)
    assert report.backend_name == "stub"


def test_an_unknown_experiment_says_so(connection: Connection, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="holds no experiment"):
        evaluate_experiment(
            connection, experiment_id=9999, library_root=tmp_path, feature_extractor=None, settings=SETTINGS
        )


def test_a_report_renders_as_json_a_tracker_can_read(
    connection: Connection, tmp_path: Path, separable_catalog: SeededCatalog
) -> None:
    report = evaluate_experiment(
        connection,
        experiment_id=separable_catalog.experiment_id,
        library_root=tmp_path,
        feature_extractor=None,
        settings=SETTINGS,
    )

    rendered = json.loads(report_json(report))

    assert rendered["backend_name"] == "stub"
    assert rendered["categories"]["per_category"]
    assert rendered["notes"]["targets"]


def test_the_command_writes_the_report_where_it_was_asked_to(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    separable_catalog: SeededCatalog,
) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))
    output = tmp_path / "reports" / "stub.json"

    main(
        [
            "--experiment-id",
            str(separable_catalog.experiment_id),
            "--skip-transposition",
            "--output",
            str(output),
        ]
    )

    written = json.loads(output.read_text())
    assert written["experiment_id"] == separable_catalog.experiment_id
    assert written["transposition"] is None


def test_the_command_reports_an_experiment_extracted_by_an_unknown_backend(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    separable_catalog: SeededCatalog,
) -> None:
    """Retrieval describes audio again, so it needs the very extractor the vectors came from."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    with pytest.raises(ValueError, match="unknown stub backend"):
        main(["--experiment-id", str(separable_catalog.experiment_id)])


def test_the_command_reports_every_metric_it_ran(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    separable_catalog: SeededCatalog,
) -> None:
    """A reader is told which part of the catalog each score describes, beside the score."""
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(_write_config(tmp_path, _database_url)))

    main(["--experiment-id", str(separable_catalog.experiment_id), "--skip-transposition"])

    reported = capsys.readouterr().out
    assert "Category agreement" in reported
    assert "of the catalog" in reported
    assert "Note-event agreement" in reported
    assert "single-pitch AUC" in reported


def test_the_command_reports_retrieval_offset_by_offset(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    separable_catalog: SeededCatalog,
) -> None:
    """Each offset's own difficulty stays visible, which one aggregate share would hide."""
    report = evaluate_experiment(
        connection,
        experiment_id=separable_catalog.experiment_id,
        library_root=tmp_path,
        feature_extractor=None,
        settings=SETTINGS,
    )
    stubbed = replace(
        report,
        transposition=TranspositionRetrieval(
            offsets=(
                OffsetRetrieval(
                    semitone_offset=12.0, trial_count=4, rank_one_share=0.5, close_rank_share=0.75, median_rank=2.0
                ),
            ),
            probe_sample_count=4,
            catalog_sample_count=32,
            random_seed=0,
        ),
    )

    with caplog.at_level(logging.INFO):
        _report(stubbed)

    assert "Transposition retrieval over 4 probes" in caplog.text
    assert "+12 st" in caplog.text
