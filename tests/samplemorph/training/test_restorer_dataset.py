from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.derived_examples import DerivedExampleSet, ExampleFamily
from samplemorph.training.restorer_dataset import (
    SILENCE_DECIBELS,
    RestorerExample,
    crop_item,
    crop_to,
    restorer_example,
)
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
        library_root=tmp_path,
        canonicalizer=CANONICALIZER_REGISTRY["log_frequency"](),
        random_seed=0,
        family=ExampleFamily(derive=restorer_example, crop=crop_item, crop_frames=CROP_FRAMES),
    )

    least_squares, clean = training_set[0]
    assert len(training_set) == 3
    assert least_squares.shape == clean.shape
    assert least_squares.shape[1] == CROP_FRAMES
