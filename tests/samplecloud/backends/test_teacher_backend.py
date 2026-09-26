from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

import numpy as np
import pytest
import torch
from numpy.typing import NDArray

from samplecloud.backends import teacher_backend, transformers_teacher
from samplecloud.backends.teacher_backend import (
    TEACHER_BACKEND_NAME,
    TEACHER_CHECKPOINT,
    TEACHER_EMBEDDING_SIZE,
    TEACHER_RATE_HZ,
    TEACHER_REVISION,
    ClapFeatureExtractor,
    load_teacher,
    prepare_for_teacher,
)
from samplecloud.backends.transformers_teacher import TransformersTeacher, fill_window
from samplecloud.registries import BACKEND_REGISTRY
from samplecore.storage.audio_store import NOMINAL_WAV_RATE

SMALL_RATE_HZ: Final[int] = 4000
SMALL_FFT_LENGTH: Final[int] = 256
SMALL_MEL_BANDS: Final[int] = 16


@dataclass
class RecordingTeacher:
    """A teacher that remembers what it was asked to hear and answers with a fixed vector.

    A sentence reads as the unit vector of its position in the list, so a scoring against these
    prompts picks whichever label an audio vector points at.
    """

    heard: list[NDArray[np.float32]] = field(default_factory=list)

    def embed(self, mono: NDArray[np.float32]) -> NDArray[np.float32]:
        vector: NDArray[np.float32] = self.embed_many((mono,))[0]
        return vector

    def embed_many(self, monos: Sequence[NDArray[np.float32]]) -> NDArray[np.float32]:
        self.heard.extend(monos)
        return np.full((len(monos), TEACHER_EMBEDDING_SIZE), 1.0 / np.sqrt(TEACHER_EMBEDDING_SIZE), dtype=np.float32)

    def embed_text(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return np.eye(len(texts), TEACHER_EMBEDDING_SIZE, dtype=np.float32)


def test_a_clip_reaches_the_teacher_at_its_own_rate_at_full_scale() -> None:
    """The model was trained at 48 kHz on level-normalized audio, so a stored clip is brought to both."""
    stereo = np.zeros((NOMINAL_WAV_RATE, 2))
    stereo[:, 0] = 0.25 * np.sin(np.linspace(0.0, 200.0, NOMINAL_WAV_RATE))

    prepared = prepare_for_teacher(stereo)

    assert prepared.dtype == np.float32
    assert prepared.shape == (TEACHER_RATE_HZ,)
    assert np.abs(prepared).max() == pytest.approx(1.0)


def test_silence_stays_silence() -> None:
    prepared = prepare_for_teacher(np.zeros((1000, 1)))

    assert np.all(prepared == 0.0)


def test_the_extractor_answers_with_the_teacher_vector_in_double_precision() -> None:
    teacher = RecordingTeacher()
    extractor = ClapFeatureExtractor(teacher)

    vector = extractor.extract(np.ones((2000, 1)) * 0.5)

    assert vector.dtype == np.float64
    assert vector.shape == (TEACHER_EMBEDDING_SIZE,)
    assert len(teacher.heard) == 1


def test_the_registry_offers_the_teacher_as_a_backend() -> None:
    assert TEACHER_BACKEND_NAME in BACKEND_REGISTRY


def test_loading_the_teacher_names_the_extra_it_needs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(teacher_backend, "teacher_available", lambda: False)

    with pytest.raises(RuntimeError, match="teacher extra"):
        load_teacher()


@dataclass(frozen=True)
class WindowCase:
    frames: int
    window: int
    expected_head: tuple[float, ...]


@pytest.mark.parametrize(
    "case",
    [
        WindowCase(frames=3, window=8, expected_head=(1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 0.0, 0.0)),
        WindowCase(frames=4, window=8, expected_head=(1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0)),
        WindowCase(frames=10, window=8, expected_head=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0)),
    ],
    ids=lambda case: f"{case.frames}_into_{case.window}",
)
def test_a_clip_fills_the_window_whole_and_rests_against_silence(case: WindowCase) -> None:
    """The model's own reading of a short sound repeats it whole, pads the rest, and reads a long one from its start."""
    mono = np.arange(1, case.frames + 1, dtype=np.float32)

    filled = fill_window(mono, case.window)

    assert filled.shape == (case.window,)
    assert tuple(filled.tolist()) == case.expected_head


def test_the_teacher_loads_the_commit_this_build_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[dict[str, object]] = []

    class RecordingTransformersTeacher:
        def __init__(self, **arguments: object) -> None:
            loaded.append(arguments)

    monkeypatch.setattr(teacher_backend, "teacher_available", lambda: True)
    monkeypatch.setattr(transformers_teacher, "TransformersTeacher", RecordingTransformersTeacher)

    load_teacher(device="cpu")

    assert loaded == [
        {"checkpoint": TEACHER_CHECKPOINT, "revision": TEACHER_REVISION, "rate_hz": TEACHER_RATE_HZ, "device": "cpu"}
    ]


class _MeanOverFrames:
    """A stand-in audio tower hearing each clip alone: its log-mel picture averaged over frames."""

    def get_audio_features(self, input_features: torch.Tensor) -> torch.Tensor:
        return input_features[:, 0].mean(dim=1)


def _small_teacher() -> TransformersTeacher:
    """The teacher's own log-mel reading around a stand-in tower, so a test hears batches without the checkpoint."""
    teacher = TransformersTeacher.__new__(TransformersTeacher)
    teacher._rate_hz = SMALL_RATE_HZ
    teacher._device = "cpu"
    teacher._window_frames = SMALL_RATE_HZ
    teacher._fft_length = SMALL_FFT_LENGTH
    teacher._hop_length = SMALL_FFT_LENGTH // 4
    teacher._mel_filters = torch.rand(
        (SMALL_FFT_LENGTH // 2 + 1, SMALL_MEL_BANDS), generator=torch.Generator().manual_seed(0)
    )
    teacher._taper = torch.hann_window(SMALL_FFT_LENGTH, periodic=True)
    teacher._model = _MeanOverFrames()  # type: ignore[assignment]
    return teacher


def test_a_batch_is_heard_as_each_of_its_clips_would_be_alone() -> None:
    teacher = _small_teacher()
    generator = np.random.default_rng(0)
    clips = [generator.standard_normal(frames).astype(np.float32) for frames in (300, SMALL_RATE_HZ, 2 * SMALL_RATE_HZ)]

    batch = teacher.embed_many(clips)

    assert batch.shape == (len(clips), SMALL_MEL_BANDS)
    for clip, vector in zip(clips, batch, strict=True):
        np.testing.assert_allclose(vector, teacher.embed(clip), rtol=1e-5, atol=1e-6)


def test_a_batch_reaches_the_teacher_prepared_and_answers_one_vector_per_waveform() -> None:
    teacher = RecordingTeacher()
    waveforms = [np.full((NOMINAL_WAV_RATE, 1), level) for level in (0.1, 0.2, 0.3)]

    vectors = ClapFeatureExtractor(teacher).extract_many(waveforms)

    assert len(vectors) == len(waveforms)
    assert [clip.shape for clip in teacher.heard] == [(TEACHER_RATE_HZ,)] * len(waveforms)
