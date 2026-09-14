from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from samplelibrary.pipeline.events import EVENTS_FILE_NAME

PIPELINE_DIRECTORY_NAME: Final[str] = "pipeline"
RUNS_DIRECTORY_NAME: Final[str] = "runs"
STEPS_DIRECTORY_NAME: Final[str] = "steps"
EVALUATIONS_DIRECTORY_NAME: Final[str] = "evaluations"
SCRATCH_INTENT_NAME: Final[str] = "scratch.json"
ATTEMPTS_FILE_NAME: Final[str] = "attempts.jsonl"
CONFIG_SNAPSHOT_NAME: Final[str] = "config.toml"
RUN_STAMP_FORMAT: Final[str] = "%Y-%m-%dT%H-%M-%S"
RUN_ID_CHARACTERS: Final[int] = 8


@dataclass(frozen=True)
class PipelineLayout:
    """Where a library keeps what the pipeline writes about itself, beside what its steps build."""

    library_root: Path

    @property
    def root(self) -> Path:
        return self.library_root / PIPELINE_DIRECTORY_NAME

    @property
    def runs(self) -> Path:
        return self.root / RUNS_DIRECTORY_NAME

    @property
    def steps(self) -> Path:
        return self.root / STEPS_DIRECTORY_NAME

    @property
    def evaluations(self) -> Path:
        return self.root / EVALUATIONS_DIRECTORY_NAME

    @property
    def scratch_intent(self) -> Path:
        return self.root / SCRATCH_INTENT_NAME

    def step_record(self, step: str) -> Path:
        """Where the record of a step's last complete run sits, which `status` reads to say what changed."""
        return self.steps / f"{step}.json"


@dataclass(frozen=True)
class RunPaths:
    """Where one run keeps its events, its attempts, its step logs and the configuration its steps read."""

    directory: Path
    run_id: str

    @classmethod
    def opened_under(cls, layout: PipelineLayout) -> RunPaths:
        """A directory of this run's own, named by the moment it started and an identity of its own.

        Two runs beginning in one second keep their own directories, since the identity tells them
        apart; the name holds no character a file system refuses.
        """
        run_id = uuid.uuid4().hex[:RUN_ID_CHARACTERS]
        directory = layout.runs / f"{datetime.now(UTC).strftime(RUN_STAMP_FORMAT)}-{run_id}"
        directory.mkdir(parents=True)
        return cls(directory=directory, run_id=run_id)

    @property
    def events(self) -> Path:
        return self.directory / EVENTS_FILE_NAME

    @property
    def attempts(self) -> Path:
        return self.directory / ATTEMPTS_FILE_NAME

    @property
    def config_snapshot(self) -> Path:
        return self.directory / CONFIG_SNAPSHOT_NAME

    def log(self, step: str) -> Path:
        """Where one step's own output goes, which a person follows while it runs."""
        return self.directory / f"{step}.log"
