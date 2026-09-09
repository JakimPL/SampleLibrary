from __future__ import annotations

from pathlib import Path
from typing import Final

from samplecloud.backends import FeatureExtractor
from samplecore.models.experiment import MODEL_PARAMETER

DEFAULT_LEARNED_DEVICE: Final[str] = "cuda"


def build_learned_extractor(library_root: Path, *, model_name: str, device: str) -> FeatureExtractor:
    """A descriptor `samplemorph` trained, loaded by name from the library's model store.

    The import sits inside the call so the backends that need no torch keep needing none until
    this one is chosen, which is what lets a cloud pass over a hand-built descriptor run on a
    machine without the training stack.
    """
    # pylint: disable=import-outside-toplevel
    import torch

    from samplemorph.descriptors.learned import descriptor_path, load_descriptor

    return load_descriptor(descriptor_path(library_root, name=model_name), device=torch.device(device))


def learned_parameters(model_name: str) -> dict[str, str]:
    """What an experiment extracted by a learned descriptor records: which stored model it was."""
    return {MODEL_PARAMETER: model_name}
