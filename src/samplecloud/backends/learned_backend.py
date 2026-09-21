from __future__ import annotations

from pathlib import Path
from typing import Final

from samplecloud.backends import FeatureExtractor

DEFAULT_LEARNED_DEVICE: Final[str] = "cuda"


def build_learned_extractor(library_root: Path, *, model_name: str, device: str) -> FeatureExtractor:
    """A descriptor `sampledescriptor` trained, loaded by name from the library's model store.

    The import sits inside the call so the backends that need no torch keep needing none until
    this one is chosen, which is what lets a cloud pass over a hand-built descriptor run on a
    machine without the training stack.
    """
    # pylint: disable=import-outside-toplevel
    import torch

    from sampledescriptor.descriptors.learned import load_descriptor
    from sampledescriptor.model_paths import descriptor_path

    return load_descriptor(descriptor_path(library_root, name=model_name), device=torch.device(device))
