from __future__ import annotations

import sys
from typing import Final

from pydantic import BaseModel

from samplecore.cli_parsing import command_parser
from samplecore.devices import usable_cuda_card
from samplecore.models.base import FROZEN

AUTOMATIC_DEVICE: Final[str] = "auto"
CUDA_DEVICE: Final[str] = "cuda"
CPU_DEVICE: Final[str] = "cpu"


class BuildDevice(BaseModel):
    """What a build's steps compute on: an NVIDIA card by name, or the processor where `card` is None."""

    model_config = FROZEN

    card: str | None


def resolved_device(device: str) -> str:
    """The device a step's command runs on: the one named, or for `auto` an NVIDIA card where torch reaches one."""
    return available_device() if device == AUTOMATIC_DEVICE else device


def available_device() -> str:
    """CUDA where torch computes on a card here, the processor otherwise."""
    return CUDA_DEVICE if usable_cuda_card() is not None else CPU_DEVICE


def main(argv: list[str], *, prog: str) -> None:
    """Print the device builds compute on, as the JSON the application reads."""
    command_parser(prog=prog, description="Name the device builds compute on.").parse_args(argv)
    sys.stdout.write(f"{BuildDevice(card=usable_cuda_card()).model_dump_json()}\n")
