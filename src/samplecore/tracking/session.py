from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from samplecore.tracking import TrackedRun
from samplecore.tracking.silent import SilentRun


@contextmanager
def open_run(library_root: Path, *, recorded: bool, experiment_name: str, run_name: str) -> Iterator[TrackedRun]:
    """Open the run a command reports through, kept or discarded as the command was asked.

    Every command that measures something opens one of these and hands it to the work, so a pass
    reads the same either way and a quick experiment costs nothing to leave unrecorded. The store's
    own library is imported only when a run is kept, so a pass left unrecorded needs the tracking
    extra installed no more than it needs the store written.
    """
    if not recorded:
        yield SilentRun()
        return

    # pylint: disable-next=import-outside-toplevel
    from samplecore.tracking.mlflow_run import tracked_run

    with tracked_run(library_root, experiment_name=experiment_name, run_name=run_name) as run:
        yield run
