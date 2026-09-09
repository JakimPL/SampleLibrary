from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import torch
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplemorph.geometry import fourier_bin_count, log_frequency_geometry
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.phase_dataset import PhaseTrainingSet, crop_to, phase_example
from samplemorph.vocoders.learned import (
    LearnedPhaseVocoder,
    PhaseModelDescription,
    load_phase_model,
    phase_model_path,
    save_phase_model,
)
from samplemorph.vocoders.phase_model import PhaseModel, PhaseModelShape
from tests.samplemorph.conftest import harmonic_tone

FRAME_COUNT = 32768
CROP_FRAMES = 16


def _canonicalizer() -> object:
    return CANONICALIZER_REGISTRY["mel"]()


def test_an_example_pairs_a_magnitude_with_the_phase_it_came_from() -> None:
    """Both sides are read from one waveform on one window, so their frames describe one moment."""
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    waveform = harmonic_tone(FRAME_COUNT, frequency=220.0)

    example = phase_example(waveform, canonicalizer=canonicalizer, geometry=canonicalizer.geometry)

    assert example is not None
    assert example.magnitude.shape == example.cosine.shape == example.sine.shape
    assert np.allclose(example.cosine**2 + example.sine**2, 1.0, atol=1e-5)


def test_a_silent_waveform_carries_no_phase_to_learn() -> None:
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()

    assert (
        phase_example(np.zeros((FRAME_COUNT, 1)), canonicalizer=canonicalizer, geometry=canonicalizer.geometry) is None
    )


def test_a_crop_takes_the_same_frames_from_every_side() -> None:
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    example = phase_example(
        harmonic_tone(FRAME_COUNT, frequency=220.0), canonicalizer=canonicalizer, geometry=canonicalizer.geometry
    )
    assert example is not None

    cropped = crop_to(example, crop_frames=CROP_FRAMES, generator=np.random.default_rng(0))

    assert cropped.magnitude.shape[1] == CROP_FRAMES
    assert cropped.cosine.shape[1] == CROP_FRAMES
    assert cropped.sine.shape[1] == CROP_FRAMES
    assert np.array_equal(
        cropped.magnitude, example.magnitude[:, cropped.frame_offset : cropped.frame_offset + CROP_FRAMES]
    )


def test_a_span_shorter_than_the_crop_rests_against_silence() -> None:
    """Repeating the sample would join its end to its beginning and teach a phase jump.

    The loss counts each frame by how loud it is, so the silent tail carries no weight and the
    model learns nothing from it.
    """
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    example = phase_example(
        harmonic_tone(2048, frequency=220.0), canonicalizer=canonicalizer, geometry=canonicalizer.geometry
    )
    assert example is not None
    frames = example.magnitude.shape[1]
    assert frames < 512

    cropped = crop_to(example, crop_frames=512, generator=np.random.default_rng(0))

    assert cropped.magnitude.shape[1] == 512
    assert cropped.frame_offset == 0
    assert np.array_equal(cropped.magnitude[:, :frames], example.magnitude)
    assert float(np.abs(cropped.magnitude[:, frames:]).max()) == 0.0
    assert np.allclose(cropped.cosine[:, frames:] ** 2 + cropped.sine[:, frames:] ** 2, 1.0)


def test_a_training_set_yields_one_crop_per_sample(connection: Connection, tmp_path: Path) -> None:
    repository = PostgresSampleRepository(connection)
    samples = []
    for index in range(3):
        sample = Sample(
            hash=format(index + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=FRAME_COUNT
        )
        repository.upsert(sample)
        audio_store.write(tmp_path, SamplePCM(sample=sample, pcm=harmonic_tone(FRAME_COUNT, frequency=220.0)))
        samples.append(sample)

    training_set = PhaseTrainingSet(
        tuple(samples),
        library_root=tmp_path,
        canonicalizer=CANONICALIZER_REGISTRY["mel"](),
        crop_frames=CROP_FRAMES,
        random_seed=0,
    )

    magnitude, cosine, sine, frame_offset = training_set[0]
    assert len(training_set) == 3
    assert magnitude.shape[1] == CROP_FRAMES
    assert cosine.shape == sine.shape == magnitude.shape
    assert frame_offset >= 0


def test_a_stored_phase_model_is_rebuilt_as_the_network_it_was(tmp_path: Path) -> None:
    """A checkpoint carries the shape it was fitted at, so a vocoder rebuilds it rather than guessing."""
    shape = PhaseModelShape(bin_count=65, channels=32, kernel_size=3, dilations=(1, 2))
    description = PhaseModelDescription(
        canonicalizer="mel",
        bin_count=shape.bin_count,
        frames_per_turn=shape.frames_per_turn,
        channels=shape.channels,
        kernel_size=shape.kernel_size,
        dilations=shape.dilations,
        fft_length=128,
        hop_length=32,
        epochs=1,
        trained_sample_count=4,
        best_validation_loss=1.5,
    )
    path = phase_model_path(tmp_path, name="under-test")
    save_phase_model(path, PhaseModel(shape), description)

    loaded = load_phase_model(path, device=torch.device("cpu"))

    assert isinstance(loaded, LearnedPhaseVocoder)
    assert loaded.description.channels == shape.channels
    assert loaded.description.canonicalizer == "mel"


def test_asking_for_a_phase_model_that_was_never_written_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no phase model is stored"):
        load_phase_model(phase_model_path(tmp_path, name="absent"), device=torch.device("cpu"))


def test_the_learned_vocoder_returns_the_frames_the_spectrogram_asks_for() -> None:
    canonicalizer = CANONICALIZER_REGISTRY["log_frequency"]()
    geometry = log_frequency_geometry()
    spectrogram = canonicalizer.restore(canonicalizer.canonicalize(harmonic_tone(8192, frequency=220.0)))
    shape = PhaseModelShape(
        bin_count=fourier_bin_count(fft_length=geometry.fft_length), channels=16, kernel_size=3, dilations=(1,)
    )
    description = PhaseModelDescription(
        canonicalizer="log_frequency",
        bin_count=shape.bin_count,
        frames_per_turn=shape.frames_per_turn,
        channels=shape.channels,
        kernel_size=shape.kernel_size,
        dilations=shape.dilations,
        fft_length=geometry.fft_length,
        hop_length=geometry.hop_length,
        epochs=1,
        trained_sample_count=4,
        best_validation_loss=1.0,
    )
    vocoder = LearnedPhaseVocoder(model=PhaseModel(shape).eval(), description=description, device=torch.device("cpu"))

    waveform = vocoder.synthesize(spectrogram)

    assert waveform.shape == (spectrogram.frame_count,)
    assert np.all(np.isfinite(waveform))
