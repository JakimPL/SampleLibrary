from __future__ import annotations

from functools import cache
from typing import Final

AUTOMATIC_DEVICE: Final[str] = "auto"
CUDA_DEVICE: Final[str] = "cuda"
CPU_DEVICE: Final[str] = "cpu"


def resolved_device(device: str) -> str:
    """The device a step's command runs on: the one named, or for `auto` an NVIDIA card where torch reaches one."""
    return available_device() if device == AUTOMATIC_DEVICE else device


@cache
def available_device() -> str:
    """CUDA where torch is installed and sees a card, the processor otherwise.

    torch answers whether a CUDA device is usable, and importing it takes a moment, so a run asks once.
    """
    try:
        import torch  # pylint: disable=import-outside-toplevel
    except ImportError:
        return CPU_DEVICE
    return CUDA_DEVICE if torch.cuda.is_available() else CPU_DEVICE
