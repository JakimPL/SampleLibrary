from __future__ import annotations

from collections.abc import Sequence
from importlib.util import find_spec
from math import gcd
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.waveform import fold_to_mono

TEACHER_BACKEND_NAME: Final[str] = "clap"
TEACHER_CHECKPOINT: Final[str] = "laion/larger_clap_music_and_speech"
# The hub serves a checkpoint's newest commit unless told otherwise, so the commit is pinned: a
# vector read today and one read after the checkpoint's authors push again come from one model.
TEACHER_REVISION: Final[str] = "195c3a3e68faebb3e2088b9a79e79b43ddbda76b"
TEACHER_RATE_HZ: Final[int] = 48_000
TEACHER_EMBEDDING_SIZE: Final[int] = 512
TEACHER_EXTRA: Final[str] = "teacher"
TEACHER_DEVICE_AUTOMATIC: Final[str] = "auto"


class Teacher(Protocol):
    """A pretrained model that hears a clip, or reads a sentence, and answers with one vector in one space."""

    def embed(self, mono: NDArray[np.float32]) -> NDArray[np.float32]: ...

    def embed_text(self, texts: Sequence[str]) -> NDArray[np.float32]: ...


class ClapFeatureExtractor:
    """A descriptor read from a pretrained audio-text model, which knows sound from millions of captions.

    The model was trained on what people wrote about recordings, so what it puts near one another
    is what people would call alike: on the first hand labels it leads the hand-built descriptors by
    a wide margin while knowing nothing about tracker samples. It reads the clip at the rate the
    store writes, and the pass handing it the clip decides whether the frames arrive as stored or
    as the library plays them. Beside its place in the cloud it is the teacher a descriptor reading
    this project's own canonical grid is distilled from.
    """

    def __init__(self, teacher: Teacher) -> None:
        self._teacher = teacher

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        vector = self._teacher.embed(prepare_for_teacher(waveform))
        return np.asarray(vector, dtype=np.float64)


def prepare_for_teacher(waveform: NDArray[np.float64]) -> NDArray[np.float32]:
    """One channel at the teacher's own rate, at full scale, in the precision it computes in."""
    mono = fold_to_mono(waveform)
    factor = gcd(TEACHER_RATE_HZ, NOMINAL_WAV_RATE)
    resampled: NDArray[np.float32] = resample_poly(mono, TEACHER_RATE_HZ // factor, NOMINAL_WAV_RATE // factor).astype(
        np.float32
    )
    peak = float(np.abs(resampled).max())
    return resampled / peak if peak > 0.0 else resampled


def teacher_available() -> bool:
    """Whether the `teacher` extra is installed, which the pretrained model needs to load."""
    return find_spec("transformers") is not None and find_spec("torch") is not None


def load_teacher(*, device: str = TEACHER_DEVICE_AUTOMATIC) -> Teacher:
    """The pretrained model, fetched into the machine's model cache on first use.

    `device` names where it computes; the automatic choice takes the GPU when there is one, and
    naming the processor keeps the model off a GPU another job holds.

    Raises:
        RuntimeError: the `teacher` extra is absent, so the model cannot be loaded.
    """
    if not teacher_available():
        raise RuntimeError(
            f"the {TEACHER_BACKEND_NAME} backend needs the {TEACHER_EXTRA} extra: uv sync --extra {TEACHER_EXTRA}"
        )

    # pylint: disable-next=import-outside-toplevel
    from samplecloud.backends.transformers_teacher import TransformersTeacher, preferred_device

    chosen = preferred_device() if device == TEACHER_DEVICE_AUTOMATIC else device
    return TransformersTeacher(
        checkpoint=TEACHER_CHECKPOINT, revision=TEACHER_REVISION, rate_hz=TEACHER_RATE_HZ, device=chosen
    )


def build_teacher_extractor() -> ClapFeatureExtractor:
    """The registry's factory: the pretrained model behind the extractor protocol."""
    return ClapFeatureExtractor(load_teacher())
