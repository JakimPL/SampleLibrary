from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime

from samplecore.config import load_config
from samplecore.progress import ProgressReport
from samplelibrary.pipeline.events import (
    AttemptEnded,
    AttemptStarted,
    EventFile,
    RunEnded,
    RunStarted,
    StepDecided,
)
from samplelibrary.pipeline.layout import PipelineLayout, RunPaths
from samplelibrary.pipeline.results import AttemptOutcome, RunOutcome, StepVerdict

FAILING_TARGET = "all"


def main() -> None:
    """Record one run over three steps the way `samplelibrary pipeline run` does; the `all` target fails its second step."""
    target = sys.argv[1]
    config = load_config()
    run = RunPaths.opened_under(PipelineLayout(config.library_root))
    events = EventFile(run.events)
    events.emit(RunStarted(run_id=uuid.uuid4().hex[:8], targets=(target,), steps=("modules", "thumbnails", "notes")))
    events.emit(StepDecided(step="modules", verdict=StepVerdict.SATISFIED, reasons=()))
    events.emit(StepDecided(step="thumbnails", verdict=StepVerdict.RAN, reasons=("readable samples",)))
    events.emit(AttemptStarted(step="thumbnails", argv=("thumbnails",), log=str(run.log("thumbnails")), scope="s"))
    run.progress("thumbnails").write_text(
        ProgressReport(label="Computing thumbnails", done=7, total=7, updated_at=datetime.now(UTC)).model_dump_json(),
        encoding="utf-8",
    )
    failing = target == FAILING_TARGET
    run.log("thumbnails").write_text("Computing thumbnails\nthe disk is full\n", encoding="utf-8")
    outcome = AttemptOutcome.FAILED if failing else AttemptOutcome.COMPLETED
    events.emit(AttemptEnded(step="thumbnails", outcome=outcome, exit_status=1 if failing else 0))
    events.emit(
        StepDecided(step="notes", verdict=StepVerdict.NOT_REACHED if failing else StepVerdict.SATISFIED, reasons=())
    )
    events.emit(RunEnded(outcome=RunOutcome.STOPPED if failing else RunOutcome.COMPLETED))
    sys.exit(1 if failing else 0)


if __name__ == "__main__":
    main()
