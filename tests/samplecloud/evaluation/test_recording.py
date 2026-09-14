from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from sqlalchemy import Connection

from samplecloud.evaluation.harness import evaluate_experiment
from samplecloud.evaluation.recording import record_report, run_name_for
from samplecloud.evaluation.settings import EvaluationSettings
from samplecloud.evaluation.transposition import OffsetRetrieval, TranspositionRetrieval
from tests.samplecloud.evaluation.conftest import SeededCatalog, label_catalog

SETTINGS = EvaluationSettings(random_seed=0, fold_count=4, neighbor_count=3)


@dataclass
class RecordingRun:
    """A TrackedRun keeping what it was told, so a test can read it back."""

    metrics: dict[str, float] = field(default_factory=dict)
    parameters: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)

    @property
    def run_id(self) -> str:
        return "a-run"

    def log_parameters(self, parameters: dict[str, str]) -> None:
        self.parameters.update(parameters)

    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        self.metrics.update(metrics)

    def log_artifact(self, path: Path) -> None:
        self.artifacts.append(path.read_text(encoding="utf-8"))


def test_every_metric_a_report_holds_reaches_the_run(
    connection: Connection, tmp_path: Path, separable_catalog: SeededCatalog
) -> None:
    label_catalog(connection, separable_catalog)
    report = evaluate_experiment(
        connection,
        experiment_id=separable_catalog.experiment_id,
        describer=None,
        settings=SETTINGS,
    )
    run = RecordingRun()

    record_report(report, run)

    assert run.parameters["backend"] == "stub"
    assert run.parameters["experiment_id"] == str(separable_catalog.experiment_id)
    assert {"categories/accuracy", "categories/kick/f1", "notes/single_pitch_auc"} <= set(run.metrics)
    assert {
        "hand_labels/ndcg",
        "hand_labels/snare/average_precision",
        "hand_labels/bass__synth/average_precision",
    } <= set(run.metrics)
    assert "transposition/rank_one_share" not in run.metrics
    assert json.loads(run.artifacts[0])["experiment_id"] == separable_catalog.experiment_id


def test_a_retuning_is_named_by_its_direction_and_size(
    connection: Connection, tmp_path: Path, separable_catalog: SeededCatalog
) -> None:
    """A metric name carries no sign, so an offset reads as up or down by so many semitones."""
    report = evaluate_experiment(
        connection,
        experiment_id=separable_catalog.experiment_id,
        describer=None,
        settings=SETTINGS,
    )
    offsets = tuple(
        OffsetRetrieval(
            semitone_offset=offset, trial_count=4, rank_one_share=0.5, close_rank_share=0.75, median_rank=2.0
        )
        for offset in (-12.0, 7.0)
    )
    stubbed = replace(
        report,
        transposition=TranspositionRetrieval(
            offsets=offsets, probe_sample_count=4, unavailable_probe_count=0, catalog_sample_count=32, random_seed=0
        ),
    )
    run = RecordingRun()

    record_report(stubbed, run)

    assert run.metrics["transposition/down_12/rank_one_share"] == 0.5
    assert run.metrics["transposition/up_7/median_rank"] == 2.0


def test_a_run_is_named_after_the_descriptor_and_its_experiment() -> None:
    assert run_name_for(backend_name="librosa", experiment_id=3) == "librosa-3"
