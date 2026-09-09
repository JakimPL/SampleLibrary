from __future__ import annotations

from collections.abc import Callable
from typing import Final

from samplecloud.backends import FeatureExtractor
from samplecloud.backends.invariant_backend import InvariantFeatureExtractor
from samplecloud.backends.librosa_backend import LibrosaFeatureExtractor
from samplecloud.backends.teacher_backend import TEACHER_BACKEND_NAME, build_teacher_extractor

DEFAULT_BACKEND_NAME: Final[str] = "librosa"

BACKEND_REGISTRY: Final[dict[str, Callable[[], FeatureExtractor]]] = {
    DEFAULT_BACKEND_NAME: LibrosaFeatureExtractor,
    "invariant": InvariantFeatureExtractor,
    TEACHER_BACKEND_NAME: build_teacher_extractor,
}
