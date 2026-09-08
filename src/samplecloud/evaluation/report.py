from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime

from samplecloud.evaluation.categories import CategoryAgreement
from samplecloud.evaluation.notes import NoteAgreement
from samplecloud.evaluation.transposition import TranspositionRetrieval


@dataclass(frozen=True)
class EvaluationReport:
    """Everything one evaluation pass measured about one experiment's descriptor.

    The three metrics answer three separate questions -- whether pitch moves a descriptor, whether
    it groups what a keyword calls alike, and whether it groups what the library plays alike -- and
    each carries its own coverage, so a reader sees which part of the catalog each score describes.

    The report holds numbers and writes nothing. A run tracker, when one is chosen, reads this tree
    rather than the harness reading the tracker.
    """

    experiment_id: int
    backend_name: str
    sample_count: int
    random_seed: int
    evaluated_at: datetime
    transposition: TranspositionRetrieval | None
    categories: CategoryAgreement | None
    notes: NoteAgreement | None


def report_json(report: EvaluationReport) -> str:
    """The report as indented JSON, for a file a person reads and a tracker later ingests."""
    return json.dumps(asdict(report), indent=2, default=str)
