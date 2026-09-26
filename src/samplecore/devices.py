from __future__ import annotations

import re
from functools import cache
from typing import Final

ARCHITECTURE_PATTERN: Final[re.Pattern[str]] = re.compile(r"(sm|compute)_(\d+)(\d)")
BINARY_ARCHITECTURE: Final[str] = "sm"

CardCapability = tuple[int, int]


@cache
def usable_cuda_card() -> str | None:
    """The NVIDIA card torch computes on here, by name, or None where it reaches none its build runs on.

    A card torch reaches but its build carries no code for, such as one older than the build
    supports, counts as none, so work runs on the processor rather than failing at its first kernel.
    torch loads its CUDA libraries as it is imported, which takes a moment, so a process asks once.
    """
    try:
        import torch  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    capability = torch.cuda.get_device_capability()
    if not any(runs_on(architecture, capability) for architecture in torch.cuda.get_arch_list()):
        return None
    return torch.cuda.get_device_name()


def runs_on(architecture: str, capability: CardCapability) -> bool:
    """Whether code torch carries for ``architecture``, such as `sm_86` or `compute_90`, runs on a card of this capability.

    Machine code runs on cards of its own major version at its minor version or above, so `sm_86`
    serves a card of capability 8.9; code carried as PTX compiles for any card at its version or above.
    """
    match = ARCHITECTURE_PATTERN.fullmatch(architecture)
    if match is None:
        return False
    built_for = (int(match.group(2)), int(match.group(3)))
    if match.group(1) == BINARY_ARCHITECTURE:
        return built_for[0] == capability[0] and built_for[1] <= capability[1]
    return built_for <= capability
