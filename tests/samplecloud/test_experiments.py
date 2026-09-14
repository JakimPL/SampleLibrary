from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud.backends.teacher_backend import TEACHER_REVISION
from samplecloud.experiments import (
    EmbeddingRecipe,
    ExperimentRefused,
    ExtractorChanged,
    experiment_named,
    recipe_of,
    require_reproducible,
)
from samplecloud.hearing import Hearing
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import Experiment, Reading, SampleFeatureVector
from samplecore.models.sample import Sample
from samplecore.models.sample_file import SampleFile
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio

NOMINAL = Hearing(reading=Reading.NOMINAL, playback_rate_by_hash={})


def _experiment(backend_name: str, params: dict[str, Any]) -> Experiment:
    return Experiment(id=3, backend_name=backend_name, params=params, created_at=datetime.now(UTC), label=None)


@dataclass(frozen=True)
class RecipeCase:
    backend_name: str
    params: dict[str, Any]
    recipe: EmbeddingRecipe


@pytest.mark.parametrize(
    "case",
    [
        RecipeCase(
            backend_name="librosa",
            params={"reading": "nominal"},
            recipe=EmbeddingRecipe(backend_name="librosa", reading=Reading.NOMINAL, model_name=None),
        ),
        RecipeCase(
            backend_name="clap",
            params={"reading": "heard_rate", "checkpoint_revision": TEACHER_REVISION},
            recipe=EmbeddingRecipe(backend_name="clap", reading=Reading.HEARD_RATE, model_name=None),
        ),
        RecipeCase(
            backend_name="learned",
            params={"reading": "nominal", "model": "descriptor"},
            recipe=EmbeddingRecipe(backend_name="learned", reading=Reading.NOMINAL, model_name="descriptor"),
        ),
    ],
    ids=("a registered backend", "a heard-rate reading", "a learned descriptor"),
)
def test_an_experiment_row_gives_back_the_recipe_it_recorded(case: RecipeCase) -> None:
    recipe = recipe_of(_experiment(case.backend_name, case.params))

    assert recipe == case.recipe
    assert recipe.parameters == case.params


@dataclass(frozen=True)
class RefusedRecipeCase:
    backend_name: str
    params: dict[str, Any]
    reason: str


@pytest.mark.parametrize(
    "case",
    [
        RefusedRecipeCase(backend_name="zero_shot", params={}, reason="label suggestions"),
        RefusedRecipeCase(backend_name="retired", params={"reading": "nominal"}, reason="unknown here"),
        RefusedRecipeCase(backend_name="learned", params={"reading": "nominal"}, reason="does not name"),
        RefusedRecipeCase(backend_name="librosa", params={}, reason="records no reading"),
        RefusedRecipeCase(backend_name="librosa", params={"reading": "sideways"}, reason="records no reading"),
        RefusedRecipeCase(
            backend_name="clap",
            params={"reading": "nominal", "checkpoint_revision": "0" * 40},
            reason="listening-model commit 0{40}",
        ),
        RefusedRecipeCase(backend_name="clap", params={"reading": "nominal"}, reason="commit unrecorded"),
    ],
    ids=(
        "a scoring",
        "an unknown backend",
        "a learned one naming no model",
        "no reading",
        "an unknown reading",
        "another listening-model commit",
        "no listening-model commit",
    ),
)
def test_an_experiment_recording_no_followable_recipe_is_refused(case: RefusedRecipeCase) -> None:
    with pytest.raises(ExperimentRefused, match=case.reason):
        recipe_of(_experiment(case.backend_name, case.params))


def test_an_unknown_experiment_is_refused_by_its_id(connection: Connection) -> None:
    with pytest.raises(ExperimentRefused, match="holds no experiment 999999"):
        experiment_named(connection, 999_999)


class _ShapeExtractor:
    def __init__(self, *, swapped: bool) -> None:
        self.swapped = swapped

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        described = np.array([waveform.mean(), waveform.std()])
        return described[::-1] if self.swapped else described


def _seed_experiment(connection: Connection, library_root: Path) -> int:
    experiment_id = PostgresExperimentRepository(connection).create(
        backend_name="stub", label=None, params={}, key=None
    )
    samples = PostgresSampleRepository(connection)
    vectors: list[SampleFeatureVector] = []
    for seed in range(3):
        pcm = np.random.default_rng(seed).uniform(-1.0, 1.0, (64, 1))
        sample = Sample(hash=format(seed + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=64)
        samples.upsert(sample)
        audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
        stored = audio_store.read(library_root, sample).pcm
        vectors.append(
            SampleFeatureVector(
                experiment_id=experiment_id,
                sample_hash=sample.hash,
                vector=tuple(_ShapeExtractor(swapped=False).extract(stored).tolist()),
                computed_at=datetime.now(UTC),
            )
        )
    PostgresSampleFeatureVectorRepository(connection).insert_many(vectors)
    connection.commit()
    return experiment_id


def test_the_extractor_that_made_an_experiment_reproduces_it(connection: Connection, tmp_path: Path) -> None:
    experiment_id = _seed_experiment(connection, tmp_path)

    require_reproducible(
        connection,
        SampleAudio.from_catalog(connection, tmp_path),
        experiment_id=experiment_id,
        extractor=_ShapeExtractor(swapped=False),
        hearing=NOMINAL,
    )


def test_an_extractor_describing_the_samples_otherwise_is_refused(connection: Connection, tmp_path: Path) -> None:
    experiment_id = _seed_experiment(connection, tmp_path)

    with pytest.raises(ExtractorChanged, match="start a new experiment"):
        require_reproducible(
            connection,
            SampleAudio.from_catalog(connection, tmp_path),
            experiment_id=experiment_id,
            extractor=_ShapeExtractor(swapped=True),
            hearing=NOMINAL,
        )


def _add_vector(connection: Connection, experiment_id: int, sample_hash: str) -> None:
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [
            SampleFeatureVector(
                experiment_id=experiment_id, sample_hash=sample_hash, vector=(0.0, 1.0), computed_at=datetime.now(UTC)
            )
        ]
    )
    connection.commit()


def test_a_sample_whose_file_is_gone_is_passed_over_by_the_check(
    connection: Connection, tmp_path: Path, vanished_sample_file: SampleFile
) -> None:
    experiment_id = _seed_experiment(connection, tmp_path)
    _add_vector(connection, experiment_id, vanished_sample_file.sample_hash)

    require_reproducible(
        connection,
        SampleAudio.from_catalog(connection, tmp_path),
        experiment_id=experiment_id,
        extractor=_ShapeExtractor(swapped=False),
        hearing=NOMINAL,
    )


def test_an_experiment_none_of_whose_samples_can_be_read_is_refused(
    connection: Connection, tmp_path: Path, vanished_sample_file: SampleFile
) -> None:
    experiment_id = PostgresExperimentRepository(connection).create(
        backend_name="stub", label=None, params={}, key=None
    )
    _add_vector(connection, experiment_id, vanished_sample_file.sample_hash)

    with pytest.raises(ExperimentRefused, match="can be read now"):
        require_reproducible(
            connection,
            SampleAudio.from_catalog(connection, tmp_path),
            experiment_id=experiment_id,
            extractor=_ShapeExtractor(swapped=False),
            hearing=NOMINAL,
        )
