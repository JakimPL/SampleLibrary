from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from samplecore.models.experiment import ExperimentKey
from samplecore.storage.atomic import copy_atomically
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplelibrary.pipeline.artifacts import (
    CONTENT_KEY,
    artifact_holds_its_content,
    content_digest,
    read_sidecar,
    remove_path,
    seal_artifact,
    sidecar_path,
)
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.results import StepAction, StepPlan

NO_EXPERIMENT: Final[str] = "no experiment"
SAMPLES_TO_DESCRIBE: Final[str] = "samples to describe"
NOT_SHOWN: Final[str] = "not shown"
SEALED_COPY_MISSING: Final[str] = "sealed copy missing"

Inputs = Mapping[str, str]
InputReader = Callable[[PipelineContext], Inputs]
CommandBuilder = Callable[[PipelineContext], tuple[str, ...]]
ArtifactCommandBuilder = Callable[[PipelineContext, Path, bool], tuple[str, ...]]
ArtifactNamer = Callable[[PipelineContext, str], Path]
ContextTest = Callable[[PipelineContext], bool]
KeyNamer = Callable[[PipelineContext, str], ExperimentKey]


class Step(Protocol):
    """One thing a run does to a library, which decides for itself whether it is already done."""

    @property
    def name(self) -> str: ...

    @property
    def requires(self) -> tuple[str, ...]: ...

    def evaluate(self, context: PipelineContext) -> StepPlan:
        """What this step reads now, and what is left to do about it."""

    def seal(self, context: PipelineContext, plan: StepPlan) -> Inputs:
        """Bind what the step produced to the inputs it was built from, answering what it produced.

        Raises:
            MissingOutput: the command ended a success and produced nothing.
        """


class MissingOutput(Exception):
    """Raised when a step's command ended a success without leaving the output the step stands for."""


class StepRefused(Exception):
    """Raised while a step reads its inputs, when what it would read cannot be read as the step needs it."""


@dataclass(frozen=True)
class PassStep:
    """A pass that always runs and skips its own work, such as extraction over an unchanged collection.

    The command decides for itself what is left to do, so the run's part is to start it and read how
    it ended.
    """

    name: str
    requires: tuple[str, ...]
    command: CommandBuilder

    def evaluate(self, context: PipelineContext) -> StepPlan:
        return StepPlan(inputs={}, action=StepAction.RUN, argv=self.command(context))

    def seal(self, context: PipelineContext, plan: StepPlan) -> Inputs:  # pylint: disable=unused-argument
        return {}


@dataclass(frozen=True)
class GuardedPassStep:
    """A pass that runs only where a condition holds, and refuses where its own precondition is unmet.

    The labels a fresh catalog reads are such a pass: importing them into a library that already
    holds labels of its own would replace a person's newer decisions with a file's older ones.
    """

    name: str
    requires: tuple[str, ...]
    command: CommandBuilder
    satisfied: ContextTest
    refusal: Callable[[PipelineContext], str | None]

    def evaluate(self, context: PipelineContext) -> StepPlan:
        refusal = self.refusal(context)
        if refusal is not None:
            return StepPlan(inputs={}, action=StepAction.REFUSE, reason=refusal)
        if self.satisfied(context):
            return StepPlan(inputs={}, action=StepAction.SKIP)
        return StepPlan(inputs={}, action=StepAction.RUN, argv=self.command(context))

    def seal(self, context: PipelineContext, plan: StepPlan) -> Inputs:  # pylint: disable=unused-argument
        return {}


@dataclass(frozen=True)
class GrowingExperimentStep:
    """An experiment that keeps one key and takes in whatever the catalog has gained since.

    It is done when its key names an experiment and nothing readable is left for it to describe, so
    a library that grew has something to do and one that stands still has nothing.
    """

    name: str
    requires: tuple[str, ...]
    key: Callable[[PipelineContext], ExperimentKey]
    command: CommandBuilder
    pending: Callable[[PipelineContext, int], int]
    inputs: InputReader

    def evaluate(self, context: PipelineContext) -> StepPlan:
        inputs = self.inputs(context)
        filed = PostgresExperimentRepository(context.connection).get_by_key(self.key(context))
        if filed is None:
            return StepPlan(
                inputs=inputs, action=StepAction.RUN, argv=self.command(context), reasons=frozenset({NO_EXPERIMENT})
            )
        if self.pending(context, filed.id) == 0:
            return StepPlan(inputs=inputs, action=StepAction.SKIP)
        return StepPlan(
            inputs=inputs, action=StepAction.RUN, argv=self.command(context), reasons=frozenset({SAMPLES_TO_DESCRIBE})
        )

    def seal(self, context: PipelineContext, plan: StepPlan) -> Inputs:  # pylint: disable=unused-argument
        key = self.key(context)
        filed = PostgresExperimentRepository(context.connection).get_by_key(key)
        if filed is None:
            raise MissingOutput(f"{self.name} left no experiment filed under {key}")
        return {"experiment": str(filed.id), "key": key}


@dataclass(frozen=True)
class DerivedExperimentStep:
    """An experiment named by what it was made from, which stands whole or not at all.

    Its key holds the digest of its inputs, so a run finding that key finds the very experiment
    those inputs make, and one finding none makes it.
    """

    name: str
    requires: tuple[str, ...]
    inputs: InputReader
    key: KeyNamer
    command: Callable[[PipelineContext, ExperimentKey], tuple[str, ...]]
    shown: Callable[[PipelineContext, int], bool] | None = None

    def evaluate(self, context: PipelineContext) -> StepPlan:
        inputs = self.inputs(context)
        plan = StepPlan(inputs=inputs, action=StepAction.SKIP)
        key = self.key(context, plan.digest)
        filed = PostgresExperimentRepository(context.connection).get_by_key(key)
        if filed is not None and (self.shown is None or self.shown(context, filed.id)):
            return plan
        reasons = frozenset({NOT_SHOWN}) if filed is not None else frozenset()
        return StepPlan(inputs=inputs, action=StepAction.RUN, argv=self.command(context, key), reasons=reasons)

    def seal(self, context: PipelineContext, plan: StepPlan) -> Inputs:
        key = self.key(context, plan.digest)
        filed = PostgresExperimentRepository(context.connection).get_by_key(key)
        if filed is None:
            raise MissingOutput(f"{self.name} left no experiment filed under {key}")
        if self.shown is not None and not self.shown(context, filed.id):
            raise MissingOutput(f"{self.name} filed experiment {filed.id} under {key} and left it unshown")
        return {"experiment": str(filed.id), "key": key}


@dataclass(frozen=True)
class TrainingRecords:
    """Where a training run keeps what it leaves beside its model: its directory, its resume point, and its finished record."""

    directory: Path
    resume_point: Path
    finished: Path


@dataclass(frozen=True)
class FileArtifactStep:
    """A file or directory named by the digest of what it was built from, bound to those inputs when complete.

    A build that ended leaves the artifact under that name; the sidecar beside it says which inputs
    it came from. An artifact standing complete without a sidecar -- a run whose process died between
    the two -- is sealed rather than built again. A training run is complete once its finished record
    stands beside its model, and continues from its resume point where it stopped short of it. A
    step naming a sealed copy keeps one under the artifact's content, which an experiment names so the
    model it loads by that name is always the one it was described by.
    """

    name: str
    requires: tuple[str, ...]
    inputs: InputReader
    artifact: ArtifactNamer
    command: ArtifactCommandBuilder
    complete: Callable[[Path], bool]
    training: Callable[[PipelineContext, str], TrainingRecords] | None = None
    sealed_as: Callable[[PipelineContext, str], Path] | None = None

    def evaluate(self, context: PipelineContext) -> StepPlan:
        inputs = self.inputs(context)
        plan = StepPlan(inputs=inputs, action=StepAction.SKIP)
        artifact = self.artifact(context, plan.digest)
        sidecar = read_sidecar(artifact)
        if sidecar is not None and sidecar.digest == plan.digest and artifact_holds_its_content(artifact, sidecar):
            if self._sealed_copy_stands(context, sidecar.content):
                return plan
            return StepPlan(inputs=inputs, action=StepAction.SEAL, reasons=frozenset({SEALED_COPY_MISSING}))
        if self._complete(context, plan.digest):
            return StepPlan(inputs=inputs, action=StepAction.SEAL)
        return StepPlan(
            inputs=inputs,
            action=StepAction.RUN,
            argv=self.command(context, artifact, self._resumes(context, plan.digest)),
        )

    def seal(self, context: PipelineContext, plan: StepPlan) -> Inputs:
        artifact = self.artifact(context, plan.digest)
        if not self._complete(context, plan.digest):
            raise MissingOutput(f"{self.name} left no complete {artifact}")
        sidecar = seal_artifact(artifact, inputs=plan.inputs, digest=plan.digest)
        outputs = {"artifact": artifact.name, CONTENT_KEY: sidecar.content}
        if self.sealed_as is not None:
            sealed = self.sealed_as(context, sidecar.content)
            copy_atomically(artifact, sealed)
            seal_artifact(sealed, inputs=plan.inputs, digest=plan.digest)
            outputs["sealed"] = sealed.name
        return outputs

    def content(self, context: PipelineContext) -> str | None:
        """What this step's artifact for the inputs it reads now holds, or nothing where no sealed build stands."""
        plan = StepPlan(inputs=self.inputs(context), action=StepAction.SKIP)
        sidecar = read_sidecar(self.artifact(context, plan.digest))
        return None if sidecar is None or sidecar.digest != plan.digest else sidecar.content

    def forget(self, context: PipelineContext) -> tuple[Path, ...]:
        """Remove what this step built for the inputs it reads now, so a redo builds it again; a sealed copy stays."""
        plan = StepPlan(inputs=self.inputs(context), action=StepAction.SKIP)
        artifact = self.artifact(context, plan.digest)
        removed = remove_path(sidecar_path(artifact)) + remove_path(artifact)
        if self.training is not None:
            removed += remove_path(self.training(context, plan.digest).directory)
        return removed

    def _complete(self, context: PipelineContext, digest: str) -> bool:
        if not self.complete(self.artifact(context, digest)):
            return False
        return self.training is None or self.training(context, digest).finished.is_file()

    def _resumes(self, context: PipelineContext, digest: str) -> bool:
        """Whether a training run of these inputs stopped short of finishing and left a point to continue from."""
        if self.training is None:
            return False
        records = self.training(context, digest)
        return records.resume_point.is_file() and not records.finished.is_file()

    def _sealed_copy_stands(self, context: PipelineContext, content: str) -> bool:
        if self.sealed_as is None:
            return True
        sealed = self.sealed_as(context, content)
        sidecar = read_sidecar(sealed)
        return sidecar is not None and artifact_holds_its_content(sealed, sidecar)


@dataclass(frozen=True)
class PointerStep:
    """A step that makes one of the library's own records name what an earlier step built.

    The cloud a viewer sees and the models the renderer loads are such records: what they name is a
    decision, so the step is done when the record names this run's output.
    """

    name: str
    requires: tuple[str, ...]
    inputs: InputReader
    satisfied: ContextTest
    command: CommandBuilder
    outputs: Callable[[PipelineContext], Inputs] = field(default=lambda context: {})

    def evaluate(self, context: PipelineContext) -> StepPlan:
        inputs = self.inputs(context)
        if self.satisfied(context):
            return StepPlan(inputs=inputs, action=StepAction.SKIP)
        return StepPlan(inputs=inputs, action=StepAction.RUN, argv=self.command(context))

    def seal(self, context: PipelineContext, plan: StepPlan) -> Inputs:  # pylint: disable=unused-argument
        if not self.satisfied(context):
            raise MissingOutput(f"{self.name} left the library naming something else")
        return self.outputs(context)


def local_artifact_is_complete(artifact: Path) -> bool:
    """Whether a file artifact is there at all, which is complete for anything written in one move."""
    return artifact.exists()


def directory_artifact_is_complete(marker: str) -> Callable[[Path], bool]:
    """Whether a directory artifact holds the file its builder writes last."""

    def complete(artifact: Path) -> bool:
        return (artifact / marker).is_file()

    return complete


def artifact_content(artifact: Path) -> str:
    """What an artifact holds now, for a caller naming an output by its content."""
    return content_digest(artifact)
