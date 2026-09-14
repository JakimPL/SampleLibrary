from __future__ import annotations

from collections.abc import Callable
from typing import Final

from pydantic import Field

from samplecloud.backends.teacher_backend import TEACHER_BACKEND_NAME, TEACHER_REVISION
from samplecloud.features import readable_pending_count
from samplecloud.hearing import hearing_for
from samplecloud.suggestions.scoring import DEFAULT_SUGGESTION_COUNT, MAXIMUM_SUGGESTION_COUNT
from samplecloud.suggestions.vocabulary import INSTRUMENTS_CHOICE, VocabularyRefused, vocabulary_from
from samplecore.digests import digest_of_rows
from samplecore.models.experiment import ExperimentKey, Reading
from samplecore.storage.repositories.label_suggestion import PostgresSuggestionPromotionRepository
from samplecore.storage.sample_audio import readable_membership_digest
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.settings import StepSettings
from samplelibrary.pipeline.steps.catalog import MODULES, NOTES, SAMPLE_FILES
from samplelibrary.pipeline.steps.kinds import (
    DerivedExperimentStep,
    GrowingExperimentStep,
    Inputs,
    Step,
    StepRefused,
)
from samplelibrary.pipeline.steps.shared import PARAMETERS, READABLE_SAMPLES, filed_experiment, vectors_digest

TEACHER: Final[str] = "teacher"
HEARING_TEACHER: Final[str] = "hearing-teacher"
SUGGESTIONS: Final[str] = "suggestions"
REVISION_CHARACTERS: Final[int] = 12
TEACHER_KEY: Final[ExperimentKey] = f"teacher-nominal-{TEACHER_REVISION[:REVISION_CHARACTERS]}"
HEARING_TEACHER_KEY: Final[ExperimentKey] = f"teacher-heard-{TEACHER_REVISION[:REVISION_CHARACTERS]}"
SUGGESTIONS_KEY_PREFIX: Final[str] = "suggestions"
LISTENING_MODEL: Final[str] = "listening model"
PLAYBACK_RATES: Final[str] = "playback rates"
HEARD_VECTORS: Final[str] = "heard vectors"
VOCABULARY: Final[str] = "vocabulary"


class SuggestionSettings(StepSettings):
    """What the suggestions step takes: how many labels each sample keeps, and which vocabulary they come from."""

    top: int = Field(default=DEFAULT_SUGGESTION_COUNT, ge=1, le=MAXIMUM_SUGGESTION_COUNT)
    vocabulary: str = INSTRUMENTS_CHOICE


def listening_steps() -> tuple[Step, ...]:
    """The listening model's two readings of every sample the library can read, and the labels it suggests.

    Both readings keep one key each for the life of the listening model's commit, and take in the
    samples the catalog gains; the suggestions are named by the heard vectors and the vocabulary
    they rank, so a scoring over the same of both stands.
    """
    return (
        GrowingExperimentStep(
            name=TEACHER,
            requires=(MODULES, SAMPLE_FILES),
            key=lambda context: TEACHER_KEY,
            command=lambda context: _embed_command(TEACHER_KEY, heard=False),
            pending=_pending(Reading.NOMINAL),
            inputs=_teacher_inputs,
        ),
        GrowingExperimentStep(
            name=HEARING_TEACHER,
            requires=(SAMPLE_FILES, NOTES),
            key=lambda context: HEARING_TEACHER_KEY,
            command=lambda context: _embed_command(HEARING_TEACHER_KEY, heard=True),
            pending=_pending(Reading.HEARD_RATE),
            inputs=_hearing_inputs,
        ),
        DerivedExperimentStep(
            name=SUGGESTIONS,
            requires=(HEARING_TEACHER,),
            inputs=_suggestion_inputs,
            key=lambda context, digest: f"{SUGGESTIONS_KEY_PREFIX}-{digest}",
            command=_suggest_command,
            shown=_suggestions_shown,
        ),
    )


def _embed_command(key: ExperimentKey, *, heard: bool) -> tuple[str, ...]:
    reading = ("--heard-rate",) if heard else ()
    return ("cloud", "embed", "--backend", TEACHER_BACKEND_NAME, "--extract-only", *reading, "--key", key)


def _pending(reading: Reading) -> Callable[[PipelineContext, int], int]:
    def pending(context: PipelineContext, experiment_id: int) -> int:
        return readable_pending_count(
            context.connection, experiment_id, hearing=hearing_for(context.connection, reading)
        )

    return pending


def _teacher_inputs(context: PipelineContext) -> Inputs:
    return {
        READABLE_SAMPLES: readable_membership_digest(context.connection),
        LISTENING_MODEL: TEACHER_REVISION,
    }


def _hearing_inputs(context: PipelineContext) -> Inputs:
    return {
        **_teacher_inputs(context),
        PLAYBACK_RATES: hearing_for(context.connection, Reading.HEARD_RATE).rates_digest,
    }


def _suggestion_settings(context: PipelineContext) -> SuggestionSettings:
    return context.settings.settings_for(SUGGESTIONS, SuggestionSettings)


def _suggestion_inputs(context: PipelineContext) -> Inputs:
    """The heard vectors a scoring ranks, the labels it ranks them against, and how many it keeps.

    Raises:
        StepRefused: the vocabulary names a file that cannot be read, or one holding no label.
    """
    settings = _suggestion_settings(context)
    try:
        vocabulary = vocabulary_from(settings.vocabulary, context.connection)
    except VocabularyRefused as error:
        raise StepRefused(str(error)) from error
    return {
        HEARD_VECTORS: vectors_digest(context, HEARING_TEACHER_KEY),
        VOCABULARY: digest_of_rows((label,) for label in vocabulary),
        PARAMETERS: settings.parameters_digest,
    }


def _suggest_command(context: PipelineContext, key: ExperimentKey) -> tuple[str, ...]:
    """The scoring of the heard vectors, filed under this key."""
    settings = _suggestion_settings(context)
    return (
        "cloud",
        "suggest",
        "--experiment-id",
        str(filed_experiment(context, HEARING_TEACHER_KEY)),
        "--vocabulary",
        settings.vocabulary,
        "--top",
        str(settings.top),
        "--key",
        key,
    )


def _suggestions_shown(context: PipelineContext, experiment_id: int) -> bool:
    shown = PostgresSuggestionPromotionRepository(context.connection).current()
    return shown is not None and shown.experiment_id == experiment_id
