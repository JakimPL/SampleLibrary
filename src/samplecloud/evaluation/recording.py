from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from samplecloud.evaluation.categories import CategoryAgreement
from samplecloud.evaluation.hand_labels import HandLabelAgreement
from samplecloud.evaluation.notes import NoteAgreement
from samplecloud.evaluation.report import EvaluationReport, report_json
from samplecloud.evaluation.settings import EvaluationScope
from samplecloud.evaluation.transposition import TranspositionRetrieval
from samplecore.tracking import TrackedRun

EVALUATION_EXPERIMENT_NAME: Final[str] = "descriptor-evaluation"
REPORT_ARTIFACT_NAME: Final[str] = "report.json"
# An evaluation measures once, so every metric lands at the same step.
REPORT_STEP: Final[int] = 0


def run_name_for(*, backend_name: str, experiment_id: int, scope: EvaluationScope) -> str:
    """The name a recorded evaluation goes by: the descriptor, the experiment it was read from, and the scope it scored."""
    return f"{backend_name}-{experiment_id}-{scope.value}"


def record_report(report: EvaluationReport, tracker: TrackedRun) -> None:
    """Write everything a report holds into the run, so the run alone answers what was measured.

    The headline numbers become metrics under one namespace per question, the identity of the pass
    becomes parameters, and the whole report travels as an artifact for the figures the metric
    namespaces summarize.
    """
    tracker.log_parameters(
        {
            "experiment_id": str(report.experiment_id),
            "backend": report.backend_name,
            "scope": report.scope.value,
            "corpus_digest": report.corpus_digest,
            "sample_count": str(report.sample_count),
            "random_seed": str(report.random_seed),
        }
    )
    metrics: dict[str, float] = {}
    if report.transposition is not None:
        metrics.update(_transposition_metrics(report.transposition))
    if report.categories is not None:
        metrics.update(_category_metrics(report.categories))
    if report.notes is not None:
        metrics.update(_note_metrics(report.notes))
    if report.hand_labels is not None:
        metrics.update(_hand_label_metrics(report.hand_labels))
    tracker.log_metrics(metrics, step=REPORT_STEP)
    with TemporaryDirectory() as directory:
        path = Path(directory) / REPORT_ARTIFACT_NAME
        path.write_text(report_json(report), encoding="utf-8")
        tracker.log_artifact(path)


def _transposition_metrics(retrieval: TranspositionRetrieval) -> dict[str, float]:
    metrics = {
        "transposition/rank_one_share": retrieval.rank_one_share,
        "transposition/median_rank": retrieval.median_rank,
    }
    for offset in retrieval.offsets:
        name = _offset_name(offset.semitone_offset)
        metrics[f"transposition/{name}/rank_one_share"] = offset.rank_one_share
        metrics[f"transposition/{name}/close_rank_share"] = offset.close_rank_share
        metrics[f"transposition/{name}/median_rank"] = offset.median_rank
    return metrics


def _offset_name(semitones: float) -> str:
    """A retuning as a metric name, since a sign is not a character a metric name may carry."""
    direction = "down" if semitones < 0 else "up"
    return f"{direction}_{abs(semitones):g}"


def _category_metrics(agreement: CategoryAgreement) -> dict[str, float]:
    metrics = {
        "categories/accuracy": agreement.accuracy,
        "categories/macro_f1": agreement.macro_f1,
        "categories/coverage": agreement.coverage,
    }
    for score in agreement.per_category:
        metrics[f"categories/{score.category}/f1"] = score.f1
    return metrics


def _note_metrics(agreement: NoteAgreement) -> dict[str, float]:
    metrics = {
        "notes/single_pitch_auc": agreement.single_pitch_auc,
        "notes/coverage": agreement.coverage,
    }
    for score in agreement.targets:
        metrics[f"notes/{score.target}/spearman"] = score.spearman
    for score in agreement.well_struck_targets:
        metrics[f"notes/{score.target}/well_struck_spearman"] = score.spearman
    return metrics


def _hand_label_metrics(agreement: HandLabelAgreement) -> dict[str, float]:
    low, high = agreement.ndcg_interval
    metrics = {
        "hand_labels/ndcg": agreement.ndcg,
        "hand_labels/ndcg_low": low,
        "hand_labels/ndcg_high": high,
        "hand_labels/ndcg_chance": agreement.ndcg_chance,
        "hand_labels/mean_average_precision": agreement.mean_average_precision,
        "hand_labels/precision_at_one": agreement.precision_at_one,
        "hand_labels/precision_at_one_chance": agreement.precision_at_one_chance,
        "hand_labels/coverage": agreement.coverage,
        "hand_labels/labeled_sample_count": float(agreement.labeled_sample_count),
    }
    for score in agreement.per_tag:
        metrics[f"hand_labels/{_tag_name(score.path)}/average_precision"] = score.average_precision
    return metrics


def _tag_name(path: str) -> str:
    """A tag path as a metric name segment, keeping to the characters a metric name may carry."""
    return "".join(character if character.isalnum() or character in "-_." else "_" for character in path.lower())
