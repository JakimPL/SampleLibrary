from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime

from samplecloud.evaluation.categories import CategoryAgreement
from samplecloud.evaluation.hand_labels import HandLabelAgreement
from samplecloud.evaluation.notes import NoteAgreement
from samplecloud.evaluation.settings import EvaluationScope
from samplecloud.evaluation.transposition import TranspositionRetrieval


@dataclass(frozen=True)
class EvaluationReport:
    """Everything one evaluation pass measured about one experiment's descriptor.

    The four metrics answer four separate questions -- whether pitch moves a descriptor, whether it
    groups what a keyword calls alike, whether it groups what the library plays alike, and whether
    it groups what a person labeled alike -- and each carries its own coverage, so a reader sees
    which part of the catalog each score describes. `scope` and `corpus_digest` name the samples the
    pass scored, so two reports read side by side say whether they scored one corpus.

    The report holds numbers and writes nothing. A run tracker, when one is chosen, reads this tree
    rather than the harness reading the tracker.
    """

    experiment_id: int
    backend_name: str
    scope: EvaluationScope
    corpus_digest: str
    sample_count: int
    random_seed: int
    evaluated_at: datetime
    transposition: TranspositionRetrieval | None
    categories: CategoryAgreement | None
    notes: NoteAgreement | None
    hand_labels: HandLabelAgreement | None


def report_json(report: EvaluationReport) -> str:
    """The report as indented JSON, for a file a person reads and a tracker later ingests.

    A score a metric could not read, such as a correlation over a constant target, is written as null.
    """
    return json.dumps(_with_null_scores(asdict(report)), indent=2, default=str, allow_nan=False)


def _with_null_scores(value: object) -> object:
    match value:
        case float() if math.isnan(value):
            return None
        case dict():
            return {key: _with_null_scores(item) for key, item in value.items()}
        case list() | tuple():
            return [_with_null_scores(item) for item in value]
        case _:
            return value
