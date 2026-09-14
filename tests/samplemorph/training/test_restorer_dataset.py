from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_file import SampleFile
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.commands.draws import readable_samples
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.analysis_data import AnalysisCorpus, AnalysisDataModule
from samplemorph.training.derived_examples import DerivedExampleSet, ExampleFamily
from samplemorph.training.epoch_draws import EpochCropSampler, FixedCropSampler
from samplemorph.training.refusals import TrainingDataShortfall
from samplemorph.training.restorer_dataset import (
    SILENCE_DECIBELS,
    RestorerExample,
    crop_item,
    crop_to,
    restorer_example,
)
from samplemorph.training.run_settings import RunSettings
from tests.samplemorph.conftest import harmonic_tone

FRAME_COUNT = 32768
CROP_FRAMES = 16


def _example() -> RestorerExample:
    canonicalizer = CANONICALIZER_REGISTRY["log_frequency"]()
    example = restorer_example(
        harmonic_tone(FRAME_COUNT, frequency=220.0), canonicalizer=canonicalizer, geometry=canonicalizer.geometry
    )
    assert example is not None
    return example


def test_an_example_pairs_the_reading_back_with_the_analysis_on_one_scale() -> None:
    """Both sides are decibels against the reading's own peak, so the target is the residual the grid removed."""
    example = _example()

    assert example.least_squares.shape == example.clean.shape
    assert example.least_squares.dtype == example.clean.dtype == np.float32
    assert example.least_squares.max() == 0.0
    assert example.least_squares.min() >= SILENCE_DECIBELS
    assert example.clean.min() >= SILENCE_DECIBELS
    assert np.abs(example.clean - example.least_squares).max() > 0.0


def test_a_silent_waveform_carries_nothing_to_put_back() -> None:
    canonicalizer = CANONICALIZER_REGISTRY["log_frequency"]()

    assert (
        restorer_example(np.zeros((FRAME_COUNT, 1)), canonicalizer=canonicalizer, geometry=canonicalizer.geometry)
        is None
    )


def test_a_crop_takes_the_same_frames_from_both_sides() -> None:
    example = _example()

    cropped = crop_to(example, crop_frames=CROP_FRAMES, generator=np.random.default_rng(0))

    assert cropped.frame_count == CROP_FRAMES
    starts = [
        start
        for start in range(example.frame_count - CROP_FRAMES + 1)
        if np.array_equal(example.least_squares[:, start : start + CROP_FRAMES], cropped.least_squares)
    ]
    assert starts
    assert np.array_equal(example.clean[:, starts[0] : starts[0] + CROP_FRAMES], cropped.clean)


def test_a_short_example_rests_against_silence_on_both_sides() -> None:
    example = _example()
    frames = example.frame_count

    cropped = crop_to(example, crop_frames=frames + 5, generator=np.random.default_rng(0))

    assert cropped.frame_count == frames + 5
    assert np.all(cropped.least_squares[:, frames:] == SILENCE_DECIBELS)
    assert np.all(cropped.clean[:, frames:] == SILENCE_DECIBELS)


def test_a_training_set_yields_one_pair_per_sample(connection: Connection, tmp_path: Path) -> None:
    repository = PostgresSampleRepository(connection)
    samples = []
    for index in range(3):
        sample = Sample(
            hash=format(index + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=FRAME_COUNT
        )
        repository.upsert(sample)
        audio_store.write(tmp_path, SamplePCM(sample=sample, pcm=harmonic_tone(FRAME_COUNT, frequency=220.0)))
        samples.append(sample)

    training_set = DerivedExampleSet(
        tuple(samples),
        audio=SampleAudio.of_files(tmp_path, ()),
        canonicalizer=CANONICALIZER_REGISTRY["log_frequency"](),
        family=ExampleFamily(derive=restorer_example, crop=crop_item, crop_frames=CROP_FRAMES),
    )

    least_squares, clean = training_set[(0, 0)]
    assert len(training_set) == 3
    assert least_squares.shape == clean.shape
    assert least_squares.shape[1] == CROP_FRAMES


def _requests(sampler: EpochCropSampler, epoch: int) -> list[tuple[int, int]]:
    sampler.set_epoch(epoch)
    return list(sampler)


def test_training_crops_are_drawn_afresh_every_epoch_and_replay_under_one_seed() -> None:
    """A crop fixed per sample would show a long run the same span of every sample, epoch after epoch."""
    first = _requests(EpochCropSampler(12, random_seed=0), 0)

    assert sorted(index for index, _ in first) == list(range(12))
    assert _requests(EpochCropSampler(12, random_seed=0), 1) != first
    assert _requests(EpochCropSampler(12, random_seed=0), 0) == first


def test_validation_crops_stay_where_they_were_every_epoch() -> None:
    sampler = FixedCropSampler(12, random_seed=0)

    assert list(sampler) == list(sampler) == list(FixedCropSampler(12, random_seed=0))
    assert [index for index, _ in sampler] == list(range(12))


def test_a_crop_seed_decides_the_span_a_request_reads() -> None:
    example = _example()

    first = crop_to(example, crop_frames=CROP_FRAMES, generator=np.random.default_rng(11))
    again = crop_to(example, crop_frames=CROP_FRAMES, generator=np.random.default_rng(11))

    np.testing.assert_array_equal(first.least_squares, again.least_squares)


def _sample(index: int) -> Sample:
    return Sample(
        hash=format(index + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=FRAME_COUNT
    )


@pytest.mark.parametrize(
    ("sample_count", "batch_size", "reason"),
    [(1, 1, "nothing to train on"), (20, 32, "fill no batch of 32; set --batch")],
    ids=("too few to hold any back", "too few for one batch"),
)
def test_a_corpus_too_small_to_train_on_is_refused(sample_count: int, batch_size: int, reason: str) -> None:
    corpus = AnalysisCorpus(
        samples=tuple(_sample(index) for index in range(sample_count)),
        audio=SampleAudio.of_files(Path("unused"), ()),
        canonicalizer=CANONICALIZER_REGISTRY["log_frequency"](),
        canonicalizer_name="log_frequency",
    )

    with pytest.raises(TrainingDataShortfall, match=reason):
        AnalysisDataModule(
            corpus,
            family=ExampleFamily(derive=restorer_example, crop=crop_item, crop_frames=CROP_FRAMES),
            run=RunSettings(batch_size=batch_size, worker_count=0, random_seed=0),
        )


def test_a_sample_whose_file_is_gone_yields_the_next_sample_along(
    connection: Connection, tmp_path: Path, vanished_sample_file: SampleFile
) -> None:
    stored = Sample(hash=format(1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=FRAME_COUNT)
    PostgresSampleRepository(connection).upsert(stored)
    audio_store.write(tmp_path, SamplePCM(sample=stored, pcm=harmonic_tone(FRAME_COUNT, frequency=220.0)))
    vanished = PostgresSampleRepository(connection).get(vanished_sample_file.sample_hash)
    assert vanished is not None
    audio = SampleAudio.from_catalog(connection, tmp_path)
    training_set = DerivedExampleSet(
        (vanished, stored),
        audio=audio,
        canonicalizer=CANONICALIZER_REGISTRY["log_frequency"](),
        family=ExampleFamily(derive=restorer_example, crop=crop_item, crop_frames=CROP_FRAMES),
    )

    least_squares, _ = training_set[(0, 0)]

    assert least_squares.shape[1] == CROP_FRAMES
    assert readable_samples((vanished, stored), audio) == (stored,)
